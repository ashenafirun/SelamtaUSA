# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2018-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>:wink:
# See LICENSE file for full copyright and licensing details.
#################################################################################
from odoo import api, fields, models
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)


class AdvancedWebsiteSettings(models.TransientModel):
	_name = 'advance.website.settings'
	_description = 'Website Cart Settings'

	def execute_settings(self):
		
		website_id = self.website_id
		# redirect_to_cart = self.redirect_to_cart		
		sub_total = self.sub_total
		minimum_order_value = self.minimum_order_value
		c_id = self.c_id

		website_id.write({
			# 'redirect_to_cart' : redirect_to_cart,			
			'sub_total' : sub_total,				
			'minimum_order_value' : minimum_order_value,			
			'c_id' : c_id.id
			
		})

		return 'ir.act.window.close'
		
	website_id = fields.Many2one('website',string='Website')
	add_to_cart_action = fields.Selection(related='website_id.add_to_cart_action', readonly=False)
	sub_total = fields.Boolean(string = 'Show Subtotal',related='website_id.sub_total',readonly=False)
	reference_number = fields.Boolean(string="Reference Number", related='website_id.reference_number',readonly=False)
	minimum_order_value = fields.Float(string = 'Minimum Cart Value To Validate Order',related='website_id.minimum_order_value',readonly=False)
	minimum_product_quantity = fields.Integer(string="Minimum Product Quantity",related="website_id.minimum_product_quantity",readonly=False,default=-1)
	max_product_quantity = fields.Integer(string="Maxmium Product Quantity",related="website_id.max_product_quantity",readonly=False,default=-1)
	c_id = fields.Many2one('res.currency', 'Cart Currency',default=lambda self: self.env.user.company_id.currency_id.id,required=True,related='website_id.c_id',readonly=False)


	@api.model_create_multi
	def create(self,vals):
		for val in vals:
			rec = super(AdvancedWebsiteSettings,self).create(val)
			if val["minimum_product_quantity"] or val["max_product_quantity"]:
				if (val["minimum_product_quantity"] > val["max_product_quantity"])  and val["max_product_quantity"] != -1:
					raise ValidationError("Maximum product quantity should be more than minimum product qunatity")
				elif val["minimum_product_quantity"] < -1 or val["max_product_quantity"] < -1:
						raise ValidationError(" Value must be greater then -2")
			if val["minimum_product_quantity"]==0 or val["max_product_quantity"]==0:
				raise ValidationError("Product quantity should not be zero.")
		return rec

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_translation_frontend_modules_name(cls):
        modules = super()._get_translation_frontend_modules_name()
        return modules + ['advance_website_settings']