# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ltl_shipment_id = fields.Many2one(
        'selamta.ltl.shipment', 'LTL shipment', copy=False, index=True, ondelete='set null')

    @api.depends('origin')
    @api.depends_context('ltl_show_order')
    def _compute_display_name(self):
        """On a shipment's pallet lines, show the sales order with the delivery
        ('S01234 (WH/OUT/05678)') so staff pick the order they know."""
        super()._compute_display_name()
        if self.env.context.get('ltl_show_order'):
            for picking in self.filtered('origin'):
                picking.display_name = '%s (%s)' % (picking.origin, picking.name)

    def action_ltl_shipment(self):
        """Open this delivery's LTL shipment, creating it the first time.

        With several deliveries selected they go on one shipment (one BOL, one PRO). If they
        go to different addresses, ask where the truck delivers first. If one of them is
        already on a shipment, the others join it."""
        pickings = self.filtered(lambda p: p.state != 'cancel')
        shipment = pickings.ltl_shipment_id
        Shipment = self.env['selamta.ltl.shipment']
        if len(shipment) == 1 and not pickings.filtered(lambda p: not p.ltl_shipment_id):
            return shipment._open_form()
        if len(shipment) <= 1 and Shipment._needs_drop_choice(pickings, shipment or None):
            wizard = self.env['selamta.ltl.drop.wizard'].create({
                'shipment_id': shipment.id or False,
                'picking_ids': [(6, 0, pickings.filtered(lambda p: not p.ltl_shipment_id).ids)],
                'partner_id': (shipment.partner_id or pickings[:1].partner_id).id,
            })
            return {
                'type': 'ir.actions.act_window',
                'name': _('Where does the truck deliver?'),
                'res_model': 'selamta.ltl.drop.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }
        shipment = Shipment._create_from_pickings(pickings)
        return shipment._open_form()

