# -*- coding: utf-8 -*-
from odoo import api, fields, models

# Daylight accId values from the Accessorial Matrix on dylt-portalapi.apigee.io/overview.
# "-" = Daylight has no such charge (left out of Daylight requests, still on our BOL).
DEFAULT_DAYLIGHT_CODES = {
    'LIFTGATE_DEL': 'Lift Gate Delivery',
    'RESIDENTIAL_DEL': 'Residential Delivery',
    'LIMITED_ACCESS_DEL': 'Limited Access or Constr Site Dlvry',
    'INSIDE_DEL': 'Inside Delivery',
    'APPOINTMENT_DEL': 'Appointment Fee',
    'NOTIFY_DEL': '-',
    'LIFTGATE_PU': 'Lift Gate Pickup',
}


class LtlAccessorial(models.Model):
    _inherit = 'selamta.ltl.accessorial'

    dylt_code = fields.Char(
        'Daylight code',
        help='Daylight\'s accessorial code for this service (accId in the Accessorial Matrix on '
             'Daylight\'s API portal), e.g. "Lift Gate Delivery". Enter "-" when Daylight has no '
             'such charge. Services left empty are not included in Daylight rates, and Daylight '
             'pickups cannot be booked with them.')

    @api.model
    def _dylt_set_default_codes(self):
        """Fill in Daylight codes for our standard services, without touching codes that
        were already set (runs on install and on every update)."""
        for service in self.with_context(active_test=False).search(
                [('code', 'in', list(DEFAULT_DAYLIGHT_CODES)), ('dylt_code', '=', False)]):
            service.dylt_code = DEFAULT_DAYLIGHT_CODES[service.code]
