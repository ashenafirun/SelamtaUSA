# -*- coding: utf-8 -*-

import ast
import json
from werkzeug.exceptions import Forbidden, NotFound, RequestTimeout

from odoo.http import request
from odoo import http, fields,  SUPERUSER_ID, tools, _
from odoo.addons.website.controllers.main import QueryURL
from odoo.addons.http_routing.models.ir_http import slug
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.main import TableCompute

# Alan Shop Page Customization
class AtharvaWebsiteSaleExtend(WebsiteSale):
    @http.route([])
    def shop(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, ppg=False, **post):
        # Super shop call
        res = super(AtharvaWebsiteSaleExtend, self).shop(page=page, category=category, search=search,
        min_price=min_price, max_price=max_price, ppg=ppg, **post)
        # Ensure min and max price
        try:
            min_price = float(min_price)
        except ValueError:
            min_price = 0
        try:
            max_price = float(max_price)
        except ValueError:
            max_price = 0
        # Ensure product per page and row
        if ppg:
            try:
                ppg = int(ppg)
                post['ppg'] = ppg
            except ValueError:
                ppg = False
        if not ppg:
            ppg = request.env['website'].get_current_website().shop_ppg or 20
        ppr = request.env['website'].get_current_website().shop_ppr or 4
        # Category find and search category
        Category = request.env['product.public.category']
        category_tags = False
        if category:
            category = Category.search([('id', '=', int(category))], limit=1)
            category_tags = Category.search([('parent_id', '=', category.id)])
            if not category or not category.can_access_from_current_website():
                raise NotFound()
        else:
            category = Category
        # Get pricelist context data
        pricelist_context, pricelist = self._get_pricelist_context()
        # Alan rbt(rating,brand,tag) filter data
        common_domain = [('active','=',True), ('website_id', 'in', (False, request.website.id))]
        all_brand_list = request.env['as.product.brand'].search(common_domain)
        all_tag_list = request.env['product.tags'].search(common_domain)
        rating_list = request.httprequest.args.getlist('rating')
        brand_list = request.httprequest.args.getlist('brand')
        tag_list = request.httprequest.args.getlist('tag')
        post.update({'tag':tag_list, 'rating':rating_list, 'brand':brand_list})
        # Set rbt(rating,brand,tag) domain for rbt data
        if not len(rating_list):
            rating_domain = False
        else:
            rating_domain = min(rating_list)
        if not len(brand_list):
            brand_domain = False
        else:
            brand_domain = brand_list
        if not len(tag_list):
            tag_domain = False
        else:
            tag_domain = tag_list
        # Default attribute
        attrib_list = request.httprequest.args.getlist('attrib')
        attrib_values = [[int(x) for x in v.split("-")] for v in attrib_list if v]
        attributes_ids = {v[0] for v in attrib_values}
        attrib_set = {v[1] for v in attrib_values}
        # Default price filter
        filter_by_price_enabled = request.website.is_view_active('website_sale.filter_products_price')
        if filter_by_price_enabled:
            company_currency = request.website.company_id.currency_id
            conversion_rate = request.env['res.currency']._get_conversion_rate(company_currency, pricelist.currency_id, request.website.company_id, fields.Date.today())
        else:
            conversion_rate = 1
        # Default keep with rbt data
        keep = QueryURL('/shop', category=category and int(category),
                        search=search,
                        attrib=attrib_list,
                        min_price=min_price, max_price=max_price,
                        order=post.get('order'),
                        rating=rating_list,
                        brand=brand_list,
                        tag=tag_list)
        # Add extra rbt data in options to find accurate product with rbt filter
        options = {
            'displayDescription': True,
            'displayDetail': True,
            'displayExtraDetail': True,
            'displayExtraLink': True,
            'displayImage': True,
            'allowFuzzy': not post.get('noFuzzy'),
            'category': str(category.id) if category else None,
            'min_price': min_price / conversion_rate,
            'max_price': max_price / conversion_rate,
            'attrib_values': attrib_values,
            'display_currency': pricelist.currency_id,
            'rating':rating_domain,
            'brand':brand_domain,
            'tag':tag_domain,
        }
        # Get acutal product with filter applied
        product_count, details, fuzzy_search_term = request.website._search_with_fuzzy("products_only", search,
            limit=None, order=self._get_search_order(post), options=options)
        search_product = details[0].get('results', request.env['product.template']).with_context(bin_size=True)
        website_domain = request.website.website_domain()
        categs_domain = [('parent_id', '=', False)] + website_domain
        if search:
            search_categories = Category.search([('product_tmpl_ids', 'in', search_product.ids)] + website_domain).parents_and_self
            categs_domain.append(('id', 'in', search_categories.ids))
        else:
            search_categories = Category
        categs = Category.search(categs_domain)
        url = "/shop"
        if category:
            url = "/shop/category/%s" % slug(category)
        # Get pager data with offset
        pager = request.website.pager(url=url, total=product_count, page=page, step=ppg, scope=7, url_args=post)
        offset = pager['offset']
        products = search_product[offset:offset + ppg]
        ProductAttribute = request.env['product.attribute']
        # Default attribute filter applied based on product seacrh product
        if products:
            attributes = ProductAttribute.search([
                ('product_tmpl_ids', 'in', search_product.ids),
                ('visibility', '=', 'visible'),
            ])
        else:
            attributes = ProductAttribute.browse(attributes_ids)
        # Alan product counter and hide no product attributes
        if request.website.is_view_active('atharva_theme_base.product_counter') or request.website.is_view_active('atharva_theme_base.no_product_attribute_hide'):
            variant_count = self._variant_count(search_product, attributes)
            rating_count, brand_count, tag_count = self._rbt_count(search_product, all_brand_list, all_tag_list)
            category_count = self._category_count(website_domain)
            res.qcontext.update({ 'variant_count':variant_count,
                'brand_count':brand_count,'tag_count':tag_count,
                'rating_count':rating_count,'category_count':category_count })
        # Update defualt context value
        res.qcontext.update({
            'attrib_values': attrib_values,
            'attrib_set': attrib_set,
            'pager': pager,
            'products': products,
            'search_count': product_count,
            'bins': TableCompute().process(products, ppg, ppr),
            'categories': categs,
            'attributes': attributes,
            'keep': keep,
            'rating':rating_list,
            'sel_brand_list':brand_list,
            "all_brand_list":all_brand_list,
            'sel_tag_list':tag_list,
            "all_tag_list":all_tag_list,
            'category_tags':category_tags,
            'search_categories_ids': search_categories.ids,
            'order':post.get('order')
        })
        return res

    def _variant_count(self, search_product, attributes):
        ''' Default attribute counter'''
        attr_count = {}
        attrs_line = request.env['product.template.attribute.line'].search([('product_tmpl_id','in',search_product.ids)])
        for attr in attributes:
            for val in attr.value_ids:
                attr_count[val.id] = 0
        if attrs_line:
            for each_line in attrs_line:
                for val in each_line.value_ids:
                    if val.id in attr_count:
                        attr_count[val.id] += 1
        return attr_count

    def _rbt_count(self, search_product, brand_list, tag_list):
        ''' Rating Brand Tag(rbt)counter'''
        brand_count = { brand.id : 0 for brand in brand_list }
        tag_count = { tag.id : 0 for tag in tag_list }
        rating_count = { rating : 0 for rating in range(1,5) }
        for prod in search_product:
            if prod.product_brand_id:
                brand_count[prod.product_brand_id.id] += 1
            if prod.product_tags_ids:
                for tag in prod.product_tags_ids:
                    if tag.id in tag_count:
                        tag_count[tag.id] += 1
            for rat in range(1,5):
                if prod.product_rating >= rat:
                    rating_count[rat] += 1
        return rating_count, brand_count, tag_count

    def _category_count(self,website_domain):
        '''Category counter base on product'''
        categories = request.env['product.public.category'].search(website_domain)
        category_count = { cat.id:0 for cat in categories }
        Product = request.env['product.template'].with_context(bin_size=True)
        for cat in categories:
            search_product = Product.search_count([('public_categ_ids', 'child_of', int(cat.id))])
            category_count[cat.id] = search_product
        return category_count

    @http.route('/json/shop/product/', type='json', auth='public', website=True, sitemap=False)
    def get_json_product(self, page=0, category=None, search='', min_price=0.0, max_price=0.0, ppg=False, **post):
        '''Alan quick load product'''
        paper_dic = {}
        page = int(page) + 1
        # Ensure min and max price
        try:
            min_price = float(min_price)
        except ValueError:
            min_price = 0
        try:
            max_price = float(max_price)
        except ValueError:
            max_price = 0
         # Ensure product per page and row
        if ppg:
            try:
                ppg = int(ppg)
                post['ppg'] = ppg
            except ValueError:
                ppg = False
        if not ppg:
            ppg = request.env['website'].get_current_website().shop_ppg or 20
        ppr = request.env['website'].get_current_website().shop_ppr or 4
        # Category find and search category
        Category = request.env['product.public.category']
        if category:
            category = Category.search([('id', '=', int(category))], limit=1)
            if not category or not category.can_access_from_current_website():
                raise NotFound()
        else:
            category = Category
        # get pricelist context data
        pricelist_context, pricelist = self._get_pricelist_context()
        # Alan rbt(rating,brand,tag) filter data
        rating_list = ast.literal_eval(post.get("rating","[]"))
        brand_list = ast.literal_eval(post.get("sel_brand_list","[]"))
        tag_list = ast.literal_eval(post.get("sel_tag_list","[]"))
        # Set rbt(rating,brand,tag) domain for rbt data
        if not len(rating_list):
            rating_domain = False
        else:
            rating_domain = min(rating_list)
        if not len(brand_list):
            brand_domain = False
        else:
            brand_domain = brand_list
        if not len(tag_list):
            tag_domain = False
        else:
            tag_domain = tag_list
        # Default attribute
        attrib_values= post.get('attrval')
        attrib_values = json.loads(attrib_values)
        attrib_list = [str(i[0]) + "-" + str(i[1]) for i in attrib_values]
        # Default price filter
        filter_by_price_enabled = request.website.is_view_active('website_sale.filter_products_price')
        if filter_by_price_enabled:
            company_currency = request.website.company_id.currency_id
            conversion_rate = request.env['res.currency']._get_conversion_rate(company_currency, pricelist.currency_id, request.website.company_id, fields.Date.today())
            Product = request.env['product.template'].with_context(bin_size=True)
            domain = self._get_search_domain(search, category, attrib_values)
            from_clause, where_clause, where_params = Product._where_calc(domain).get_sql()
            query = f"""
                SELECT COALESCE(MIN(list_price), 0) * {conversion_rate}, COALESCE(MAX(list_price), 0) * {conversion_rate}
                  FROM {from_clause}
                 WHERE {where_clause}
            """
            request.env.cr.execute(query, where_params)
            available_min_price, available_max_price = request.env.cr.fetchone()
            if min_price or max_price:
                if min_price:
                    min_price = min_price if min_price <= available_max_price else available_min_price
                    post['min_price'] = min_price
                if max_price:
                    max_price = max_price if max_price >= available_min_price else available_max_price
                    post['max_price'] = max_price
        else:
            conversion_rate = 1
        # Default keep with rbt data
        keep = QueryURL('/shop', category=category and int(category),
                        search=search,
                        attrib=attrib_list,
                        min_price=min_price, max_price=max_price,
                        order=post.get('order'),
                        rating=rating_list,
                        brand=brand_list,
                        tag=tag_list)
        # Add extra rbt data in options to find accurate product with rbt filter
        options = {
            'displayDescription': True,
            'displayDetail': True,
            'displayExtraDetail': True,
            'displayExtraLink': True,
            'displayImage': True,
            'allowFuzzy': not post.get('noFuzzy'),
            'category': str(category.id) if category else None,
            'min_price': min_price / conversion_rate,
            'max_price': max_price / conversion_rate,
            'attrib_values': attrib_values,
            'display_currency': pricelist.currency_id,
            'rating':rating_domain,
            'brand':brand_domain,
            'tag':tag_domain,
        }
        # Get acutal product with filter applied
        product_count, details, fuzzy_search_term = request.website._search_with_fuzzy("products_only", search,
            limit=None, order=self._get_search_order(post), options=options)
        search_product = details[0].get('results', request.env['product.template']).with_context(bin_size=True)
        url = "/shop"
        if category:
            paper_dic.update({'category':category.id})
            url = "/shop/category/%s" % slug(category)
        if search != '':
            paper_dic.update({'search':search})
        if post.get('order', False):
            paper_dic.update({'order':post.get('order')})
        try:
            if min_price != available_min_price:
                paper_dic.update({'min_price':min_price})
            if max_price != available_max_price:
                paper_dic.update({'max_price':max_price})
        except:
            pass
        paper_dic.update({'attrib':attrib_list, 'tag': tag_list, 'brand':brand_list, 'rating':rating_list})
        pager = request.website.pager(url=url, total=product_count, page=page, step=ppg, scope=7, url_args=paper_dic)
        offset = pager['offset']
        products = search_product[offset:offset + ppg]
        # Get accurate product in custom product template
        temp_of_prod = request.env.ref('atharva_theme_base.as_quick_products_load')._render({'bins':TableCompute().process(products, ppg, ppr),
                        'pager': pager,'keep':keep})
        # Get updated pager
        pager_template = request.env['ir.ui.view']._render_template('portal.pager', {'pager':pager})
        # Set and return finished data
        data = {'product':temp_of_prod,'max_page':pager['page_count'],
                'pagerheader': page,'pager_template':pager_template}
        return data

    @http.route('/shop/brands', type='http', auth='public', website=True, sitemap=False)
    def all_brands(self, **post):
        ''' Brand page and searching brand '''
        values = {}
        domain = [('active','=',True),('visible_slider','=',True)] + request.website.website_domain()
        if post.get('search'):
            domain += [('name', 'ilike', post.get('search'))]
        brand_ids = request.env['as.product.brand'].search(domain)
        keep = QueryURL('/shop/brands', brand_id=[])
        if brand_ids:
            values.update({'brands': brand_ids,'keep': keep})
        if post.get('search'):
            values.update({'search': post.get('search')})
        return request.render('atharva_theme_base.product_brands', values)