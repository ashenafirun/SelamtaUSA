# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

import logging

from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
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
    card_fee_on_payment = fields.Boolean(
        string="Card Fee Booked on Payment",
        readonly=True,
        copy=False,
        help="The card fee was booked on the payment, to the fee income account, "
        "instead of being added to an order.",
    )
    card_fee_on_order = fields.Boolean(
        string="Card Fee Added to Order",
        readonly=True,
        copy=False,
        help="The card fee was added as a line on the sale order this payment confirmed.",
    )
    card_fee_refunded = fields.Monetary(
        string="Card Fee Refunded",
        currency_field="currency_id",
        readonly=True,
        copy=False,
        help="Part of the source payment's card fee taken back by this refund.",
    )

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
        """Record the payment for the full amount charged to the card.

        Adyen charged `amount + fees`, so the payment is created for that total.

        - Paid from a quotation that this payment confirmed: the fee was added as a
          line on the order (`_check_amount_and_confirm_order`) and flows to its
          invoice, so the whole payment is applied to the invoice as before.
        - Anything else (invoices, an order that was already confirmed, a payment
          link with no document): the fee is booked on the payment as a write-off
          to the fee income account. Only the amount itself is applied to the
          customer's account, and invoices are never reset to draft (resetting
          them detached the payments already applied to them).
        - A refund of a payment whose fee was booked that way takes back the
          refunded share of the fee, so the customer isn't left owing it.
        """
        self.ensure_one()
        if self.operation == "refund":
            fee_refunded = self._add_card_fee_refund_write_off(extra_create_values)
            payment = super()._create_payment(**extra_create_values)
            if fee_refunded:
                self.card_fee_refunded = fee_refunded
            return payment

        fee = self.currency_id.round(self.fees or 0.0)
        if not fee:
            return super()._create_payment(**extra_create_values)

        gross = self.currency_id.round(self.amount + fee)
        extra_create_values["amount"] = gross
        fee_on_payment = False
        if not self.card_fee_on_order:
            write_off = self.provider_id._prepare_card_fee_write_off_vals(
                fee,
                self.currency_id,
                self.partner_id.commercial_partner_id,
            )
            if write_off:
                extra_create_values["write_off_line_vals"] = list(
                    extra_create_values.get("write_off_line_vals") or []
                ) + [write_off]
                fee_on_payment = True
            else:
                _logger.warning(
                    "No income account on the Payment Fees product: the %s fee "
                    "of %s stays on the customer's account.",
                    fee,
                    self.reference,
                )
        payment = super()._create_payment(**extra_create_values)
        # Keep tx.amount as the full amount charged to the card, fee included.
        # Set after the payment is created so Odoo's early-payment-discount check,
        # which compares tx.amount with the amount due, still sees the amount itself.
        self.write({"amount": gross, "card_fee_on_payment": fee_on_payment})
        return payment

    def _add_card_fee_refund_write_off(self, extra_create_values):
        """Add the write-off that takes back the fee share of a refund.

        :return: the fee amount taken back (0.0 when there is none).
        """
        self.ensure_one()
        source = self.source_transaction_id
        source_payment = source.payment_id
        fee = source.currency_id.round(source.fees or 0.0)
        if not (source.card_fee_on_payment and fee and source_payment.amount):
            return 0.0

        refunded = abs(self.amount)
        earlier_refunds = source.child_transaction_ids.filtered(
            lambda tx: tx != self and tx.operation == "refund" and tx.payment_id
        )
        fee_already_refunded = sum(earlier_refunds.mapped("card_fee_refunded"))
        amount_already_refunded = sum(earlier_refunds.mapped("payment_id.amount"))
        if self.currency_id.compare_amounts(
            refunded + amount_already_refunded, source_payment.amount
        ) >= 0:
            # Last refund: take back whatever is left, so rounding never leaves a cent.
            fee_part = fee - fee_already_refunded
        else:
            fee_part = fee * refunded / source_payment.amount
        fee_part = self.currency_id.round(max(min(fee_part, fee - fee_already_refunded), 0.0))
        if not fee_part:
            return 0.0

        # Reverse the fee on the account it was booked to.
        _liquidity, _counterpart, write_offs = source_payment._seek_for_lines()
        fee_line = write_offs.filtered(
            lambda line: source.currency_id.is_zero(line.amount_currency + fee)
        )[:1]
        write_off = source.provider_id._prepare_card_fee_write_off_vals(
            fee_part,
            self.currency_id,
            self.partner_id.commercial_partner_id,
            refund=True,
            account=fee_line.account_id or None,
        )
        if not write_off:
            return 0.0
        extra_create_values["write_off_line_vals"] = list(
            extra_create_values.get("write_off_line_vals") or []
        ) + [write_off]
        return fee_part

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
            if context.get("is_backend_method") and values.get("payment_id"):
                # Charged from Register Payment: the wizard already computed the fee
                # and recorded the payment for amount + fee, with the fee booked on it.
                values["amount"] = context.get("amount", values.get("amount", 0.0))
                values["fees"] = context.get("card_fees") or 0.0
                values["net_amount"] = values["amount"] - values["fees"]
                values["card_fee_on_payment"] = bool(values["fees"])
            elif values.get("source_transaction_id"):
                # Refunds, partial captures and voids of an earlier charge: the fee
                # belongs to the source transaction, never charged again.
                pass
            elif provider.is_support_fees(method) and values.get("operation") not in [
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
                # A saved card charged from a payment whose fee wasn't booked
                # (Register Payment and Payments > New both book it and set the
                # backend flag): the card would be charged the fee while the payment
                # records only the amount. Refuse rather than charge.
                if values["fees"] and values.get("payment_id"):
                    raise UserError(_(
                        "The card processing fee can't be added to this payment. "
                        "Create a new payment (Accounting > Payments > New) or use "
                        "Register Payment on the invoice to charge the card."
                    ))
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
                        tx.with_company(tx.company_id)._add_fee_line_to_sale_order()
                        fee_product = self.env.ref(
                            "sync_payment_adyen_charge.product_product_payment_fees",
                            raise_if_not_found=False,
                        )
                        # The fee is now on the order and will be invoiced with it,
                        # so the payment must not book it a second time.
                        tx.card_fee_on_order = bool(
                            fee_product
                            and quotation.order_line.filtered(
                                lambda line: line.product_id == fee_product
                            )
                        )
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