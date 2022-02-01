# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2018-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>:wink:
# See LICENSE file for full copyright and licensing details.
#################################################################################
from odoo import api, fields, models
from odoo import tools
import logging
_logger = logging.getLogger(__name__)


class AdvancedWebsiteSettings(models.TransientModel):
	_name = 'advance.website.settings'
	_description = 'Website Cart Settings'

	def execute_settings(self):
		
		website_id = self.website_id
		redirect_to_cart = self.redirect_to_cart		
		sub_total = self.sub_total
		minimum_order_value = self.minimum_order_value
		c_id = self.c_id

		website_id.write({
			'redirect_to_cart' : redirect_to_cart,			
			'sub_total' : sub_total,				
			'minimum_order_value' : minimum_order_value,			
			'c_id' : c_id.id
			

		})

		return 'ir.act.window.close'
		
	website_id = fields.Many2one('website',string='Website')
	redirect_to_cart =  fields.Selection([('same','Product Page'),('cart','Cart Summary'),('previous_page','Same Page')], string='Redirect page after adding to cart',related='website_id.redirect_to_cart',readonly=False)
	sub_total = fields.Boolean(string = 'Show Subtotal',related='website_id.sub_total',readonly=False)
	minimum_order_value = fields.Float(string = 'Minimum Cart Value To Validate Order',related='website_id.minimum_order_value',readonly=False)
	c_id = fields.Many2one('res.currency', 'Cart Currency',default=lambda self: self.env.user.company_id.currency_id.id,required=True,related='website_id.c_id',readonly=False)
