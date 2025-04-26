# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2018-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>:wink:
# See LICENSE file for full copyright and licensing details.
#################################################################################
from odoo import api, fields, models,_
from odoo.http import request
import logging
_log = logging.getLogger(__name__)
class SaleOrderLine(models.Model):
	_inherit = 'sale.order.line'


	def get_subtotal_cart(self, line):
		if line:
			self_obj = self.browse(line)
			# price = self_obj.price_unit
			# quantity = self_obj.product_uom_qty
			# return price*quantity
			return self_obj.price_subtotal

	def get_subtotal_deleted(self, line):
		if line:
			
			price = line.product_id.lst_price
			quantity = line.product_uom_qty
			return price*quantity


class SaleOrder(models.Model):
	_inherit = 'sale.order'

	def get_show_subtotal(self):

		
		ir_default = self.env['website'].sudo().get_current_website().sub_total
		return True if ir_default == None else ir_default
	def get_minimun_cart_value(self):
		ir_default = self.env['website'].get_current_website().c_id._convert(
                    self.env['website'].get_current_website().minimum_order_value, request.env['website'].get_current_website().pricelist_id.currency_id, self.env.user.company_id,
                    fields.Date.today()
                    )		
		return 1 if ir_default == None else round(ir_default, 2)
	

	def get_minimum_quantity_value(self):
		ir_default = self.env['website'].get_current_website().minimum_product_quantity
		return 1 if ir_default == None else ir_default
	

	def get_max_quantity_value(self):
		ir_default = self.env['website'].get_current_website().max_product_quantity
		return 1 if ir_default == None else ir_default
	
	def get_particuler_min_max_value(self,id):
		product_id = request.env["product.product"].sudo().browse(int(id))		
		return 1 if product_id == None else product_id.product_tmpl_id
	
	def get_particuler_min_value_varient(self,id):
		product_id = request.env["product.product"].sudo().browse(int(id))
		return 1 if product_id.minimum_product_quantity == None else product_id.minimum_product_quantity
	
	def get_particuler_max_value_varient(self,id):
		product_id = request.env["product.product"].sudo().browse(int(id))
		return 1 if product_id.max_product_quantity == None else product_id.max_product_quantity
	
	def get_current_varient(self,id):
		count_varient = 0
		product_id = request.env["product.product"].sudo().browse(int(id))
		attribute_line_ids = product_id.product_tmpl_id.attribute_line_ids
		if len(attribute_line_ids)!=0:
			varients_id = product_id.product_tmpl_id.product_variant_ids
			count_varient = len(varients_id)
		return 1 if count_varient == None else count_varient
	

	def get_particuler_enable_limit(self,id):
		product_id = request.env["product.product"].sudo().browse(int(id))
		return 1 if product_id.check_box == None else product_id.check_box
	
	def get_particuler_enable_limit_template(self,id):
		product_id = request.env["product.product"].sudo().browse(int(id))		
		return 1 if product_id == None else product_id.product_tmpl_id
	@api.model
	def _get_errors(self, order):
		
		minimum_order_value =1 if self.env['website'].sudo().get_current_website().minimum_order_value == None else self.env['website'].sudo().get_current_website().c_id._convert(
                    self.env['website'].sudo().get_current_website().minimum_order_value, self.env['website'].sudo()._get_current_pricelist().currency_id, self.env.user.company_id,
                    fields.Date.today()
                    )
		minimum_order_value = round(minimum_order_value,2)
		errors = []
		if order and order.amount_total < minimum_order_value:
			errors.append(['Invalid Cart Value',_("A minimum purchase total of") + order.currency_id.symbol + minimum_order_value + _("is required to confirm your order, current purchase total is") + order.currency_id.symbol + order.amount_total])
			pass
		return errors
