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

    @api.depends(
        "amount", "payment_token_id", "partner_id", "currency_id",
        "payment_type", "partner_type", "state",
    )
    def _compute_card_fee_preview(self):
        for payment in self:
            payment.card_fee_preview = payment._get_hand_entered_card_fee()

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
