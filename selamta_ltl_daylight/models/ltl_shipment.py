# -*- coding: utf-8 -*-
from odoo import fields, models


class LtlShipment(models.Model):
    _inherit = 'selamta.ltl.shipment'

    dylt_reservation = fields.Char(
        'Daylight reservation', copy=False, readonly=True,
        help='Daylight\'s answer to the pickup request: accepted, or adjusted with the reason.')
