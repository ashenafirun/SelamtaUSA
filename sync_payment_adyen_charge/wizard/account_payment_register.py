# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

import logging

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    card_fees = fields.Monetary(
        string="Card Fees",
        currency_field="currency_id",
        help="Stripe Charge payment Card fees (e.g., card processing).",
        store=True,
        compute="_compute_card_account_compute_fees",
    )

    provider_code = fields.Selection(
        string="Provider Code",
        related="payment_method_line_id.payment_provider_id.code",
        store=False,
    )

    fees_active = fields.Boolean(
        related="payment_method_line_id.payment_provider_id.fees_active",
        store=False,
        string="Fees Active",
    )

    adyen_method_code = fields.Char(
        compute="_compute_adyen_method_code",
        store=False
    )

    @api.depends("payment_method_line_id",'payment_token_id')
    def _compute_adyen_method_code(self):
        for rec in self:
            rec.adyen_method_code = (
                rec.payment_token_id.payment_method_id.code or ""
            )

    @api.depends("amount", "payment_method_line_id", "partner_id", "currency_id")
    def _compute_card_account_compute_fees(self):
        for rec in self:
            rec.card_fees = 0.0
            if rec.amount and rec.payment_method_line_id:
                provider = rec.payment_method_line_id.payment_provider_id
                payment_method_code = (
                    rec.payment_token_id.payment_method_id.code
                    if rec.payment_token_id
                    else rec.payment_method_line_id.payment_method_id.code
                )
                if (
                    provider
                    and provider.code == "adyen"
                    and getattr(provider, "fees_active", False)
                ):
                    partner_country = (
                        rec.partner_id.country_id or rec.company_id.country_id
                    )
                    is_dom = partner_country == provider.company_id.country_id
                    if is_dom:
                        if (
                            provider.fees_dom_above
                            and provider.fees_dom_amount
                            and rec.amount > provider.fees_dom_amount
                        ):
                            rec.card_fees = 0.0
                            continue
                    else:
                        if (
                            provider.fees_int_above
                            and provider.fees_int_amount
                            and rec.amount > provider.fees_int_amount
                        ):
                            rec.card_fees = 0.0
                            continue
                    computed_fees = provider._card_compute_fees(
                        rec.amount,
                        rec.currency_id,
                        partner_country,
                    )
                    if computed_fees == 0 and (
                        provider.fees_dom_var > 0
                        or provider.fees_int_var > 0
                        or provider.fees_dom_fixed > 0
                        or provider.fees_int_fixed > 0
                    ):
                        fixed = (
                            provider.fees_dom_fixed
                            if is_dom
                            else provider.fees_int_fixed
                        )
                        variable = (
                            provider.fees_dom_var if is_dom else provider.fees_int_var
                        )

                        rec.card_fees = rec.currency_id.round(
                            (rec.amount * variable) + fixed
                        )
                    else:
                        rec.card_fees = rec.currency_id.round(computed_fees)

    def _should_apply_adyen_fees(self):
        provider = self.payment_method_line_id.payment_provider_id
        payment_method_code = (
            self.payment_token_id.payment_method_id.code
            if self.payment_token_id
            else self.payment_method_line_id.payment_method_id.code
        )
        if not provider:
            return False
        if provider.code != "adyen":
            return False
        if payment_method_code == "ach_direct_debit":
            return False
        if not getattr(provider, "fees_active", False):
            return False
        has_fees = (
            provider.fees_dom_fixed > 0
            or provider.fees_dom_var > 0
            or provider.fees_int_fixed > 0
            or provider.fees_int_var > 0
        )
        return has_fees

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        total_fee = self.env.context.get("card_fees", 0.0)
        if total_fee:
            payment_vals["amount"] = self.amount + total_fee
        return payment_vals

    def action_create_payments(self):
        total_fee = 0.0
        # provider = self.payment_method_line_id.payment_provider_id
        fee_product = self.env.ref(
            "sync_payment_adyen_charge.product_product_payment_fees",
            raise_if_not_found=False,
        )

        if self._should_apply_adyen_fees():
            invoices = self.line_ids.mapped("move_id").filtered(
                lambda move: move.move_type == "out_invoice"
            )
            existing_fees_before = {
                inv.id: inv.invoice_line_ids.filtered(
                    lambda line: line.product_id == fee_product
                )[:1].price_unit
                or 0.0
                for inv in invoices
            }
            self.create_fee_line()
            for invoice in invoices:
                fee_line = invoice.invoice_line_ids.filtered(
                    lambda line: line.product_id == fee_product
                )[:1]
                if fee_line:
                    fee_before = existing_fees_before.get(invoice.id, 0.0)
                    new_fee = fee_line.price_unit - fee_before
                    if new_fee > 0:
                        total_fee += new_fee
            total_fee = self.currency_id.round(total_fee)
        _logger.info(
            "[PAYMENT] Amount: %s | New Fee: %s | Total: %s",
            self.amount,
            total_fee,
            self.amount + total_fee,
        )
        self._compute_batches()
        context = dict(self.env.context or {})
        context.update(
            {
                "is_backend_method": True,
                "amount": self.amount + total_fee,
                "card_fees": total_fee,
            }
        )
        return super(
            AccountPaymentRegister, self.with_context(**context)
        ).action_create_payments()

    def create_fee_line(self):
        if not self._should_apply_adyen_fees():
            return

        provider = self.payment_method_line_id.payment_provider_id

        fee_product = self.env.ref(
            "sync_payment_adyen_charge.product_product_payment_fees",
            raise_if_not_found=False,
        )
        if not fee_product:
            _logger.warning("Adyen fee product not found, skipping")
            return

        fee_account = (
            fee_product.property_account_income_id
            or fee_product.categ_id.property_account_income_categ_id
        )
        if not fee_account:
            _logger.warning("No income account on fee product, skipping")
            return

        invoices = self.line_ids.mapped("move_id").filtered(
            lambda move: move.move_type == "out_invoice" and move.state == "posted"
        )

        if not invoices:
            _logger.info("[FEE] No posted customer invoices found")
            return

        partner_country = self.partner_id.country_id or self.company_id.country_id
        is_dom = partner_country == provider.company_id.country_id

        for invoice in invoices:
            if invoice.amount_residual <= 0:
                continue

            existing_fee_line = invoice.invoice_line_ids.filtered(
                lambda line: line.product_id == fee_product
            )[:1]

            if existing_fee_line:
                continue

            if is_dom:
                if (
                    provider.fees_dom_above
                    and provider.fees_dom_amount
                    and invoice.amount_residual > provider.fees_dom_amount
                ):
                    invoice_fee = 0.0
                else:
                    computed_fee = provider._card_compute_fees(
                        invoice.amount_residual,
                        self.currency_id,
                        partner_country,
                    )
                    invoice_fee = self.currency_id.round(computed_fee)
            else:
                if (
                    provider.fees_int_above
                    and provider.fees_int_amount
                    and invoice.amount_residual > provider.fees_int_amount
                ):
                    invoice_fee = 0.0
                else:
                    computed_fee = provider._card_compute_fees(
                        invoice.amount_residual,
                        self.currency_id,
                        partner_country,
                    )
                    invoice_fee = self.currency_id.round(computed_fee)

            if invoice_fee <= 0:
                continue

            invoice.button_draft()

            self.env["account.move.line"].with_context(
                check_move_validity=False
            ).create(
                {
                    "move_id": invoice.id,
                    "product_id": fee_product.id,
                    "name": _(
                        "Adyen Processing Fee: %(symbol)s %(amount)s",
                        symbol=self.currency_id.symbol,
                        amount=invoice_fee,
                    ),
                    "account_id": fee_account.id,
                    "price_unit": invoice_fee,
                    "quantity": 1,
                    "display_type": "product",
                }
            )

            _logger.info(
                "[FEE] Created fee line on invoice %s | Fee: %s",
                invoice.name,
                invoice_fee,
            )

            invoice.with_context(by_pass_credit_check=True).action_post()
