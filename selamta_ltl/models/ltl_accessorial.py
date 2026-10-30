# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LtlAccessorial(models.Model):
    """An extra service ordered from the carrier (liftgate, residential, inside delivery...).

    The code is ours and stays the same for every carrier; each carrier connection maps it
    to that carrier's own code (XPO DLG, TForce LIFD, Saia LiftgateService...).
    """
    _name = 'selamta.ltl.accessorial'
    _description = 'LTL accessorial service'
    _order = 'sequence, id'

    name = fields.Char('Service', required=True, translate=True)
    code = fields.Char(
        'Code', required=True,
        help='Our code for this service, the same for every carrier. Carrier connections '
             'translate it to the carrier\'s own code.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    keywords = fields.Char(
        'Match customer delivery services',
        help='Comma-separated words. When a customer\'s delivery services (on the contact) '
             'contain one of these words, this service is ordered on new shipments to them. '
             'Example: "liftgate".')

    _sql_constraints = [
        ('code_uniq', 'unique (code)', 'This accessorial code already exists.'),
    ]

    @api.model
    def _from_service_names(self, service_names):
        """Accessorials whose keywords appear in any of the given delivery service names."""
        names = [(n or '').lower() for n in service_names]
        found = self.browse()
        for accessorial in self.search([('keywords', '!=', False)]):
            words = [w.strip().lower() for w in accessorial.keywords.split(',') if w.strip()]
            if any(word in name for word in words for name in names):
                found |= accessorial
        return found
