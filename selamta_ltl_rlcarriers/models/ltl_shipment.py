# -*- coding: utf-8 -*-
from odoo import fields, models


class LtlShipment(models.Model):
    _inherit = 'selamta.ltl.shipment'

    rlc_service_center = fields.Char(
        'R+L service center', copy=False, readonly=True,
        help='R+L origin service center from the rate quote, with its phone number.')
