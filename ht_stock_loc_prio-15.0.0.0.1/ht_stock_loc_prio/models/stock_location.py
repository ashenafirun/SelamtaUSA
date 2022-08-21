# -*- coding: utf-8 -*-
##############################################################################
#
#    Harhu IT Solutions
#    Copyright (C) 2019-TODAY Harhu IT Solutions(<http://www.harhutech.com>).
#    Author: Harhu IT Solutions(<http://www.harhutech.com>)
#    you can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    It is forbidden to publish, distribute, sublicense, or sell copies
#    of the Software or modified copies of the Software.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    GENERAL PUBLIC LICENSE (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


from odoo.exceptions import UserError, ValidationError

import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare, float_round
from odoo.tools.float_utils import float_repr
from odoo.tools.misc import format_date

class SaleOrderLine(models.Model):
    
    _inherit = 'sale.order.line'

    def get_all_procurements(self, procurements,qty,line,values,procurement_uom):
        all_stock_location = self.env['stock.location'].search([
            ('usage','=','internal'),('priority','!=',False)])
        product_qty = qty
        for location in all_stock_location:
            stock_qty =line.product_id.with_context(compute_child=False,location=location.id).free_qty
            if stock_qty >= product_qty:
                procurements.append(self.env['procurement.group'].Procurement(
                    line.product_id, product_qty, procurement_uom,
                    line.order_id.partner_shipping_id.property_stock_customer,
                    line.name, line.order_id.name, line.order_id.company_id, values))
                product_qty = 0
                break
            elif stock_qty > 0:
                product_qty = product_qty - stock_qty
                procurements.append(self.env['procurement.group'].Procurement(
                    line.product_id, stock_qty, procurement_uom,
                    line.order_id.partner_shipping_id.property_stock_customer,
                    line.name, line.order_id.name, line.order_id.company_id, values))
        if product_qty >0:
            procurements.append(self.env['procurement.group'].Procurement(
                line.product_id, product_qty, procurement_uom,
                line.order_id.partner_shipping_id.property_stock_customer,
                line.name, line.order_id.name, line.order_id.company_id, values))
            
                
        return procurements
            
    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
        Launch procurement group run method with required/custom fields genrated by a
        sale order line. procurement group will launch '_run_pull', '_run_buy' or '_run_manufacture'
        depending on the sale order line product rule.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        procurements = []
        for line in self:
            line = line.with_company(line.company_id)
            if line.state != 'sale' or not line.product_id.type in ('consu','product'):
                continue
            qty = line._get_qty_procurement(previous_product_uom_qty)
            if float_compare(qty, line.product_uom_qty, precision_digits=precision) >= 0:
                continue

            group_id = line._get_procurement_group()
            if not group_id:
                group_id = self.env['procurement.group'].create(line._prepare_procurement_group_vals())
                line.order_id.procurement_group_id = group_id
            else:
                # In case the procurement group is already created and the order was
                # cancelled, we need to update certain values of the group.
                updated_vals = {}
                if group_id.partner_id != line.order_id.partner_shipping_id:
                    updated_vals.update({'partner_id': line.order_id.partner_shipping_id.id})
                if group_id.move_type != line.order_id.picking_policy:
                    updated_vals.update({'move_type': line.order_id.picking_policy})
                if updated_vals:
                    group_id.write(updated_vals)

            values = line._prepare_procurement_values(group_id=group_id)
            product_qty = line.product_uom_qty - qty

            line_uom = line.product_uom
            quant_uom = line.product_id.uom_id
            product_qty, procurement_uom = line_uom._adjust_uom_quantities(product_qty, quant_uom)
            procurements = self.get_all_procurements(procurements,product_qty,line,values,procurement_uom)
#             procurements.append(self.env['procurement.group'].Procurement(
#                 line.product_id, product_qty, procurement_uom,
#                 line.order_id.partner_shipping_id.property_stock_customer,
#                 line.name, line.order_id.name, line.order_id.company_id, values))
        if procurements:
            self.env['procurement.group'].run(procurements)
        return True

