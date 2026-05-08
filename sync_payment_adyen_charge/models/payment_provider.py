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
        if (
            (pm_sudo.code == "card")
            or (
                pm_sudo.primary_payment_method_id
                and pm_sudo.primary_payment_method_id.code == "card"
            )
            and self.code == "adyen"
        ):
            currency = kwargs.get("currency")
            if isinstance(currency, int):
                currency = self.env["res.currency"].sudo().browse(currency)
            partner_id = kwargs.get("partner_id")
            country = self.env["res.country"].sudo()
            if isinstance(partner_id, int):
                country = self.env["res.partner"].sudo().browse(partner_id).country_id
        return self._card_compute_fees(amount, currency, country)

    def is_support_fees(self, method):
        """
        New method for method support fees
        """
        self.ensure_one()
        if (
            method.code == "card"
            or (
                method.primary_payment_method_id
                and method.primary_payment_method_id.code == "card"
            )
        ) and self.code == "adyen":
            return self.support_fees and self.fees_active
