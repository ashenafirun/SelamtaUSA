# -*- coding: utf-8 -*-

import json
import datetime
from markupsafe import Markup
from datetime import timedelta

from odoo import http, _
from odoo.http import request
from odoo.osv import expression

class ThemeAlanBaseSnippetRoute(http.Controller):

    @http.route('/json/alternative_product/' ,type='json',auth='public',website=True)
    def json_alternative_product(self,**kwargs):
        ''' Method To fetch Similar Product In quick cart template '''
        getproduct = request.env['product.template'].search([('id','=',kwargs['prod_tmp_id'])])
        getSimilarProd = getproduct.alternative_product_ids
        get_temp_id = request.website.sudo().theme_id.name + ".quick_alter_prod_template"
        get_template = request.env['ir.ui.view']._render_template(get_temp_id, {'products':getSimilarProd})
        return {'quickAlterTemp':get_template}

    @http.route(['/get/quick_product_view', '/shop/page/get/quick_product_view' ], type='json', auth='public', website=True)
    def quick_product_view(self,**kwargs):
        ''' Method to add Quick Viee Product Data in Modal '''
        id = kwargs.get("productId")
        hasVariant = kwargs.get("hasVariant")
        viewType = kwargs.get("viewType")
        getProduct = request.env['product.template'].sudo().search([('id','=', int(id))])
        if viewType == "as-quick-add-to-cart" and hasVariant == "True":
            get_template = request.env['ir.ui.view']._render_template(
            "theme_alan.quick_cart", {'product':getProduct})
        elif viewType == "as-quick-add-to-cart" and hasVariant != "True":
            getProduct = request.env['product.product'].sudo().search([('id','=', int(id))])
            cartQuant = kwargs.get("cartQuant","")
            totalAmount = kwargs.get("totalAmount","")
            get_template = request.env['ir.ui.view']._render_template(
            "theme_alan.addedCart", {'product':getProduct,'cartQuant':cartQuant,'totalAmount':Markup(totalAmount)})
        else:
            get_template = request.env['ir.ui.view']._render_template(
            "theme_alan.quick_view", {'product':getProduct})
        return {'template': get_template}

    @http.route(['/get/get_cat_brand_slider_content'], type='json', auth='public', website=True)
    def get_cat_brand_slider_content(self, **kwargs):
        '''Method to get Brand and Category slider data '''
        values = {}
        brand_ids = ""
        cat_ids = ""
        blog_ids = ""
        snippet_type = ""
        products=[]
        website_domain = request.website.website_domain()
        domain = website_domain + [('website_published', '=', True),('sale_ok', '=', True),('is_published','=',True)]
        if kwargs.get('snippet_type'):
            snippet_type = kwargs.get('snippet_type')
        if kwargs.get('brand_ids'):
            brand_vals = json.loads(kwargs.get('brand_ids'))
            seq_brand = []
            for b in brand_vals:
                get_brand = request.env['as.product.brand'].search([('id','=',b)] + website_domain)
                if len(get_brand):
                    seq_brand.append(get_brand.id)
            brand_ids = request.env['as.product.brand'].browse(seq_brand)
            if snippet_type == "brand_product":
                domain += [('product_brand_id', 'in', brand_ids.ids)]
                domain = expression.AND([domain])
                products = request.env['product.template'].sudo().search(domain + website_domain)
        if kwargs.get('cat_ids'):
            cat_vals = json.loads(kwargs.get('cat_ids'))
            seq_categ = []
            for c in cat_vals:
                get_categ = request.env['product.public.category'].search([('id','=',c)] + website_domain)
                if len(get_categ):
                    seq_categ.append(get_categ.id)
            cat_ids = request.env['product.public.category'].browse(seq_categ)
            if snippet_type == "category_product":
                domain += [('public_categ_ids', 'in', cat_ids.ids)]
                domain = expression.AND([domain])
                products = request.env['product.template'].sudo().search(domain + website_domain)
        if kwargs.get('blog_ids'):
            blog_vals = json.loads(kwargs.get('blog_ids'))
            seq_blog = []
            for b in blog_vals:
                get_blog = request.env['blog.post'].search([('id','=',b)] + website_domain)
                if len(get_blog):
                    seq_blog.append(get_blog.id)
            blog_ids = request.env['blog.post'].browse(seq_blog)
        mainUI = kwargs.get('mainUI')
        tabOption = kwargs.get('tabOption')
        styleUI = kwargs.get('styleUI')
        recLink = kwargs.get('recordLink')
        aSlider = kwargs.get('autoSlider')
        product_label = kwargs.get('prodLabel')
        buyNow = kwargs.get('buyNow')
        wish_list = kwargs.get('wishList')
        compares = kwargs.get('compare')
        ratings = kwargs.get('rating')
        cart = kwargs.get('cart')
        quickViews = kwargs.get('quickView')
        infinity_slider = kwargs.get('infinity')
        sliderType = json.loads(kwargs.get('sliderType'))
        recordLink = False if recLink == "" else True
        autoSlider = False if aSlider == "" else True
        prod_label = False if product_label == "" else True
        wishList = False if wish_list == "" else True
        prod_buy = False if buyNow == "" else True
        prod_compare = False if compares == "" else True
        prod_rating = False if ratings == "" else True
        prod_cart = False if cart == "" else True
        quickView = False if quickViews == "" else True
        infinity = False if infinity_slider == "" else True
        dataCount = json.loads(kwargs.get('dataCount'))
        if kwargs.get('sTimer'):
            sTimer = json.loads(kwargs.get('sTimer'))
        if "slider" in mainUI:
            if brand_ids:
                if snippet_type == "brand_product":
                    tmplt = request.website.viewref("theme_alan.alan_brand_product_slider_layout")
                else:
                    tmplt = request.website.viewref("theme_alan.alan_brand_slider_layout")
            elif cat_ids:
                if snippet_type == "category_product":
                    tmplt = request.website.viewref("theme_alan.alan_cat_product_slider_layout")
                else:
                    tmplt = request.website.viewref("theme_alan.alan_cat_slider_layout")
            elif blog_ids:
                tmplt = request.website.viewref("theme_alan.alan_blog_slider_layout")
        else :
            if brand_ids:
                if snippet_type == "brand_product":
                    tmplt = request.website.viewref("theme_alan.alan_brand_product_column_layout")
                else:
                    tmplt = request.website.viewref("theme_alan.alan_brand_column_layout")
            elif cat_ids:
                if snippet_type == "category_product":
                    tmplt = request.website.viewref("theme_alan.alan_cat_product_column_layout")
                else:
                    tmplt = request.website.viewref("theme_alan.alan_cat_column_layout")
            elif blog_ids:
                tmplt = request.website.viewref("theme_alan.alan_blog_grid_layout")
        if tmplt:
            values.update({'dataCount': dataCount, 'mainUI': mainUI,
                    'autoSlider': autoSlider, 'tabOption':tabOption, 'sliderType': sliderType})
            common_data = {'recordLink': recordLink, 'dataCount': dataCount , 'styleUI': styleUI}
            if sliderType == 7:
                common_data['sliderType'] = sliderType
            quick_option_data = {'prod_label': prod_label, 'wish_list': wishList, 'prod_compare': prod_compare, 'prod_rating': prod_rating,
                                 'prod_cart': prod_cart, 'quickView': quickView, 'prod_buy': prod_buy}
            if brand_ids:
                if products:
                    values.update(
                    {'slider': tmplt._render({'brands': brand_ids, 'products': products, 'tabOption': tabOption, **common_data, **quick_option_data})})
                else:
                    values.update(
                    {'slider': tmplt._render({'brands': brand_ids, **common_data})})
            elif cat_ids:
                if products:
                    values.update(
                    {'slider': tmplt._render({'categories': cat_ids, 'products': products, 'tabOption': tabOption, **common_data, **quick_option_data})})
                else:
                    values.update(
                    {'slider': tmplt._render({'categories': cat_ids, **common_data})})
            elif blog_ids:
                values.update({'slider': tmplt._render({'blogs': blog_ids,'dataCount': dataCount,'styleUI': styleUI, 'sliderType':sliderType
                    })})
            if kwargs.get('sTimer'):
                values.update({'sTimer': sTimer*1000})
            if infinity:
                values.update({'infinity': infinity})
            return values
        else:
            return False

    @http.route('/get/product_popover',type="json",auth='public',website=True)
    def product_popover_image_hotspot(self,**kwargs):
        ''''Image Hotspot Popover '''
        prod_id = int(kwargs.get('id'))
        getpd = request.env['product.template'].sudo().search([('id','=',prod_id)])
        get_products_temp = request.env['ir.ui.view']._render_template(
            'theme_alan.img_hotspot_product_popover',{'product':getpd,'cls':kwargs.get('popstyle')})
        return get_products_temp

    @http.route(['/get/get_product_slider_content'], type='json', auth='public', website=True)
    def get_product_slider_content(self, **kwargs):
        '''Method to get Product Data'''
        values = {}
        prod_ids = ""
        snippet_type = ""
        mainUI = ""
        website_domain = request.website.website_domain()
        snippet_type = kwargs.get('snippet_type')
        totalCount = kwargs.get('totalCount')
        imgPosition = kwargs.get('imgPosition')
        styleUI = kwargs.get('styleUI')
        product_label = kwargs.get('prodLabel')
        if kwargs.get('mainUI'):
            mainUI = kwargs.get('mainUI')
        wish_list = kwargs.get('wishList')
        compares = kwargs.get('compare')
        ratings = kwargs.get('rating')
        cart = kwargs.get('cart')
        buyNow = kwargs.get('buyNow')
        quickViews = kwargs.get('quickView')
        infinity_slider = kwargs.get('infinity')
        aSlider = kwargs.get('autoSlider')
        sliderType = json.loads(kwargs.get('sliderType'))
        if kwargs.get('dataCount'):
            dataCount = json.loads(kwargs.get('dataCount'))
        prod_label = False if product_label == "" else True
        wishList = False if wish_list == "" else True
        prod_compare = False if compares == "" else True
        prod_rating = False if ratings == "" else True
        prod_cart = False if cart == "" else True
        prod_buy = False if buyNow == "" else True
        quickView = False if quickViews == "" else True
        autoSlider = False if aSlider == "" else True
        infinity = False if infinity_slider == "" else True
        if kwargs.get('sTimer'):
            sTimer = json.loads(kwargs.get('sTimer'))
        if snippet_type == "best_product":
            website_id = request.website.id
            request.env.cr.execute("""SELECT PT.id, SUM(SO.product_uom_qty),PT.website_id
                                      FROM sale_order S
                                      JOIN sale_order_line SO ON (S.id = SO.order_id)
                                      JOIN product_product P ON (SO.product_id = P.id)
                                      JOIN product_template pt ON (P.product_tmpl_id = PT.id)
                                      WHERE S.state in ('sale','done')
                                      AND (S.date_order >= %s AND S.date_order <= %s)
                                      AND (PT.website_id IS NULL OR PT.website_id = %s)
                                      AND PT.active='t'
                                      AND PT.is_published='t'
                                      GROUP BY PT.id
                                      ORDER BY SUM(SO.product_uom_qty)
                                      DESC LIMIT %s
                                   """, [datetime.datetime.today() - timedelta(int(totalCount)), datetime.datetime.today(), website_id, totalCount])
            table = request.env.cr.fetchall()
            products = []
            for record in table:
                if record[0]:
                    pro_obj = request.env[
                        'product.template'].sudo().browse(record[0])
                    if pro_obj.sale_ok == True and pro_obj.is_published == True:
                        products.append(pro_obj)
        if snippet_type == "latest_product":
            prod_ids = request.env['product.template'].sudo().search([('website_published', '=', True),('sale_ok', '=', True),('is_published','=',True)] + website_domain, order='id desc', limit=int(totalCount))
        if snippet_type == "prod_variant":
            modal = "product.product"
        else:
            modal = "product.template"
        if kwargs.get('prod_ids'):
            prod_vals = json.loads(kwargs.get('prod_ids'))
            prod_lst = []
            for prod in prod_vals:
                domain = [('website_published', '=', True),('sale_ok', '=', True),('is_published','=',True),('id', '=', prod)] + website_domain
                domain = expression.AND([domain])
                if len(request.env[modal].sudo().search(domain)):
                    prod_lst.append(prod)
        if snippet_type == "prod_variant":
            prod_ids = request.env[modal].browse(prod_lst)
        if snippet_type == "product":
            prod_ids = request.env[modal].browse(prod_lst)
        if snippet_type == "best_product":
            prod_ids = products
        if snippet_type == "prod_banner":
            prod_ids = request.env[modal].browse(prod_lst)
            tmplt = request.website.viewref("theme_alan.alan_product_banner_slider_layout")
        if "slider" in mainUI:
            if snippet_type == "prod_variant":
                tmplt = request.website.viewref("theme_alan.alan_product_variant_slider_layout")
            elif snippet_type == "product":
                tmplt = request.website.viewref("theme_alan.alan_product_slider_layout")
            elif snippet_type == "best_product":
                tmplt = request.website.viewref("theme_alan.alan_best_seller_product_slider_layout")
            elif snippet_type == "latest_product":
                tmplt = request.website.viewref("theme_alan.alan_latest_product_slider_layout")
        else :
            if snippet_type == "prod_variant":
                tmplt = request.website.viewref("theme_alan.alan_product_variant_grid_layout")
            elif snippet_type == "product":
                tmplt = request.website.viewref("theme_alan.alan_product_grid_layout")
            elif snippet_type == "best_product":
                tmplt = request.website.viewref("theme_alan.alan_best_seller_product_grid_layout")
            elif snippet_type == "latest_product":
                tmplt = request.website.viewref("theme_alan.alan_latest_product_grid_layout")
        if snippet_type == "prod_banner":
            values.update({'slider': tmplt._render({'products': prod_ids, 'prod_label': prod_label, 'prod_buy': prod_buy,
                                                'imgPosition': imgPosition, 'prod_rating': prod_rating, 'prod_cart': prod_cart,
                                                'quickView': quickView, 'styleUI': styleUI, 'sliderType': sliderType}),
                                                'autoSlider': autoSlider, 'sliderType': sliderType})
        else:
            values.update({'slider': tmplt._render({'products': prod_ids, 'prod_label': prod_label,'wish_list': wishList,
                                                'prod_compare': prod_compare, 'prod_rating': prod_rating, 'prod_cart': prod_cart,
                                                'quickView': quickView, 'styleUI': styleUI,'dataCount': dataCount, 'sliderType': sliderType}),
                                                'dataCount': dataCount, 'autoSlider': autoSlider, 'sliderType': sliderType})
        if kwargs.get('sTimer'):
            values.update({'sTimer': sTimer*1000})
        if infinity:
            values.update({'infinity': infinity})
        return values

    @http.route(['/get_website_faq_list'], type='json', auth='public', website=True)
    def get_website_faq_list(self):
        """ get data for FAQ slider template """
        response = http.Response(template='atharva_theme_base.as_dynamic_faq_container')
        return response.render()

    @http.route(['/get/get_product_offer_content'], type='json', auth='public', website=True)
    def get_product_offer_content(self, **kwargs):
        """Get data for Product Offer snippet"""
        values = {}
        prod_val = json.loads(kwargs.get("prod_ids"))
        domain = [('website_published', '=', True),('sale_ok', '=', True),('is_published','=',True),('id', '=', prod_val[0])]
        product = request.env['product.template'].sudo().search(domain)
        offerTime = kwargs.get('offerTime')
        pos = kwargs.get('imgPosition')
        ratings = kwargs.get('rating')
        cart = kwargs.get('cart')
        buyNow = kwargs.get('buyNow')
        product_label = kwargs.get('prodLabel')
        prod_label = False if product_label == "" else True
        prod_rating = False if ratings == "" else True
        prod_cart = False if cart == "" else True
        prod_buy = False if buyNow == "" else True
        tmplt = request.website.viewref("theme_alan.alan_product_offer_layout")
        values.update({'template': tmplt._render({'product': product, 'pos': pos, 'prod_label': prod_label, 'prod_buy': prod_buy,
                                                  'prod_rating': prod_rating, 'prod_cart': prod_cart}),
                        'offerTime': offerTime})
        return values