class StockMove(models.Model):

    _inherit = 'stock.move'

    is_not_need_to_merge = fields.Boolean(copy=False,default=False)
    
    def _merge_moves(self, merge_into=False):
        if any(self.filtered(lambda x:x.is_not_need_to_merge)):
            return self
        else:
            return super(StockMove,self)._merge_moves(merge_into=merge_into)
    
    def _action_confirm(self,merge=True, merge_into=False):
        res = super(StockMove,self)._action_confirm(merge=merge, merge_into=merge_into)
        if any(self.filtered(lambda x:x.is_not_need_to_merge)):
            all_product_qty_ids = self.env['stock.location.product.quantity.set'].search([])
            all_product_qty_ids.unlink()
        return res
    
    def _search_picking_for_assignation(self):
        self.ensure_one()
        if self.is_not_need_to_merge:
            picking = self.env['stock.picking'].search([
                    ('group_id', '=', self.group_id.id),
                    ('location_dest_id', '=', self.location_dest_id.id),
                    ('picking_type_id', '=', self.picking_type_id.id),
                    ('printed', '=', False),
                    ('immediate_transfer', '=', False),
                    ('state', 'in', ['draft', 'confirmed', 'waiting', 'partially_available', 'assigned'])], limit=1)
            return picking
            
        else:
            return super(StockMove,self)._search_picking_for_assignation()
                
class StockLocation(models.Model):

    _inherit = 'stock.location'
    _order = 'priority asc'

    priority = fields.Integer(string="Priority")
    location_set_qty = fields.Float(copy=False,default=0)
    
class StockQuant(models.Model):

    _inherit = 'stock.quant'
    _order = 'priority asc'

    priority = fields.Integer(string="Priority", related='location_id.priority', store=True)
    
    @api.model
    def _get_removal_strategy_order(self, removal_strategy):
        if removal_strategy == 'fifo':
            return 'in_date ASC, priority'
        elif removal_strategy == 'lifo':
            return 'in_date DESC, priority DESC'
        elif removal_strategy == 'closest':
            return 'location_id ASC, priority DESC'
        raise UserError(_('Removal strategy %s not implemented.') % (removal_strategy,))

class StockRule(models.Model):

    _inherit = 'stock.rule'

    def create_stock_location_product_history(self,product_id,location,stock_qty):
        self.env['stock.location.product.quantity.set'].create({'product_id':product_id.id,'location_id':location.id,'qty':stock_qty})
        
    def get_priority_location(self, vals):
        all_stock_location = self.env['stock.location'].search([
            ('usage','=','internal'),('priority','!=',False)])
        for location in all_stock_location:
            if vals.get('product_id',False):
                product_id = self.env['product.product'].browse(vals.get('product_id'))
                stock_qty =product_id.with_context(compute_child=False,location=location.id).free_qty
                location_set_qty = 0
                loc_product_ids = self.env['stock.location.product.quantity.set'].search([('product_id','=',product_id.id),('location_id','=',location.id)])
                location_set_qty = sum(x.qty for x in loc_product_ids)
                stock_qty = stock_qty - location_set_qty
                if stock_qty >= vals.get('product_uom_qty',0):
                    vals.update({'location_id':location.id})
                    self.create_stock_location_product_history(product_id,location,vals.get('product_uom_qty',0))
                    break
                elif stock_qty > 0:
                    vals.update({'location_id':location.id})
                    self.create_stock_location_product_history(product_id,location,stock_qty)
                    break
                    
        return vals
    
    
    def _get_stock_move_values(self, product_id, product_qty, product_uom, location_id, name, origin, company_id, values):
        move_vals = super(StockRule,self)._get_stock_move_values(product_id, product_qty, product_uom, location_id, name, origin, company_id, values)
        if move_vals.get('sale_line_id',False):
            move_vals.update({'is_not_need_to_merge':True})
            move_vals = self.get_priority_location(move_vals)
        return move_vals
     
    
class StockLocationProductQuantitySet(models.Model):
    
    _name = 'stock.location.product.quantity.set'
    
    product_id = fields.Many2one('product.product','Product')
    location_id = fields.Many2one('stock.location','Location')
    qty = fields.Float("Quantity")
    
    
