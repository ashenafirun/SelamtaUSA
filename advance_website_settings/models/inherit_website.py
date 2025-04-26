# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2018-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>:wink:
# See LICENSE file for full copyright and licensing details.
#################################################################################

from odoo import fields, models,api
from odoo import models
from odoo.tools.translate import _
import logging
_logger = logging.getLogger(__name__)

class website(models.Model):
	_inherit = 'website'

	add_to_cart_action = fields.Selection(selection_add=[('shop_page', 'Go to Shop page')], ondelete={'force_dialog': 'set default'})
	reference_number = fields.Boolean(string = 'Reference Number')
	sub_total = fields.Boolean(string = 'Show Subtotal')
	minimum_order_value = fields.Float(string = 'Minimum Cart Value To Validate Order')
	minimum_product_quantity = fields.Integer(string="Minimum Product Quantity To Validate Order",default=-1)
	max_product_quantity = fields.Integer(string="Maxmium Product Quantity To Validate Order",default=-1)
	c_id = fields.Many2one('res.currency', 'Cart Currency',default=lambda self: self.env.user.company_id.currency_id.id,required=True)


	def show_subTotal(self):
		ir_default = self.env['website'].sudo().get_current_website().sub_total
		return True if ir_default == None else ir_default
