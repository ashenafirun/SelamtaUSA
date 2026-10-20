# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    fees_active = fields.Boolean(string="Add Extra Fees with Credit Card Payments")
    fees_dom_fixed = fields.Monetary(
        string="Fixed Domestic Fees",
        currency_field="main_currency_id",
        help="A Fixed Fee Amount applied to Domestic Payments.",
    )
    fees_dom_var = fields.Float(
        string="Variable Domestic Fees",
        help="A Percentage-Based fee (e.g., 0.03 for 3%) applied to Domestic Transactions.",
    )
    fees_dom_above = fields.Boolean(string="Free Domestic Fees if Amount is above")
    fees_dom_amount = fields.Float("Domestic Total Amount")

    fees_int_fixed = fields.Monetary(
        string="Fixed International Fees",
        currency_field="main_currency_id",
        help="A Fixed Fee amount applied to International Payments.",
    )
    fees_int_var = fields.Float(
        string="Variable International Fees",
        help="A Percentage-Based Fee (e.g., 0.04 for 4%) applied to International Transactions.",
    )
    fees_int_above = fields.Boolean(string="Free International Fees if Amount is above")
    fees_int_amount = fields.Float("International Total Amount")
    support_fees = fields.Boolean(
        string="Fees Supported", compute="_compute_feature_support_fields"
    )

    def _compute_feature_support_fields(self):
        """
        Override of `payment` to enable additional features.
        """
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "adyen").update(
            {
                "support_fees": True,
            }
        )

    @api.constrains(
        "fees_dom_var",
        "fees_int_var",
        "fees_dom_fixed",
        "fees_int_fixed",
        "fees_dom_amount",
        "fees_int_amount",
    )
    def _check_fee_var_within_boundaries(self):
        """Check that variable fees are within realistic boundaries.

        Variable fee values should always be positive and below 100% to respectively avoid negative
        and infinite (division by zero) fee amounts.

        :return None
        """
        for provider in self:
            if any(
                not 0 <= fee < 1
                for fee in (provider.fees_dom_var, provider.fees_int_var)
            ):
                raise ValidationError(
                    _("Variable fees must always be positive and below 100%.")
                )

            for field in [
                "fees_dom_fixed",
                "fees_int_fixed",
                "fees_dom_amount",
                "fees_int_amount",
            ]:
                fee = getattr(provider, field)
                if fee < 0.0:
                    label = provider._fields[field].string
                    raise ValidationError(_("%s Must always be Positive.") % label)

    def _card_compute_fees(self, amount, currency, country):
        """
        New method which will compute stripe charge fees for card payments
        """
        self.ensure_one()
        fees = 0.0
        if self.fees_active:
            is_dom = False
            if country == self.company_id.country_id:
                is_dom = True
                fixed = self.fees_dom_fixed
                variable = self.fees_dom_var
            else:
                fixed = self.fees_int_fixed
                variable = self.fees_int_var

            fees = (amount * variable) + fixed
            if (self.fees_dom_above and is_dom and amount > self.fees_dom_amount) or (
                self.fees_int_above and not is_dom and amount > self.fees_int_amount
            ):
                fees = 0
        return fees

    def _card_compute_fees_without_fixed(self, amount, currency, country):
        """
        New method which will compute stripe charge fees for card payments
        """
        self.ensure_one()
        fees = 0.0
        if self.fees_active:
            is_dom = False
            if country == self.company_id.country_id:
                is_dom = True
                variable = self.fees_dom_var
            else:
                variable = self.fees_int_var

            fees = amount * variable
            if (self.fees_dom_above and is_dom and amount > self.fees_dom_amount) or (
                self.fees_int_above and not is_dom and amount > self.fees_int_amount
            ):
                fees = 0
        return fees

    def compute_fees(self, pm_sudo, amount, **kwargs):
        """
        New method which will calculate fees
        """
        self.ensure_one()
        if not pm_sudo or not (
            (pm_sudo.code == "card")
            or (
                pm_sudo.primary_payment_method_id
                and pm_sudo.primary_payment_method_id.code == "card"
            )
            and self.code == "adyen"
        ):
            return 0.0
        currency = kwargs.get("currency")
        if isinstance(currency, int):
            currency = self.env["res.currency"].sudo().browse(currency)
        partner_id = kwargs.get("partner_id")
        if isinstance(partner_id, models.BaseModel):
            partner = partner_id.sudo()
        elif partner_id:
            partner = self.env["res.partner"].sudo().browse(partner_id)
        else:
            partner = self.env["res.partner"].sudo()
        # Same rule as staff charges (Register Payment): a customer with no country
        # on file is treated as domestic, so they pay the domestic fee.
        country = partner.country_id or self.company_id.country_id
        return self._card_compute_fees(amount, currency, country)

    def _get_card_fee_account(self):
        """Return the income account the card processing fee is booked to.

        It is the income account of the 'Payment Fees' product, or of its product
        category when the product has none.
        """
        self.ensure_one()
        fee_product = self.env.ref(
            "sync_payment_adyen_charge.product_product_payment_fees",
            raise_if_not_found=False,
        )
        if not fee_product:
            return self.env["account.account"]
        fee_product = fee_product.with_company(self.company_id or self.env.company)
        return (
            fee_product.property_account_income_id
            or fee_product.categ_id.property_account_income_categ_id
        )

    def _prepare_card_fee_write_off_vals(
        self, fee, currency, partner, date=None, refund=False, account=None
    ):
        """Return the write-off line that books a card fee on the payment itself.

        The payment is recorded for the full amount charged to the card (amount +
        fee). This line moves the fee to the fee income account, so only the amount
        itself is applied to the customer's invoices. The invoice is never touched.

        With `refund=True` the line takes the fee back out of the fee income account
        (a refund payment returns amount + fee to the card, but only the amount is
        owed back on the customer's account).

        :return: dict for `write_off_line_vals`, or None when no fee account is set.
        """
        self.ensure_one()
        account = account or self._get_card_fee_account()
        if not account:
            return None
        company = self.company_id or self.env.company
        balance = currency._convert(
            fee, company.currency_id, company, date or fields.Date.context_today(self)
        )
        sign = 1 if refund else -1
        return {
            "name": _("Adyen Processing Fee refund") if refund else _("Adyen Processing Fee"),
            "account_id": account.id,
            "partner_id": partner.id,
            "currency_id": currency.id,
            "amount_currency": sign * fee,
            "balance": sign * balance,
        }

    def is_support_fees(self, method):
        """
        New method for method support fees
        """
        self.ensure_one()
        if (
            method.code == "card" or (
                method.primary_payment_method_id
                and method.primary_payment_method_id.code == "card"
            )
        ) and self.code == "adyen":
            return self.support_fees and self.fees_active