# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, RedirectWarning, ValidationError
from markupsafe import Markup


class OrderMerge(models.TransientModel):
    _name = 'order.merge'
    _description = 'Merge Sale orders'

    @api.model
    def default_get(self, fields):
        rec = super(OrderMerge, self).default_get(fields)
        context = dict(self._context or {})
        active_ids = context.get('active_ids')

        if active_ids:
            sales = self.env['sale.order'].browse(active_ids)

            if any(sale.state == 'done' for sale in sales):
                raise UserError('You can not merge done orders.')
            if any(sale.state != 'draft' for sale in sales):
                raise UserError('You can only merge draft orders.')

            sale_ids = [sale.id for sale in sales if sale.state in 'draft']

            if 'order_to_merge' in fields and sale_ids:
                rec.update({'order_to_merge': [(6, 0, sale_ids)]})
        return rec

    order_to_merge = fields.Many2many(
        'sale.order', 'rel_sale_to_merge', 'sale_id', 'to_merge_id',
        'Orders to merge', domain=[('state', '!=', 'done')])
    type = fields.Selection(
        [('new', 'New Order and Cancel Selected'), ('exist', 'New order and Delete all selected order'),
         ('exist_1', 'Merge order on existing selected order and cancel others'),
         ('exist_2', 'Merge order on existing selected order and delete others')], 'Merge Type', default='new',
        required=True)
    order = fields.Many2one('sale.order', string='Merge with')

    def merge(self):
        sale_obj = self.env['sale.order']
        line_obj = self.env['sale.order.line']
        sales = sale_obj.browse(self._context.get('active_ids', []))
        partners_list = []
        partners_list_write = []
        line_list = []
        cancel_list = []
        copy_list = []
        vals = {}
        customer_ref = []
        partner_name = False
        myString = ''

        if len(sales) < 2:
            raise UserError('Please select multiple orders to merge in the list view.')

        if any(sale.state in ['done', 'sale', 'confirmed', 'cancel'] for sale in sales):
            raise UserError('You can not merge Done and Sale order orders.')

        for sale in sales:
            if sale.client_order_ref:
                customer_ref.append(sale.client_order_ref)
                if len(customer_ref) > 1:
                    myString = ",".join(customer_ref)
                else:
                    myString = customer_ref[0]

        msg_origin = ""
        origin_list = []

        for sale in sales:
            origin_list.append(sale.name)

        for i in range(len(origin_list)):
            if i == len(origin_list) - 1:
                msg_origin = msg_origin + origin_list[i] + "."
            else:
                msg_origin = msg_origin + origin_list[i] + ","

        if self.order:
            self.order.write({'client_order_ref': myString})

        if self.type == 'new':

            partner_name = sales and sales[0].partner_id.id
            new_sale = sale_obj.create({'partner_id': partner_name, 'client_order_ref': myString, 'origin': msg_origin})
            id_list = []
            for sale in sales:

                partners_list.append(sale.partner_id)
                if not partners_list[1:] == partners_list[:-1]:
                    raise UserError('You can only merge orders of same partners.')

                else:
                    cancel_list.append(sale)
                    merge_ids = line_obj.search([('order_id', '=', sale.id)])

                    for line in merge_ids:
                        if new_sale.order_line:
                            required_line = new_sale.order_line.search(
                                [('product_id', '=', line.product_id.id), ('order_id', '=', new_sale.id)], limit=1)
                            if required_line:
                                required_line.update({
                                    'product_uom_qty': required_line.product_uom_qty + line.product_uom_qty,
                                    'price_unit': line.price_unit,
                                })
                                for rec in line.tax_id.ids:
                                    required_line.update({'tax_id': [(4, rec)]})
                            else:
                                vals = {
                                    'product_id': line.product_id.id or False,
                                    'product_uom_qty': line.product_uom_qty or False,
                                    'price_unit': line.price_unit or False,
                                    'tax_id': [(6, 0, [tax.id for tax in line.tax_id if line.tax_id])] or False,
                                    'order_id': new_sale.id,
                                }
                                line_obj.create(vals)
                        else:
                            vals = {
                                'product_id': line.product_id.id or False,
                                'product_uom_qty': line.product_uom_qty or False,
                                'price_unit': line.price_unit or False,
                                'tax_id': [(6, 0, [tax.id for tax in line.tax_id if line.tax_id])] or False,
                                'order_id': new_sale.id,
                            }
                            line_obj.create(vals)

            msg_body = Markup(_(f"This sale order has been created from: <b>{msg_origin}</b>"))
            new_sale.message_post(body=msg_body)
            for orders in cancel_list:
                orders.action_cancel()

        if self.type == 'exist':
            partner_name = sales and sales[0].partner_id.id
            new_sale = sale_obj.create({'partner_id': partner_name, 'client_order_ref': myString, 'origin': msg_origin})
            for sale in sales:

                partners_list_write.append(sale.partner_id)

                if not partners_list_write[1:] == partners_list_write[:-1]:
                    raise UserError('You can only merge orders of same partners.')

                else:
                    cancel_list.append(sale.id)
                    merge_ids = line_obj.search([('order_id', '=', sale.id)])
                    for line in merge_ids:
                        if new_sale.order_line:
                            required_line = new_sale.order_line.search(
                                [('product_id', '=', line.product_id.id), ('order_id', '=', new_sale.id)], limit=1)
                            if required_line:
                                required_line.update({
                                    'price_unit': line.price_unit,
                                    'product_uom_qty': required_line.product_uom_qty + line.product_uom_qty
                                })
                                for rec in line.tax_id.ids:
                                    required_line.update({'tax_id': [(4, rec)]})
                            else:
                                vals = {
                                    'product_id': line.product_id.id or False,
                                    'product_uom_qty': line.product_uom_qty or False,
                                    'price_unit': line.price_unit or False,
                                    'tax_id': [(6, 0, [tax.id for tax in line.tax_id if line.tax_id])] or False,
                                    'order_id': new_sale.id,
                                }
                                line_obj.create(vals)


                        else:
                            vals = {
                                'product_id': line.product_id.id or False,
                                'product_uom_qty': line.product_uom_qty or False,
                                'price_unit': line.price_unit or False,
                                'tax_id': [(6, 0, [tax.id for tax in line.tax_id if line.tax_id])] or False,
                                'order_id': new_sale.id,
                            }
                            line_obj.create(vals)

            msg_body = Markup(_(f"This sale order has been created from: <b>{msg_origin}</b>"))
            new_sale.message_post(body=msg_body)

            for orders in cancel_list:
                for s_order in self.env['sale.order'].browse(orders):
                    s_order.action_cancel()
                    s_order.unlink()

        if self.type == 'exist_1':
            for sale in sales:
                partners_list_write.append(sale.partner_id)
                if self.order.state != 'draft':
                    raise UserError('You can only merge order into draft quotation.')

                new_sale = self.order
                if not partners_list_write[1:] == partners_list_write[:-1]:
                    raise UserError('You can only merge orders of same partners.')

                else:
                    partner_name = sale.partner_id.id
                    cancel_list.append(sale.id)
                    merge_ids = line_obj.search([('order_id', '=', sale.id)])
                    if self.order == sale:
                        continue
                    else:
                        for line in merge_ids:
                            if self.order.order_line:
                                required_line = self.order.order_line.search(
                                    [('product_id', '=', line.product_id.id), ('order_id', '=', self.order.id)],
                                    limit=1)
                                if required_line:
                                    required_line.update({
                                        'price_unit': line.price_unit,
                                        'product_uom_qty': required_line.product_uom_qty + line.product_uom_qty
                                    })
                                    for rec in line.tax_id.ids:
                                        required_line.update({'tax_id': [(4, rec)]})
                                else:
                                    line.write({'order_id': self.order.id})

                            else:
                                line.write({'order_id': self.order.id})

            msg_body = Markup(_(f"This sale order has been created from: <b>{msg_origin}</b>"))
            self.order.message_post(body=msg_body)
            self.order.origin = msg_origin

            if self.order.id in cancel_list:
                cancel_list.remove(self.order.id)
            for orders in cancel_list:
                for s_order in self.env['sale.order'].browse(orders):
                    s_order.action_cancel()
            return True
        if self.type == 'exist_2':

            for sale in sales:

                partners_list_write.append(sale.partner_id)
                if self.order.state != 'draft':
                    raise UserError('You can only merge order into draft quotation.')
                new_sale = self.order
                if not partners_list_write[1:] == partners_list_write[:-1]:
                    raise UserError('You can only merge orders of same partners.')

                else:
                    if self.order.state in ['done', 'sale', 'confirmed', 'cancel']:
                        raise UserError('You can not merge oredrs with Done, Cancel and Sale order orders.')
                    partner_name = sale.partner_id.id
                    cancel_list.append(sale.id)
                    merge_ids = line_obj.search([('order_id', '=', sale.id)])
                    if self.order == sale:
                        continue
                    else:
                        for line in merge_ids:
                            if self.order.order_line:
                                required_line = self.order.order_line.search(
                                    [('product_id', '=', line.product_id.id), ('order_id', '=', self.order.id)],
                                    limit=1)
                                if required_line:
                                    required_line.update({
                                        'price_unit': line.price_unit,
                                        'product_uom_qty': required_line.product_uom_qty + line.product_uom_qty
                                    })
                                    for rec in line.tax_id.ids:
                                        required_line.update({'tax_id': [(4, rec)]})
                                else:
                                    line.write({'order_id': self.order.id})

                            else:
                                line.write({'order_id': self.order.id})

            msg_body = Markup(_(f"This sale order has been created from: <b>{msg_origin}</b>"))
            self.order.message_post(body=msg_body)
            self.order.origin = msg_origin

            if self.order.id in cancel_list:
                cancel_list.remove(self.order.id)
            for orders in cancel_list:
                for s_order in self.env['sale.order'].browse(orders):
                    s_order.action_cancel()
                    s_order.unlink()
            return True
        result = {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': new_sale.id,
            'views': [(False, 'form')],
        }
        return result


