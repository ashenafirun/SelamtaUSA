# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    card_fee_preview = fields.Monetary(
        string="Card Fee",
        currency_field="currency_id",
        compute="_compute_card_fee_preview",
        help="Card processing fee added to the charge when you confirm. The payment "
        "is recorded for the amount plus this fee.",
    )

    card_fee_amount = fields.Monetary(
        string="Card Processing Fee",
        currency_field="currency_id",
        compute="_compute_card_fee_amount",
        help="Card processing fee included in this payment (or, for a refund, the fee "
        "returned with it). Shown as a separate line on the receipt.",
    )
    card_fee_percent = fields.Float(
        string="Card Fee Rate (%)",
        compute="_compute_card_fee_amount",
    )
    card_fee_label = fields.Char(
        string="Card Fee Label",
        compute="_compute_card_fee_amount",
    )
    partner_balance_due = fields.Monetary(
        string="Customer Balance Due",
        currency_field="company_currency_id",
        compute="_compute_partner_balance_due",
        help="What the customer still owes in total, printed at the bottom of the receipt.",
    )
    payment_account_display = fields.Char(
        string="Paid With",
        compute="_compute_payment_account_display",
        help="Card brand or bank method and its last four digits, e.g. VISA •••• 7897.",
    )

    @api.depends("partner_id", "state")
    def _compute_partner_balance_due(self):
        for payment in self:
            partner = payment.partner_id.commercial_partner_id.with_company(payment.company_id)
            if not partner:
                payment.partner_balance_due = 0.0
            elif "total_due" in partner._fields:
                # Same figure as the "remaining balance due" in the receipt email.
                payment.partner_balance_due = partner.total_due
            else:
                lines = self.env["account.move.line"].sudo().search([
                    ("partner_id", "=", partner.id),
                    ("company_id", "=", payment.company_id.id),
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("parent_state", "=", "posted"),
                    ("reconciled", "=", False),
                ])
                payment.partner_balance_due = sum(lines.mapped("amount_residual"))

    @api.depends(
        "payment_transaction_id.payment_method_id",
        "payment_transaction_id.payment_last4",
        "payment_token_id.payment_details",
    )
    def _compute_payment_account_display(self):
        for payment in self:
            tx = payment.sudo().payment_transaction_id
            source = tx.source_transaction_id or tx
            token = payment.sudo().payment_token_id or source.token_id
            method = source.payment_method_id or token.payment_method_id
            last4 = (source.payment_last4 or token.payment_details or "").strip()
            parts = [method.name] if method else []
            if last4[-4:].isdigit():
                parts.append("•••• %s" % last4[-4:])
            payment.payment_account_display = " ".join(parts)

    @api.depends(
        "amount", "payment_token_id", "partner_id", "currency_id",
        "payment_type", "partner_type", "state",
    )
    def _compute_card_fee_preview(self):
        for payment in self:
            payment.card_fee_preview = payment._get_hand_entered_card_fee()

    @api.depends(
        "payment_transaction_id.fees",
        "payment_transaction_id.card_fee_on_payment",
        "payment_transaction_id.card_fee_refunded",
    )
    def _compute_card_fee_amount(self):
        for payment in self:
            tx = payment.sudo().payment_transaction_id
            if tx.operation == "refund":
                fee = tx.card_fee_refunded
            elif tx.card_fee_on_payment:
                fee = tx.fees
            else:
                fee = 0.0
            payment.card_fee_amount = fee
            percent = payment._get_card_fee_percent(tx) if fee else 0.0
            payment.card_fee_percent = percent
            payment.card_fee_label = (
                _("Card processing fee (%s%%)", "%g" % percent) if percent
                else _("Card processing fee")
            )

    def _get_card_fee_percent(self, tx):
        """The percentage to print next to the fee, when it is a plain percentage."""
        provider = tx.provider_id
        source = tx.source_transaction_id or tx
        if not provider or provider.fees_dom_fixed or provider.fees_int_fixed:
            return 0.0
        country = source.partner_id.country_id or provider.company_id.country_id
        rate = provider.fees_dom_var if country == provider.company_id.country_id else provider.fees_int_var
        return rate * 100

    def action_post(self):
        """Charge the card fee on payments entered by hand with a saved card.

        Accounting > Payments > New with a saved card: Odoo charges the card when
        the payment is confirmed. The 3% fee is added to the charge and recorded on
        the payment the same way Register Payment does it: the payment is for
        amount + fee, and a line books the fee to the fee income account, so only
        the amount itself is credited to the customer.
        """
        fee_payments = self.filtered(lambda pay: pay._get_hand_entered_card_fee())
        for payment in fee_payments:
            base_amount = payment.amount
            fee = payment._book_card_fee()
            super(
                AccountPayment,
                payment.with_context(
                    is_backend_method=True,
                    amount=payment.amount,
                    card_fees=fee,
                ),
            ).action_post()
            if payment.state == "canceled" and not payment.move_id:
                # Card declined: show the payment as it was typed.
                payment.amount = base_amount
        return super(AccountPayment, self - fee_payments).action_post()

    def _get_hand_entered_card_fee(self):
        """Return the card fee to add when this payment charges a saved card.

        Only for a customer payment typed in by hand (Register Payment books its
        own fee) that will charge a card and has no journal entry yet.
        """
        self.ensure_one()
        if (
            self.env.context.get("is_backend_method")
            or self.state != "draft"
            or self.move_id
            or self.payment_transaction_id
            or self.payment_type != "inbound"
            or self.partner_type != "customer"
            or not self.payment_token_id
        ):
            return 0.0
        provider = self.payment_token_id.provider_id
        if provider.code != "adyen" or not provider.is_support_fees(
            self.payment_token_id.payment_method_id
        ):
            return 0.0
        country = self.partner_id.country_id or provider.company_id.country_id
        return self.currency_id.round(
            provider._card_compute_fees(self.amount, self.currency_id, country)
        )

    def _book_card_fee(self):
        """Raise the payment to amount + fee and book the fee on its journal entry.

        :return: the fee.
        """
        self.ensure_one()
        fee = self._get_hand_entered_card_fee()
        provider = self.payment_token_id.provider_id
        if not provider._get_card_fee_account():
            raise UserError(_(
                "Set an income account on the 'Payment Fees' product (or its "
                "product category) before charging card fees."
            ))
        if not self.outstanding_account_id:
            raise UserError(_(
                "Set an Outstanding Receipts account on the '%(method)s' payment "
                "method of the %(journal)s journal before charging card fees.",
                method=self.payment_method_line_id.name,
                journal=self.journal_id.display_name,
            ))
        self.amount = self.currency_id.round(self.amount + fee)
        write_off = provider._prepare_card_fee_write_off_vals(
            fee, self.currency_id, self.partner_id, self.date
        )
        # The entry stays in draft until the card is charged; Odoo posts it then,
        # or deletes it if the card is declined.
        move = self.env["account.move"].create(
            self._generate_move_vals(write_off_line_vals=[write_off])
        )
        self.move_id = move
        return fee
