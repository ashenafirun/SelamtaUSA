# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

import logging

from odoo import models, fields, api, _, Command
from odoo.addons.payment import utils as payment_utils


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    fees = fields.Monetary(
        string="Fees",
        currency_field="currency_id",
        help="The fees amount; set by the system as it depends on the provider",
        readonly=True,
    )
    net_amount = fields.Monetary(
        string="Net Amount",
        currency_field="currency_id",
        readonly=True,
        help="Transaction amount excluding processing fees.",
    )
    fee_json = fields.Json(string="Fee Map")

    def _get_specific_processing_values(self, processing_values):
        res = super()._get_specific_processing_values(processing_values)

        if self.provider_code != "adyen":
            return res
        total_amount = self.amount + (self.fees or 0)
        converted_amount = payment_utils.to_minor_currency_units(
            total_amount, self.currency_id
        )
        res.update(
            {
                "converted_amount": converted_amount,
                "access_token": payment_utils.generate_access_token(
                    processing_values["reference"],
                    converted_amount,
                    self.currency_id.id,
                    processing_values["partner_id"],
                ),
            }
        )
        return res

    def _create_payment(self, **extra_create_values):
        self.ensure_one()
        if self.fees and self.operation != "refund":
            # self._add_fee_line_to_sale_order()

            # tx.amount should remain full order total including fee
            payment_amount = self.amount + self.fees
            self.amount = payment_amount
            extra_create_values.update(
                {
                    "amount": payment_amount,
                }
            )

        payment = super()._create_payment(**extra_create_values)

        if self.fees and self.operation != "refund":
            self._add_fee_line_to_invoice(payment)

        return payment

    def _add_fee_line_to_invoice(self, payment):
        """
        Add an Adyen processing fee line to the related posted invoice.

        At this point:
        - Invoice is posted
        - Payment is created and reconciled against the invoice for (amount + fee)
        - We need to: unreconcile → draft → add line → re-post → re-reconcile
        """
        if self.sale_order_ids:
            return

        fee_product = self.env.ref(
            "sync_payment_adyen_charge.product_product_payment_fees",
            raise_if_not_found=False,
        )
        if not fee_product:
            _logger.warning("Adyen fee product not found, skipping fee line addition")
            return

        invoices = self.invoice_ids.filtered(
            lambda inv: inv.move_type == "out_invoice" and inv.state == "posted"
        )
        total_inv_amount = sum(invoices.mapped(lambda i: i.amount_total or 0.0))
        for invoice in invoices:
            self._apply_fee_to_invoice(invoice, payment, fee_product, total_inv_amount)

    def _apply_fee_to_invoice(
        self, invoice, payment, fee_product, total_inv_amount, fee_map=None
    ):
        """
        Add an Adyen fee line to a specific invoice.

        Fee calculation priority:
        1. fee_map (explicit per-invoice fee from fee_json)
        2. self.fees (already computed on the actual transaction amount, which
           may be a partial amount from a payment link)
        3. Proportional recalculation for multi-invoice transactions
        """
        fee_account = (
            fee_product.property_account_income_id
            or fee_product.categ_id.property_account_income_categ_id
        )
        if not fee_account:
            _logger.warning(
                "No income account on fee product, skipping invoice %s",
                invoice.name,
            )
            return

        invoice_fee = 0.0

        # Priority 1: Use explicit fee_map if provided
        if fee_map:
            raw = fee_map.get(str(invoice.id)) or fee_map.get(invoice.id)
            if raw:
                invoice_fee = invoice.currency_id.round(float(raw))

        # Priority 2: For single invoice, use self.fees directly
        # (already computed on the actual payment amount — partial or full)
        if not invoice_fee and self.fees:
            all_invoices = self.invoice_ids.filtered(
                lambda i: i.move_type == "out_invoice"
            )

            if len(all_invoices) == 1:
                # Single invoice: use self.fees directly — this is already
                # computed on the actual transaction amount (partial or full)
                invoice_fee = invoice.currency_id.round(self.fees)
            else:
                # Multi-invoice: proportionally distribute fee based on
                # net_amount (the actual payment amount, not invoice totals)
                provider = self.provider_id
                if provider and provider.code == "adyen" and provider.fees_active:
                    partner_country = (
                        self.partner_id.country_id or provider.company_id.country_id
                    )
                    is_dom = partner_country == provider.company_id.country_id

                    # Use net_amount (set during create, reflects actual
                    # partial or full payment amount)
                    net_tx_amount = self.net_amount or (
                        self.amount - (self.fees or 0.0)
                    )
                    # total_inv_amount = sum(
                    #     all_invoices.mapped(lambda i: i.amount_total or 0.0)
                    # )

                    if total_inv_amount:
                        # Proportional share of the payment amount for THIS invoice
                        inv_amount = invoice.currency_id.round(
                            (invoice.amount_total / total_inv_amount) * net_tx_amount
                        )
                    else:
                        inv_amount = net_tx_amount

                    # Check "free above" threshold
                    card_fees = (
                        is_dom
                        and provider.fees_dom_above
                        and provider.fees_dom_amount
                        and inv_amount > provider.fees_dom_amount
                    ) or (
                        not is_dom
                        and provider.fees_int_above
                        and provider.fees_int_amount
                        and inv_amount > provider.fees_int_amount
                    )
                    if not card_fees:
                        card_fee = provider._card_compute_fees_without_fixed(
                            inv_amount,
                            invoice.currency_id,
                            partner_country,
                        )

                        if partner_country == provider.company_id.country_id:
                            fixed = provider.fees_dom_fixed
                        else:
                            fixed = provider.fees_int_fixed

                        # Distribute fixed charge proportionally based on
                        # this invoice's share of total selected invoice amount

                        invoice_total_percentage = (
                            invoice.amount_total / total_inv_amount
                            if total_inv_amount
                            else 1.0
                        )
                        fixed_charge = fixed * invoice_total_percentage
                        card_fee += fixed_charge
                        invoice_fee = invoice.currency_id.round(card_fee)

        if not invoice_fee:
            _logger.info("Zero fee for invoice %s, skipping", invoice.name)
            return

        invoice.button_draft()
        invoice.write(
            {
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": fee_product.id,
                            "name": _(
                                "Adyen Processing Fee: %(symbol)s %(amount)s",
                                symbol=self.currency_id.symbol,
                                amount=invoice_fee,
                            ),
                            "account_id": fee_account.id,
                            "price_unit": invoice_fee,
                            "quantity": 1,
                        },
                    )
                ]
            }
        )
        invoice.with_context(by_pass_credit_check=True).action_post()
        _logger.info(
            "Fee line %.2f %s added to invoice %s",
            invoice_fee,
            self.currency_id.name,
            invoice.name,
        )

    def _send_payment_request(self):
        """
        Override of payment to return Adyen-send payment request
        """
        context = dict(self.env.context) or {}
        is_backend = context.get("is_backend_method", False)

        if self.provider_code != "adyen" or not self.fees or is_backend:
            return super()._send_payment_request()
        original_amount = self.amount
        try:
            self.sudo().write(
                {"amount": self.currency_id.round(original_amount + self.fees)}
            )
            super()._send_payment_request()
        finally:
            self.sudo().write({"amount": original_amount})

    @api.model_create_multi
    def create(self, values_list):
        """
        Inherit create method which add fees if the provider have support fees.
        Fee is computed on the actual transaction amount (which may be a partial
        amount from a payment link).
        """
        for values in values_list:
            provider = self.env["payment.provider"].browse(values["provider_id"])
            method = self.env["payment.method"].browse(values.get("payment_method_id"))
            partner = self.env["res.partner"].browse(values["partner_id"])
            context = dict(self.env.context) or {}

            amount = values.get("amount", 0)
            values["fees"] = 0
            values["net_amount"] = amount
            if context.get("is_backend_method"):
                values["amount"] = context.get("amount", values.get("amount", 0.0))
                values["fees"] = context.get("card_fees")
                values["net_amount"] = context.get("amount")
            else:
                if provider.is_support_fees(method) and values.get("operation") not in [
                    "validation",
                    "refund",
                ]:
                    currency = (
                        self.env["res.currency"]
                        .browse(values.get("currency_id"))
                        .exists()
                    )
                    # Fee is computed on `amount` — for partial payment links,
                    # this is the partial amount, NOT the full invoice total.
                    values["fees"] = provider.compute_fees(
                        method, amount, currency=currency, partner_id=partner.id
                    )
                    values["net_amount"] = amount
        txs = super().create(values_list)
        txs.invalidate_recordset(["amount", "fees"])
        return txs

    def _add_fee_line_to_sale_order(self):
        """
        Add an Adyen processing fee line to any linked sale order.

        Called during payment-form preparation so the line is visible on the
        order before the payment is captured.  Safe to call multiple times —
        a guard prevents duplicate lines.
        """
        fee_product = self.env.ref(
            "sync_payment_adyen_charge.product_product_payment_fees",
            raise_if_not_found=False,
        )
        if not fee_product:
            _logger.warning(
                "Adyen fee product not found, skipping fee line addition to sale order"
            )
            return

        for order in self.sale_order_ids.filtered(
            lambda so: so.state in ("draft", "sent", "sale")
        ):
            # Guard: skip if a fee line already exists on this order
            if order.order_line.filtered(lambda line: line.product_id == fee_product):
                _logger.info(
                    "Fee line already exists on sale order %s, skipping", order.name
                )
                continue
            try:
                order.write(
                    {
                        "order_line": [
                            (
                                0,
                                0,
                                {
                                    "product_id": fee_product.id,
                                    "name": _(
                                        "Adyen Processing Fee: %(symbol)s %(amount)s",
                                        symbol=self.currency_id.symbol,
                                        amount=self.fees,
                                    ),
                                    "product_uom_qty": 1,
                                    "price_unit": self.fees,
                                    "is_delivery": False,
                                },
                            )
                        ]
                    }
                )
                _logger.info(
                    "Added Adyen fee line (%.2f %s) to sale order %s",
                    self.fees,
                    self.currency_id.name,
                    order.name,
                )
            except Exception:
                _logger.exception("Failed to add fee line to sale order %s", order.name)

    def _check_amount_and_confirm_order(self):
        confirmed_orders = self.env['sale.order']
        for tx in self:
            if len(tx.sale_order_ids) == 1:
                quotation = tx.sale_order_ids.filtered(lambda so: so.state in ('draft', 'sent'))
                if quotation and quotation._is_confirmation_amount_reached():
                    if tx.provider_code == 'adyen' and tx.fees > 0:
                        # tx._add_fee_line_to_sale_order()
                        tx.with_company(tx.company_id)._add_fee_line_to_sale_order()
                    quotation.with_context(send_email=True).action_confirm()
                    confirmed_orders |= quotation
        return confirmed_orders

    def _invoice_sale_orders(self):
        adyen_txs = self.filtered(lambda tx: tx.provider_code == "adyen" and tx.fees > 0)
        res = self.filtered(lambda tx: tx.id not in adyen_txs.ids)

        for tx in adyen_txs.filtered(lambda tx: tx.sale_order_ids):
            tx = tx.with_company(tx.company_id)

            confirmed_orders = tx.sale_order_ids.filtered(lambda so: so.state == 'sale')

            if confirmed_orders:
                # Force invoiceable
                confirmed_orders._force_lines_to_invoice_policy_order()

                # Create ONLY final invoice
                invoices = confirmed_orders.with_context(
                    raise_if_nothing_to_invoice=False
                )._create_invoices(final=True)

                for invoice in invoices:
                    invoice._portal_ensure_token()

                tx.invoice_ids = [Command.set(invoices.ids)]

        if res:
            super(PaymentTransaction, res)._invoice_sale_orders()


