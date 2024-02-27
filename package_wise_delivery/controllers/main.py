# -*- coding: utf-8 -*-
import logging

from odoo import fields, http, SUPERUSER_ID, tools, _
from odoo.http import request
from odoo.addons.website.controllers.form import WebsiteForm
from odoo.addons.website_sale.controllers.main import WebsiteSale
_logger = logging.getLogger(__name__)

class WebsiteSaleExtended(WebsiteSale):
    @http.route(['/shop/checkout'], type='http', auth="public", website=True, sitemap=False)
    def checkout(self, **post):
        order = request.website.sale_get_order()
        if order.order_line.ids:
            for line in order.order_line:
                line.product_packaging_id = line.product_id.packaging_ids.filtered('sales')[0] if line.product_id.packaging_ids.filtered('sales').ids else False
                line._onchange_product_packaging_id()
                line._onchange_update_product_packaging_qty()
        redirection = self.checkout_redirection(order)
        if redirection:
            return redirection

        if order.partner_id.id == request.website.user_id.sudo().partner_id.id:
            return request.redirect('/shop/address')

        redirection = self.checkout_check_address(order)
        if redirection:
            return redirection

        values = self.checkout_values(**post)

        if post.get('express'):
            return request.redirect('/shop/confirm_order')

        values.update({'website_sale_order': order})

        # Avoid useless rendering if called in ajax
        if post.get('xhr'):
            return 'ok'
        return request.render("website_sale.checkout", values)
