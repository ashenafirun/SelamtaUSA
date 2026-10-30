# -*- coding: utf-8 -*-
from odoo import fields, models


class LtlShipment(models.Model):
    _inherit = 'selamta.ltl.shipment'

    rrts_terminal = fields.Char(
        'Roadrunner terminal', copy=False, readonly=True,
        help='Roadrunner terminal that picks up this shipment, with its phone number.')
