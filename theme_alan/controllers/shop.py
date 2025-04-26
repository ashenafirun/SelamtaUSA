# -*- coding: utf-8 -*-

from odoo.http import request, route
from odoo.tools import lazy
from odoo.osv import expression
from odoo.addons.website.controllers.main import QueryURL
from odoo.addons.website_sale.controllers.main import WebsiteSale, TableCompute
from datetime import datetime
from collections import Counter

class WebsiteSaleAlanShop(WebsiteSale):

    def hide_out_of_stock(self, product):
        website = request.env['website'].get_current_website()
        total_free_qty = sum(website._get_product_available_qty(prod) for prod in product.sudo().product_variant_ids)
        if not product.sudo().allow_out_of_stock_order and total_free_qty < 1:
            return False
        return product.id

    def _shop_lookup_products(self, attrib_set, options, post, search, website):
        product_count, details, fuzzy_search_term = website.sudo()._search_with_fuzzy("products_only", search,
                                                                               limit=None,
                                                                               order=self._get_search_order(post),
                                                                               options=options)
        search_result = details[0].get('results', request.env['product.template']).with_context(bin_size=True)
        only_stock = request.session.get("stock", False)
        if only_stock:
            search_result = search_result.filtered(lambda product: self.hide_out_of_stock(product))
        if request.env.user._is_public():
            search_result = search_result.filtered(lambda x: x.is_published and x.sale_ok)
        return fuzzy_search_term, product_count, search_result

    def _count_category_products(self):
        category_count = {}
        all_categs = request.env['product.public.category'].search([('website_id', 'in', [False, request.website.id])]).sudo()
        for rec in all_categs:
            child_ids = all_categs.search([('id', 'child_of', rec.ids), ('website_id', 'in', [False, request.website.id])])
            category_count[rec.id] = len(child_ids.mapped('product_tmpl_ids').sudo().filtered(lambda x: x.is_published))
        return category_count

    def _rbt_count(self, search_product, brand_list, tag_list, attributes):
        tag_count = { tag.id: len(tag.product_template_ids.sudo().filtered(lambda x: x in search_product)) for tag in tag_list}
        attr_count = { attr.id : len(attr.pav_attribute_line_ids.mapped('product_tmpl_id').sudo().filtered(lambda x: x in search_product)) for attr in attributes.mapped('value_ids')}
        brand_count = { brand.id : len(brand.brand_product_ids.sudo().filtered(lambda x: x in search_product)) for brand in brand_list}
        rating_count = Counter(rat for prod in search_product.sudo().filtered(lambda x: not all(rating.sudo().is_internal for rating in x.rating_ids))for rat in range(1, 6)if prod.sudo().product_rating >= rat)
        rating_count.update({rating: 0 for rating in range(1, 6) if rating not in rating_count})
        return tag_count, attr_count, brand_count, rating_count

    @route()
    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, ppg=False, **post):
        # Session based PPG
        if ppg:
            request.session['ppg'] = ppg
        else:
            if request.session.get('ppg', False):
                ppg = request.session['ppg']
            else:
                ppg = False

        # Stock Only
        only_stock = request.session.get("stock", False)
        if post.get("stock", False) == 'active':
            only_stock = True
        elif post.get("stock", False) == 'inactive':
            only_stock = False
        request.session["stock"] = only_stock

        brand_list = request.httprequest.args.getlist('brand')
        rating_list = request.httprequest.args.getlist('rating')
        env_context = dict(request.env.context)
        env_context.update({ 'brands':brand_list, 'rating':rating_list})
        request.env.context = env_context

        # Calling Super
        res = super(WebsiteSaleAlanShop, self).shop(page, category, search, min_price, max_price, ppg, **post)
        url = '/shop'
        if category:
            if type(category) == str:
                url = "/shop/category/%s" % category
            else:
                url = "/shop/category/%s" % request.env['ir.http']._slug(category)

        as_search_prds = res.qcontext['search_product']

        # Load More
        as_ppg = res.qcontext['ppg']
        ofst = 0
        alan_pager = request.website.pager(url=url, total=res.qcontext['search_count'], page=page, step=as_ppg, scope=res.qcontext['search_count'], url_args=post)
        for page in alan_pager.get('pages'):
            page.update(prd_ids=as_search_prds[ofst:ofst + as_ppg].ids)
            ofst += as_ppg
        res.qcontext.update({'alan_pager':alan_pager})

        # For Rating Filters
        rating_max = 1
        if len(as_search_prds.mapped("rating_avg")):
            rating_max = int(max(as_search_prds.mapped("rating_avg")))  + 1
        rating_set = [int(rating) for rating in rating_list]

        # For Brands Filters
        website = request.env['website'].get_current_website()
        website_domain = website.website_domain()
        ProductBrand = request.env['as.product.brand']
        brand_ids = ProductBrand.search(expression.AND([[('brand_product_ids.is_published', '=', True)],website_domain]))
        brand_set = [int(brand) for brand in brand_list]

        tag_count, attr_count, brand_count, rating_count = self._rbt_count(res.qcontext.get('search_product'), brand_ids, res.qcontext.get('all_tags', []), res.qcontext.get('attributes', []))
        category_count = self._count_category_products()

        res.qcontext.update({
            'stock_only':request.session["stock"],
            'as_shop':True,
            'ppg_list':request.env['as.ppg'].search([]),
            'ratings':rating_max,
            'rating_set': rating_set,
            'brands':brand_ids,
            'brand_set': brand_set,
            'category_count': category_count,
            'tag_count': tag_count,
            'rating_count': rating_count,
            'attr_count': attr_count,
            'brand_count': brand_count,
            'selected_brands': request.env['as.product.brand'].browse(brand_set),
            'selected_tags' : request.env['product.tag'].browse(res.qcontext.get('tags')),
        })

        return res

    @route('/nextpage/products', auth='public', type="json", website=True)
    def nextpage_products(self, **kw):
        if kw.get('product_ids'):
            products = request.env['product.template'].sudo()
            if kw.get('products'):
                products = request.env['product.template'].sudo().browse(kw.get('products'))
            website = request.env['website'].get_current_website()
            ppg = int(request.session.get('ppg') or 20)
            ppr = int(kw.get('ppr') or 4)
            product_ids = request.env['product.template'].sudo().browse(kw.get('product_ids'))
            if request.env.user._is_public():
                product_ids = product_ids.filtered(lambda x: x.is_published and x.sale_ok)
            products |= product_ids
            products_prices = lazy(lambda: products._get_sales_prices(website))
            keep = QueryURL('/shop',)
            return request.env['ir.ui.view']._render_template("theme_alan.shop_page_next_products",{
                'bins': lazy(lambda: TableCompute().process(product_ids.sudo(), ppg, ppr)),
                'ppg':ppg,
                'ppr':ppr,
                'keep': keep,
                'products': products,
                'products_prices': products_prices,
                'get_product_prices': lambda product: lazy(lambda: products_prices[product.id]),
                'products_in_wishlist': request.env['product.wishlist'].sudo().current().product_id.product_tmpl_id,
                })
        return {}

    @route('/get_similar_product', auth='public', type="json", website=True)
    def similar_product(self, **kw):
        product_id = kw.get('product_id')
        domain = expression.AND([request.website.sale_product_domain(), [('id', '=', product_id)]])
        product = request.env['product.template'].sudo().search(domain, limit=1)
        if not product:
            return False
        else:
            return request.env['ir.ui.view']._render_template("theme_alan.as_similar_product", {'products':product.alternative_product_ids})

    @route('/get_color_product', auth='public', type="json", website=True)
    def get_color_product(self, **kw):
        product_id = kw.get('product_id')
        domain = expression.AND([request.website.sale_product_domain(), [('id', '=', product_id)]])
        product = request.env['product.template'].sudo().search(domain, limit=1)
        if not product:
            return False
        else:
            return request.env['ir.ui.view']._render_template("theme_alan.as_color_product_dialog",{
                'product':product,
                'product_variant':product.product_variant_ids,
            })
