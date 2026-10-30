# -*- coding: utf-8 -*-
from odoo import fields, models


class LtlAccessorial(models.Model):
    _inherit = 'selamta.ltl.accessorial'

    dylt_code = fields.Char(
        'Daylight code',
        help='Daylight\'s accessorial code for this service (accId), from the Accessorial Matrix '
             'on Daylight\'s API portal. Services without a Daylight code are left out of '
             'Daylight rates, and Daylight pickups cannot be booked with them.')
