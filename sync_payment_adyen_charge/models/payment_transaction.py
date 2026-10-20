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

        - Paid from a sale order: the fee is already a line on the order (added by
          `_check_amount_and_confirm_order`) and flows to its invoice, so the whole
          payment is applied to the invoice as before.
        - Paid against invoices, or with no document at all: the fee is booked on
          the payment as a write-off to the fee income account. Only the amount
          itself is applied to the invoices, and the invoices are never reset to
          draft (resetting them detached the payments already applied to them).
        """
        self.ensure_one()
        fee = self.currency_id.round(self.fees or 0.0)
        if fee and self.operation != "refund":
            # tx.amount should remain the full amount charged, fee included.
            self.amount = self.currency_id.round(self.amount + fee)
            extra_create_values["amount"] = self.amount
            if not self.sale_order_ids:
                write_off = self.provider_id._prepare_card_fee_write_off_vals(
                    fee,
                    self.currency_id,
                    self.partner_id.commercial_partner_id,
                )
                if write_off:
                    extra_create_values["write_off_line_vals"] = list(
                        extra_create_values.get("write_off_line_vals") or []
                    ) + [write_off]
                else:
                    _logger.warning(
                        "No income account on the Payment Fees product: the %s fee "
                        "of %s stays on the customer's account.",
                        fee,
                        self.reference,
                    )
        return super()._create_payment(**extra_create_values)

    @api.model
    def _x2many_command_ids(self, commands):
        """Return the record ids an x2many create value links to."""
        ids = []
        for command in commands or []:
            if isinstance(command, int):
                ids.append(command)
            elif isinstance(command, (list, tuple)) and command:
                if command[0] == Command.SET:
                    ids.extend(command[2] or [])
                elif command[0] == Command.LINK:
                    ids.append(command[1])
        return ids

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
                values["fees"] = context.get("card_fees") or 0.0
                values["net_amount"] = values["amount"] - values["fees"]
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
                    # A saved card charged from a payment that has no invoice or
                    # order attached (e.g. Accounting > Payments > New): the fee
                    # would be charged to the card with nothing in Odoo recording
                    # it. Refuse, and send the user to the invoice instead.
                    if (
                        values["fees"]
                        and values.get("operation") == "offline"
                        and not self._x2many_command_ids(values.get("invoice_ids"))
                        and not self._x2many_command_ids(values.get("sale_order_ids"))
                    ):
                        raise UserError(_(
                            "This card payment isn't linked to an invoice, so the card "
                            "processing fee can't be recorded. Charge the card from the "
                            "invoice instead: open the invoice (or select several "
                            "invoices) and use Register Payment."
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