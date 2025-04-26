from odoo import models, api, fields
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    discount_offer = fields.Html('Discount Offer')
    sku_code = fields.Char('SKU Code')

    @api.model
    def _search_get_detail(self, website, order, options):
        res = super(ProductTemplate, self)._search_get_detail(website, order, options)
        res['search_fields'].append('default_code')
        res['search_fields'].append('sku_code')
        return res

    def _search_render_results(self, fetch_fields, mapping, icon, limit):
        if request.website.is_public_user() and 'detail' in mapping:
            del mapping['detail']
        res = super(ProductTemplate, self)._search_render_results(fetch_fields, mapping, icon, limit)
        return res
