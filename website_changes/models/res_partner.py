# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _


class PartnerExt(models.Model):
    _inherit = 'res.partner'

    cs_credit_limit = fields.Float(string="Credit Limit")
    test_boolean = fields.Boolean(string="Test Boolean", compute='test_fn')

    @api.depends('cs_credit_limit', 'total_overdue')
    def test_fn(self):
        self.test_boolean = False
        print('HELLO')
        for partner in self:
            if partner.cs_credit_limit and partner.total_overdue:
                if partner.cs_credit_limit <= partner.total_overdue:
                    partner.sale_warn = 'block'
                    partner.sale_warn_msg = (
                        "Your order total is exceeding the limit defined on your record, so you cannot place this order. "
                        "Please reach out to us to increase your limit or pay online to place the order."
                    )
                else:
                    partner.sale_warn = 'no-message'
                    partner.sale_warn_msg = ''