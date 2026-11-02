from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_partner_credit_warning_exclude_amount(self):
        # EXTENDS 'sale': on a draft invoice, sale subtracts the linked orders'
        # amount_to_invoice from the partner's credit_to_invoice. Closed orders
        # are no longer in credit_to_invoice (see res.partner), so don't
        # subtract them a second time.
        exclude_amount = super()._get_partner_credit_warning_exclude_amount()
        today = fields.Date.context_today(self)
        for order in self.line_ids.sale_line_ids.order_id:
            if not order._selamta_is_closed_for_credit():
                continue
            order_amount = min(self._get_sale_order_invoiced_amount(order), order.amount_to_invoice)
            exclude_amount -= order.currency_id._convert(
                max(order_amount, 0), self.company_id.currency_id, self.company_id, today,
            )
        return exclude_amount