class AccountMove(models.Model):
    _inherit = "account.move"

    def copy(self, default=None):
        """Remove Adyen fee lines from duplicated invoices.
        Fees are tied to a specific payment transaction and must not carry over.
        """
        copied = super().copy(default=default)

        fee_product = self.env.ref(
            "sync_payment_adyen_charge.product_product_payment_fees",
            raise_if_not_found=False,
        )
        if not fee_product:
            return copied

        for copy_move in copied:
            fee_lines = copy_move.invoice_line_ids.filtered(
                lambda line: line.product_id == fee_product
            )
            if fee_lines:
                fee_lines.unlink()
                _logger.info(
                    "Removed %d Adyen fee line(s) from duplicated invoice %s",
                    len(fee_lines),
                    copy_move.name,
                )

        return copied

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def copy(self, default=None):
        """Remove Adyen fee lines from duplicated sale orders.
        Fees are tied to a specific payment transaction and must not carry over.
        """
        copied = super().copy(default=default)

        fee_product = self.env.ref(
            "sync_payment_adyen_charge.product_product_payment_fees",
            raise_if_not_found=False,
        )
        if not fee_product:
            return copied

        for copy_order in copied:
            fee_lines = copy_order.order_line.filtered(
                lambda line: line.product_id == fee_product
            )
            if fee_lines:
                fee_lines.unlink()
                _logger.info(
                    "Removed %d Adyen fee line(s) from duplicated sale order %s",
                    len(fee_lines),
                    copy_order.name,
                )

        return copied