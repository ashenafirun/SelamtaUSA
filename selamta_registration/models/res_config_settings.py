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
