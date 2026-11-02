from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _compute_credit_to_invoice(self):
        # EXTENDS 'sale': standard adds `amount_to_invoice` of every confirmed
        # order. Take back the part that belongs to orders that are already
        # invoiced (see sale.order._selamta_is_closed_for_credit).
        super()._compute_credit_to_invoice()
        commercial_partners = self.commercial_partner_id & self
        if not commercial_partners:
            return
        company = self.env.company
        if not company.account_use_credit_limit:
            return

        # Same selection as sale's _compute_credit_to_invoice, so we only ever
        # remove amounts that standard Odoo added.
        sale_orders = self.env['sale.order'].search([
            ('company_id', '=', company.id),
            ('partner_invoice_id', 'any', [
                ('commercial_partner_id', 'in', commercial_partners.ids),
            ]),
            ('order_line', 'any', [
                '|', ('untaxed_amount_to_invoice', '>', 0),
                     ('invoice_status', '=', 'no'),
            ]),
            ('state', '=', 'sale'),
        ])
        closed_orders = sale_orders.filtered(lambda so: so._selamta_is_closed_for_credit())
        today = fields.Date.context_today(self)
        for (partner, currency), orders in closed_orders.grouped(
            lambda so: (so.partner_invoice_id, so.currency_id),
        ).items():
            leftover = sum(orders.mapped('amount_to_invoice'))
            if currency.is_zero(leftover):
                continue
            partner.commercial_partner_id.credit_to_invoice -= currency._convert(
                leftover, company.currency_id, company, today,
            )
