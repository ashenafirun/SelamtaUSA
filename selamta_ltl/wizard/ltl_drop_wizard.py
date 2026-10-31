# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class LtlDropWizard(models.TransientModel):
    """Put delivery orders on one LTL shipment, saying where the truck delivers when they
    are not all going to the same address (one customer receiving for another, or two
    customers next to each other). Also used to add deliveries to an existing shipment."""
    _name = 'selamta.ltl.drop.wizard'
    _description = 'LTL shipment: deliveries and drop location'

    shipment_id = fields.Many2one('selamta.ltl.shipment', 'Add to shipment')
    picking_ids = fields.Many2many(
        'stock.picking', string='Delivery orders',
        domain=[('picking_type_code', '=', 'outgoing'), ('state', '!=', 'cancel'),
                ('ltl_shipment_id', '=', False)])
    address_ids = fields.Many2many(
        'res.partner', compute='_compute_address_ids', string='Delivery addresses')
    partner_id = fields.Many2one(
        'res.partner', 'Truck delivers to',
        help='Where the carrier drops the whole load. The other customers\' orders are '
             'received there; the BOL lists which pallets are for which customer.')
    different_addresses = fields.Boolean(compute='_compute_address_ids')

    @api.depends('picking_ids.partner_id', 'shipment_id.partner_id')
    def _compute_address_ids(self):
        Shipment = self.env['selamta.ltl.shipment']
        for wizard in self:
            partners = wizard.picking_ids.mapped('partner_id') | wizard.shipment_id.partner_id
            wizard.address_ids = partners
            wizard.different_addresses = Shipment._needs_drop_choice(
                wizard.picking_ids, wizard.shipment_id or None)

    @api.onchange('picking_ids', 'shipment_id')
    def _onchange_default_partner(self):
        if not self.partner_id:
            self.partner_id = self.shipment_id.partner_id or self.picking_ids[:1].partner_id

    def action_confirm(self):
        self.ensure_one()
        if not self.picking_ids:
            raise UserError(_('Choose at least one delivery order.'))
        Shipment = self.env['selamta.ltl.shipment']
        consignee = self.partner_id if self.different_addresses else None
        if self.different_addresses and not self.partner_id:
            raise UserError(_('Choose where the truck delivers.'))
        if self.shipment_id:
            shipment = self.shipment_id._add_pickings(self.picking_ids, consignee)
        else:
            shipment = Shipment._create_from_pickings(self.picking_ids, consignee)
        return {
            'type': 'ir.actions.act_window',
            'name': _('LTL shipment'),
            'res_model': 'selamta.ltl.shipment',
            'res_id': shipment.id,
            'view_mode': 'form',
            'target': 'current',
        }
