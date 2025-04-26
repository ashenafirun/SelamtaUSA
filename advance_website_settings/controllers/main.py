# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2018-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>:wink:
# See LICENSE file for full copyright and licensing details.
#################################################################################
from odoo import http
from odoo.http import request
from odoo import SUPERUSER_ID
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.variant import WebsiteSaleVariantController
from odoo import fields
import logging
_logger = logging.getLogger(__name__)


class website_sale(WebsiteSale):
	def _filter_attributes(self, **kw):
		return {k: v for k, v in kw.items() if "attribute" in k}

	# def get_redirect_url(self, product_id):
	# 	url = "/shop/cart"
	# 	redirect_to_cart = request.website.add_to_cart_action
	# 	if redirect_to_cart == 'same' and product_id:
	# 		product = request.env['product.product'].sudo().browse(int(product_id))
	# 		if product:
	# 			url = '/shop/%s' % slug(product.product_tmpl_id)
	# 	elif redirect_to_cart == "previous_page":
	# 		url = request.httprequest.referrer

	# 	return url

	# @http.route()
	# def cart_update(self, product_id, add_qty=1, set_qty=0,product_custom_attribute_values=None, no_variant_attribute_values=None,express=False, **kwargs):
	# 	super(website_sale, self).cart_update(product_id, add_qty=add_qty, set_qty=set_qty,product_custom_attribute_values=product_custom_attribute_values,no_variant_attribute_values=no_variant_attribute_values,express=express, **kwargs)
	# 	url = self.get_redirect_url(product_id)
	# 	return request.redirect(url)

	@http.route()
	def cart(self, access_token=None, revive='', **post):
		rec = super().cart(access_token=access_token,revive=revive,**post)
		is_amount_valid = True
		conf_minimum_order_value = request.env["website"].get_current_website().minimum_order_value
		ir_default =request.env['website'].get_current_website().c_id._convert(
                request.env['website'].get_current_website().minimum_order_value, request.env['website'].get_current_website().pricelist_id.currency_id, request.env.user.company_id,
                    fields.Date.today()
                    )
		pricelist_val = request.env['website'].get_current_website()._get_current_pricelist().minimum_price
		if rec.qcontext.get("amount",False):
			if pricelist_val:
				if pricelist_val > rec.qcontext["amount"]:
					is_amount_valid = False
			else:
				if ir_default > rec.qcontext["amount"]:
					is_amount_valid = False
		rec.qcontext.update({"is_amount_valid":is_amount_valid})
		return rec
	
	@http.route()
	def cart_update_json(
        self, product_id, line_id=None, add_qty=None, set_qty=None, display=True,
        product_custom_attribute_values=None, no_variant_attribute_values=None, **kw
    ):
		
		rec = super().cart_update_json(product_id,line_id=line_id,add_qty=add_qty,set_qty=set_qty,display=display,product_custom_attribute_values=product_custom_attribute_values,no_variant_attribute_values=no_variant_attribute_values,**kw)
		is_amount_valid = True
		ir_default =request.env['website'].get_current_website().c_id._convert(
                request.env['website'].get_current_website().minimum_order_value, request.env['website'].get_current_website().pricelist_id.currency_id, request.env.user.company_id,
                    fields.Date.today()
                    )
		pricelist_val = request.env['website'].get_current_website()._get_current_pricelist().minimum_price
		if 'amount' in rec.keys() :
			if rec['amount']:
				if pricelist_val:
					if pricelist_val > rec['amount']:
						is_amount_valid = False
				else:
					if ir_default > rec['amount']:
						is_amount_valid = False
		rec.update({"is_amount_valid":is_amount_valid})
		_logger.info(f'========={set_qty = }=={rec = }==')
		return rec


	@http.route("/wk_get_redirect_val", type='json', auth="public",website=True)
	def wk_get_redirect_val(self, product_id):
		url = self.get_redirect_url(product_id)
		return url

	@http.route(["/website/wk_lang"], type='json', auth="public", methods=['POST'], website=True)
	def website_langauge(self, code, **kw):
		lang_id = request.env['res.lang'].search([('code','=',code.replace('-','_'))])
		return {
			'sep_format': lang_id.grouping,
			'decimal_point': lang_id.decimal_point,
			'thousands_sep': lang_id.thousands_sep,
			'symbol':request.website._get_current_pricelist().currency_id.symbol
		}


	def checkout_redirection(self, order):
		minimum_order_value = order.get_minimun_cart_value() if order.get_minimun_cart_value() else 1
		pricelist_val =request.env['website'].get_current_website()._get_current_pricelist().minimum_price
		if pricelist_val and order.amount_total < pricelist_val:
			return request.redirect('/shop/cart')

		if minimum_order_value and order.amount_total < minimum_order_value:
			return request.redirect('/shop/cart')
		return super(website_sale, self).checkout_redirection(order)
	
class SaleCombinationInfo(WebsiteSaleVariantController):
    @http.route(auth='public')
    def get_combination_info_website(self, product_template_id, product_id, combination, add_qty,parent_combination=None , **kw):
        response = super(SaleCombinationInfo, self).get_combination_info_website(product_template_id,
        product_id, combination, add_qty, parent_combination=None, **kw)
        p_id = request.env['product.template'].sudo().browse(int(product_template_id))
        comb=request.env['product.template.attribute.value'].sudo().browse(combination)
        variant=p_id.sudo()._get_variant_for_combination(comb)
        response.update({'variant_code':variant.default_code})
        return response

	
class CutomRoute(http.Controller):
	@http.route('/varient/limit/',auth='public',type="json",website=True)
	def varient_limit(self,id,**kw):
		if id:
			varient_id = request.env["product.product"].browse(int(id))
			template_id = varient_id.product_tmpl_id
			website_id = request.env['website'].get_current_website()
			data = {
				"min_value":varient_id.minimum_product_quantity,
				"max_value":varient_id.max_product_quantity,
				"conf_max_value":website_id.max_product_quantity,
				"conf_min_value":website_id.minimum_product_quantity,
				"enable_limit":int(varient_id.check_box),
				"min_value_temp":template_id.minimum_product_quantity,
				"max_value_temp":template_id.max_product_quantity,
				"enable_limit_template":int(template_id.check_box)
			} 
			return data
		else:
			return False
	


