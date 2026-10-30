# -*- coding: utf-8 -*-
from odoo import api, fields, models


class LtlShipment(models.Model):
    _inherit = 'selamta.ltl.shipment'

    p1_carrier_name = fields.Char('Carrier (Priority1)', copy=False, tracking=True,
                                  help='The carrier Priority1 booked for this shipment.')
    p1_carrier_scac = fields.Char('SCAC (Priority1)', copy=False)
    p1_shipment_id = fields.Char('Priority1 shipment ID', copy=False, readonly=True)

    @api.depends('carrier_id.name', 'carrier_id.ltl_scac', 'p1_carrier_name', 'p1_carrier_scac')
    def _compute_print_carrier(self):
        super()._compute_print_carrier()
        for shipment in self.filtered('p1_carrier_name'):
            shipment.print_carrier_name = '%s (via %s)' % (shipment.p1_carrier_name, shipment.carrier_id.name) \
                if shipment.carrier_id else shipment.p1_carrier_name
            shipment.print_carrier_scac = shipment.p1_carrier_scac or False
