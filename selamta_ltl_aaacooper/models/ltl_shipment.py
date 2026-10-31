# -*- coding: utf-8 -*-
from odoo import fields, models


class LtlShipment(models.Model):
    _inherit = 'selamta.ltl.shipment'

    aact_terminal = fields.Char(
        'AAA Cooper terminal', copy=False, readonly=True,
        help='AAA Cooper service center assigned to the pickup, with its phone number.')
