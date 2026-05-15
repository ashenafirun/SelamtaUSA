# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    credit_code_id = fields.Many2one("credit.code", "Credit Code")

class SaleOrder(models.Model):
    _inherit = "sale.order"

    is_credit_limit_used = fields.Boolean(
        string="Used Credit Limit"
    )

    used_credit_amount = fields.Float(
        string="Used Credit Amount",
        copy=False,
    )

    def _is_confirmation_amount_reached(self):
        """Return whether the required confirmation amount is reached."""
        self.ensure_one()
        # Standard Odoo behavior
        if not self.used_credit_amount:
            return super()._is_confirmation_amount_reached()
        total_paid = self.amount_paid + self.used_credit_amount
        amount_comparison = self.currency_id.compare_amounts(
            self._get_prepayment_required_amount(),
            total_paid,
        )
        return amount_comparison <= 0

    def _is_paid(self):
        self.ensure_one()
        # Standard behavior
        if not self.used_credit_amount:
            return super()._is_paid()
        total_paid = self.amount_paid + self.used_credit_amount
        return (
            self.currency_id.compare_amounts(
                total_paid,
                self.amount_total,
            ) >= 0
        )