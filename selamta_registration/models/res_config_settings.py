# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    selamta_registration_notify_email = fields.Char(
        'Send new applications to',
        config_parameter='selamta_registration.notify_email',
        help='Email address(es) that get a message for every new wholesale application. '
             'Separate several addresses with commas.',
    )
    selamta_google_places_api_key = fields.Char(
        'Google Places API key',
        config_parameter='selamta_registration.google_places_api_key',
        groups='base.group_system',
        help='Key for "Places API (New)" in Google Cloud. Used to suggest street addresses '
             'while customers type on the wholesale registration page.',
    )
    selamta_pricelist_georgia_id = fields.Many2one(
        'product.pricelist', 'Pricelist for Georgia businesses',
        config_parameter='selamta_registration.pricelist_georgia_id',
        help='Set on a business with a Georgia address when you approve its wholesale application.',
    )
    selamta_pricelist_other_id = fields.Many2one(
        'product.pricelist', 'Pricelist for other states',
        config_parameter='selamta_registration.pricelist_other_id',
        help='Set on businesses outside Georgia when you approve their application. '
             'Leave empty to keep Odoo\'s default pricelist.',
    )