class PurchaseOrdersMerge(models.TransientModel):
    _name = 'purchase.order.merge'
    _description = 'Merge Purchase orders'

    @api.model
    def default_get(self, fields):
        rec = super(PurchaseOrdersMerge, self).default_get(fields)
        context = dict(self._context or {})
        active_model = context.get('active_model')
        active_ids = context.get('active_ids')

        if active_ids:
            purchase_ids = []
            purchases = self.env['purchase.order'].browse(active_ids)

            if any(pur.state == 'done' for pur in purchases):
                raise UserError('You can not merge done orders.')
            if any(pur.state != 'draft' for pur in purchases):
                raise UserError('You can only merge draft orders.')

            purchase_ids = [pur.id for pur in purchases if pur.state in 'draft']

            if 'purchase_order_to_merge_ids' in fields and purchase_ids:
                rec.update({'purchase_order_to_merge_ids': [(6, 0, purchase_ids)]})
        return rec

    purchase_order = fields.Many2one(
        'purchase.order', 'Merge into')
    purchase_order_to_merge_ids = fields.Many2many(
        'purchase.order', 'rel_purchase_to_merge_order', 'purchase_id', 'to_merge_id',
        string='Orders to merge', domain=[('state', '!=', 'done')])
    type = fields.Selection(
        [('new', 'New Order and Cancel Selected'), ('exist', 'New order and Delete all selected order'),
         ('exist_1', 'Merge order on existing selected order and cancel others'),
         ('exist_2', 'Merge order on existing selected order and delete others')], 'Merge Type', default='new',
        required=True)

    def merge_purchase(self):
        purchase_obj = self.env['purchase.order']
        mod_obj = self.env['ir.model.data']
        line_obj = self.env['purchase.order.line']
        # form_view_id = mod_obj.xmlid_to_res_id('purchase.purchase_order_form')
        purchases = purchase_obj.browse(self._context.get('active_ids', []))
        partners_list = []
        partners_list_write = []
        line_list = []
        cancel_list = []
        copy_list = []
        vendor_ref = []
        myString = ''

        if len(purchases) < 2:
            raise UserError('Please select multiple orders to merge in the list view.')

        if any(pur.state in ['done', 'purchase', 'cancel'] for pur in purchases):
            raise UserError('You can not merge this order with existing state.')
        for pur in purchases:
            if pur.partner_ref:
                vendor_ref.append(pur.partner_ref)
                if len(vendor_ref) > 1:
                    myString = ",".join(vendor_ref)
                else:
                    myString = vendor_ref[0]

        msg_origin = ""
        origin_list = []

        for pur in purchases:
            origin_list.append(pur.name)

        for i in range(len(origin_list)):
            if i == len(origin_list) - 1:
                msg_origin = msg_origin + origin_list[i] + "."
            else:
                msg_origin = msg_origin + origin_list[i] + ","

        if self.purchase_order:
            self.purchase_order.write({'partner_ref': myString})
        if self.type == 'new':

            partner_name = purchases and purchases[0].partner_id.id
            new_purchase = purchase_obj.create({'partner_id': partner_name, 'partner_ref': myString})
            for pur in purchases:

                partners_list.append(pur.partner_id)

                if not partners_list[1:] == partners_list[:-1]:
                    raise UserError('You can only merge orders of same partners.')

                else:
                    cancel_list.append(pur)
                    merge_ids = line_obj.search([('order_id', '=', pur.id)])
                    for line in merge_ids:
                        if new_purchase.order_line:
                            required_line = new_purchase.order_line.search(
                                [('product_id', '=', line.product_id.id), ('order_id', '=', new_purchase.id)], limit=1)
                            if required_line:
                                required_line.update({'product_qty': required_line.product_qty + line.product_qty})
                                for rec in line.taxes_id.ids:
                                    required_line.update({'taxes_id': [(4, rec)]})
                            else:
                                vals = {
                                    'date_planned': line.date_planned or False,
                                    'name': line.product_id.name or False,
                                    'product_id': line.product_id.id or False,
                                    'product_qty': line.product_qty or False,
                                    'product_uom': line.product_uom.id or False,
                                    'price_unit': line.price_unit or False,
                                    'taxes_id': [(6, 0, [tax.id for tax in line.taxes_id if line.taxes_id])] or False,
                                    'order_id': new_purchase.id,
                                }
                                line_obj.create(vals)


                        else:
                            vals = {
                                'date_planned': line.date_planned or False,
                                'name': line.product_id.name or False,
                                'product_id': line.product_id.id or False,
                                'product_qty': line.product_qty or False,
                                'product_uom': line.product_uom.id or False,
                                'price_unit': line.price_unit or False,
                                'taxes_id': [(6, 0, [tax.id for tax in line.taxes_id if line.taxes_id])] or False,
                                'order_id': new_purchase.id,
                            }
                            line_obj.create(vals)

            msg_body = Markup(_(f"This purchase order has been created from: <b>{msg_origin}</b>"))
            new_purchase.message_post(body=msg_body)

            for orders in cancel_list:
                orders.button_cancel()

        if self.type == 'exist':

            partner_name = purchases and purchases[0].partner_id.id
            new_purchase = purchase_obj.create({'partner_id': partner_name, 'partner_ref': myString})

            for pur in purchases:

                partners_list_write.append(pur.partner_id)

                if not partners_list_write[1:] == partners_list_write[:-1]:
                    raise UserError('You can only merge orders of same partners.')

                else:
                    partner_name = pur.partner_id.id
                    cancel_list.append(pur.id)
                    merge_ids = line_obj.search([('order_id', '=', pur.id)])
                    for line in merge_ids:
                        if new_purchase.order_line:
                            required_line = new_purchase.order_line.search(
                                [('product_id', '=', line.product_id.id), ('order_id', '=', new_purchase.id)], limit=1)
                            if required_line:
                                required_line.update({'product_qty': required_line.product_qty + line.product_qty})
                                for rec in line.taxes_id.ids:
                                    required_line.update({'taxes_id': [(4, rec)]})
                            else:
                                vals = {
                                    'date_planned': line.date_planned or False,
                                    'name': line.product_id.name or False,
                                    'product_id': line.product_id.id or False,
                                    'product_qty': line.product_qty or False,
                                    'product_uom': line.product_uom.id or False,
                                    'price_unit': line.price_unit or False,
                                    'taxes_id': [(6, 0, [tax.id for tax in line.taxes_id if line.taxes_id])] or False,
                                    'order_id': new_purchase.id,
                                }
                                line_obj.create(vals)

                        else:
                            vals = {
                                'date_planned': line.date_planned or False,
                                'name': line.product_id.name or False,
                                'product_id': line.product_id.id or False,
                                'product_qty': line.product_qty or False,
                                'product_uom': line.product_uom.id or False,
                                'price_unit': line.price_unit or False,
                                'taxes_id': [(6, 0, [tax.id for tax in line.taxes_id if line.taxes_id])] or False,
                                'order_id': new_purchase.id,
                            }
                            line_obj.create(vals)

            msg_body = Markup(_(f"This purchase order has been created from: <b>{msg_origin}</b>"))
            new_purchase.message_post(body=msg_body)
            for orders in cancel_list:
                for p_order in self.env['purchase.order'].browse(orders):
                    p_order.button_cancel()
                    p_order.unlink()

        if self.type == 'exist_1':
            for pur in purchases:

                partners_list_write.append(pur.partner_id)
                if self.purchase_order.state != 'draft':
                    raise UserError('You can only merge order into draft quotation.')
                new_purchase = self.purchase_order

                if not partners_list_write[1:] == partners_list_write[:-1]:
                    raise UserError('You can only merge orders of same partners.')

                else:
                    partner_name = pur.partner_id.id
                    cancel_list.append(pur.id)
                    merge_ids = line_obj.search([('order_id', '=', pur.id)])
                    if self.purchase_order == pur:
                        continue
                    else:
                        for line in merge_ids:
                            if self.purchase_order.order_line:
                                required_line = self.purchase_order.order_line.search(
                                    [('product_id', '=', line.product_id.id),
                                     ('order_id', '=', self.purchase_order.id)], limit=1)
                                if required_line:
                                    required_line.update({'product_qty': required_line.product_qty + line.product_qty})
                                    for rec in line.taxes_id.ids:
                                        required_line.update({'taxes_id': [(4, rec)]})
                                else:
                                    line.write({'order_id': self.purchase_order.id})

                            else:
                                line.write({'order_id': self.purchase_order.id})

            msg_body = Markup(_(f"This purchase order has been created from: <b>{msg_origin}</b>"))
            self.purchase_order.message_post(body=msg_body)

            if self.purchase_order.id in cancel_list:
                cancel_list.remove(self.purchase_order.id)
            for orders in cancel_list:
                for s_order in self.env['purchase.order'].browse(orders):
                    s_order.button_cancel()
            return True
        if self.type == 'exist_2':

            for pur in purchases:

                partners_list_write.append(pur.partner_id)
                if self.purchase_order.state != 'draft':
                    raise UserError('You can only merge order into draft quotation.')
                new_purchase = self.purchase_order

                if not partners_list_write[1:] == partners_list_write[:-1]:
                    raise UserError('You can only merge orders of same partners.')

                else:
                    partner_name = pur.partner_id.id
                    cancel_list.append(pur.id)
                    merge_ids = line_obj.search([('order_id', '=', pur.id)])
                    if self.purchase_order == pur:
                        continue
                    else:
                        for line in merge_ids:
                            if self.purchase_order.order_line:
                                required_line = self.purchase_order.order_line.search(
                                    [('product_id', '=', line.product_id.id),
                                     ('order_id', '=', self.purchase_order.id)], limit=1)
                                if required_line:
                                    required_line.update({'product_qty': required_line.product_qty + line.product_qty})
                                    for rec in line.taxes_id.ids:
                                        required_line.update({'taxes_id': [(4, rec)]})
                                else:
                                    line.write({'order_id': self.purchase_order.id})

                            else:
                                line.write({'order_id': self.purchase_order.id})

            msg_body = Markup(_(f"This purchase order has been created from: <b>{msg_origin}</b>"))
            self.purchase_order.message_post(body=msg_body)

            if self.purchase_order.id in cancel_list:
                cancel_list.remove(self.purchase_order.id)
            for orders in cancel_list:
                for p_order in self.env['purchase.order'].browse(orders):
                    p_order.button_cancel()
                    p_order.unlink()
            return True

        result = {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'view_type': 'form',
            'res_id': new_purchase.id,
            'views': [(False, 'form')],
        }

        return result
