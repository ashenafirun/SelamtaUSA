# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    card_fees = fields.Monetary(
        string="Card Fees",
        currency_field="currency_id",
        help="Card processing fee added to this charge, computed on the amount being paid.",
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

    @api.depends("payment_method_line_id", "payment_token_id")
    def _compute_adyen_method_code(self):
        for rec in self:
            rec.adyen_method_code = (
                rec.payment_token_id.payment_method_id.code or ""
            )

    @api.depends(
        "amount",
        "payment_method_line_id",
        "payment_token_id",
        "partner_id",
        "currency_id",
        "payment_type",
        "can_edit_wizard",
        "group_payment",
    )
    def _compute_card_account_compute_fees(self):
        for rec in self:
            rec.card_fees = rec._get_card_fee()

    def _get_card_fee(self):
        """Return the card fee for this charge.

        The fee is computed on the amount actually being charged (a partial
        payment pays a fee on the part paid), never on the invoices' open balance.
        """
        self.ensure_one()
        if not self.amount or not self._should_apply_adyen_fees():
            return 0.0
        provider = self.payment_method_line_id.payment_provider_id
        partner_country = self.partner_id.country_id or self.company_id.country_id
        return self.currency_id.round(
            provider._card_compute_fees(self.amount, self.currency_id, partner_country)
        )

    def _is_single_payment(self):
        """Mirror the test Odoo uses to build one payment from the wizard values.

        That is the only case where the wizard's amount (and a saved card) is used.
        When the wizard splits into one payment per invoice, nothing is charged to
        a card, so no fee applies.
        """
        self.ensure_one()
        if not self.can_edit_wizard:
            return False
        if self.group_payment:
            return True
        batches = self.batches or []
        return bool(batches) and len(batches[0]["lines"]) == 1

    def _should_apply_adyen_fees(self):
        self.ensure_one()
        provider = self.payment_method_line_id.payment_provider_id
        if not provider or provider.code != "adyen":
            return False
        if not getattr(provider, "fees_active", False):
            return False
        if self.payment_type != "inbound":
            return False
        # The fee applies only when Odoo actually charges a saved card. Without a
        # saved card nothing is charged, so the payment is just recorded as typed.
        token_method = self.payment_token_id.payment_method_id
        if not token_method or not provider.is_support_fees(token_method):
            return False
        has_fees = (
            provider.fees_dom_fixed > 0
            or provider.fees_dom_var > 0
            or provider.fees_int_fixed > 0
            or provider.fees_int_var > 0
        )
        if not has_fees:
            return False
        return self._is_single_payment()

    def _create_payment_vals_from_wizard(self, batch_result):
        """Record the payment for amount + fee, with the fee booked on the payment.

        The fee goes to the fee income account through a write-off line, so only
        the amount itself is applied to the invoices. The invoices are not
        modified (adding a fee line meant resetting them to draft, which detached
        every payment already applied to them).
        """
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        fee = self.env.context.get("card_fees") or 0.0
        if fee:
            provider = self.payment_method_line_id.payment_provider_id
            write_off = provider._prepare_card_fee_write_off_vals(
                fee, self.currency_id, self.partner_id, self.payment_date
            )
            payment_vals["amount"] = self.amount + fee
            payment_vals.setdefault("write_off_line_vals", []).append(write_off)
        return payment_vals

    def action_create_payments(self):
        fee = self._get_card_fee()
        if fee:
            provider = self.payment_method_line_id.payment_provider_id
            if not provider._get_card_fee_account():
                raise UserError(_(
                    "Set an income account on the 'Payment Fees' product (or its "
                    "product category) before charging card fees."
                ))
            if not self.payment_method_line_id.payment_account_id:
                # Without an Outstanding Receipts account Odoo posts no journal
                # entry for the payment, so the fee line would be silently dropped.
                raise UserError(_(
                    "Set an Outstanding Receipts account on the '%(method)s' payment "
                    "method of the %(journal)s journal before charging card fees.",
                    method=self.payment_method_line_id.name,
                    journal=self.journal_id.display_name,
                ))
        _logger.info(
            "[PAYMENT] Amount: %s | Card fee: %s | Total charged: %s",
            self.amount,
            fee,
            self.amount + fee,
        )
        context = dict(self.env.context or {})
        context.update(
            {
                "is_backend_method": True,
                "amount": self.amount + fee,
                "card_fees": fee,
            }
        )
        return super(
            AccountPaymentRegister, self.with_context(**context)
        ).action_create_payments()
