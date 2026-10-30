# -*- coding: utf-8 -*-
from odoo import _, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ltl_shipment_id = fields.Many2one(
        'selamta.ltl.shipment', 'LTL shipment', copy=False, index=True, ondelete='set null')

    def action_ltl_shipment(self):
        """Open this delivery's LTL shipment, creating it the first time. With several
        deliveries selected (same customer), they go on one shipment."""
        shipment = self.ltl_shipment_id
        if len(shipment) != 1 or self.filtered(lambda p: not p.ltl_shipment_id):
            shipment = self.env['selamta.ltl.shipment']._create_from_pickings(self)
        return {
            'type': 'ir.actions.act_window',
            'name': _('LTL shipment'),
            'res_model': 'selamta.ltl.shipment',
            'res_id': shipment.id,
            'view_mode': 'form',
            'target': 'current',
        }
