from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.variant import WebsiteSaleVariantController


class WebsiteSaleBackToStock(WebsiteSale):
    @http.route(['/shop/back/stock/notify'], type='json', auth="public", website=True)
    def notify_stock(self, notify=True, product_id=None,**kw):
        print("in notify")
        if request.website.is_public_user():
            return
        if product_id:
            in_list = request.env['product.back.to.stock'].sudo().is_in_list(product_id)
            if notify:
                if not in_list:
                    request.env['product.back.to.stock'].sudo().create({
                        'user_id': request.env.user.id,
                        'product_id': int(product_id)
                    })
            else:
                if in_list:
                    stock = request.env['product.back.to.stock'].sudo().search([('product_id', '=', int(product_id)),
                                                                                ('user_id', '=', request.env.user.id)])
                    stock.unlink()


class WebsiteSaleBackToStockController(WebsiteSaleVariantController):
    @http.route()
    def get_combination_info_website(self, product_template_id, product_id, combination, add_qty, **kw):
        kw['context'] = kw.get('context', {})
        kw['context'].update(back_to_stock_notification=True)
        return super().get_combination_info_website(product_template_id, product_id, combination, add_qty, **kw)
