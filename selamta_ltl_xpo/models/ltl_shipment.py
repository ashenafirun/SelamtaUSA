# -*- coding: utf-8 -*-
from odoo import fields, models


class LtlShipment(models.Model):
    _inherit = 'selamta.ltl.shipment'

    xpo_bol_inst_id = fields.Char(
        'XPO BOL id', copy=False, readonly=True,
        help='XPO\'s id for the BOL created through the API; cancelling uses it.')
    xpo_test_booking = fields.Boolean(
        'Booked in XPO test mode', copy=False, readonly=True,
        help='The BOL went to XPO\'s test system: nothing will be picked up.')
    xpo_terminal = fields.Char(
        'XPO terminal', copy=False, readonly=True,
        help='XPO service center (SIC) that picks the shipment up.')
