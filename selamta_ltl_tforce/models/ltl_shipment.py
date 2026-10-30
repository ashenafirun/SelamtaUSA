# -*- coding: utf-8 -*-
from odoo import fields, models


class LtlShipment(models.Model):
    _inherit = 'selamta.ltl.shipment'

    tforce_bol_id = fields.Char('TForce BOL ID', copy=False, readonly=True,
                                help='TForce\'s own id for the electronic BOL.')
    tforce_origin_terminal = fields.Char('TForce origin terminal', copy=False, readonly=True)
