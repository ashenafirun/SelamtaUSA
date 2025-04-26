# -*- coding: utf-8 -*-

import json
import ast
import random
import logging

from odoo import http, _
from odoo.http import request, route

_logger = logging.getLogger(__name__)

class ThemeAlan(http.Controller):

    @route('/get_hotspot_product', auth='public', type="json", website=True)
    def getHotSpotInfo(self, product_tmpl_id=0, style="st1"):
        product_id = request.env['product.template'].sudo().browse(int(product_tmpl_id))
        template = request.env['ir.ui.view']._render_template("theme_alan.as_img_hotspot_product_popover", {
            'product':product_id,
            'style':style,
        })
        return {'template':template}

    @http.route('/select/data/fetch', auth='user', type="http", website=True)
    def select2DataFetch(self, terms=False, searchIn=False, **kwargs):
        results = []
        parent_category = kwargs.get("parent_category", 0)
        website_domain = request.website.website_domain()
        if searchIn:
            searchIn = ast.literal_eval(searchIn)
            for search in searchIn:
                if parent_category:
                    kwargs.get("parent_category", 0)
                    domain = website_domain + [('parent_id','=',int(parent_category)),('name','ilike',terms)]
                    records = request.env[search].search(domain)
                else:
                    domain = website_domain + [('name','ilike',terms)]
                    if search in ["product.template", "blog.post"]:
                        domain += [('is_published','=',True)]
                    records = request.env[search].search(domain)
                for record in records:
                    if search == "product.public.category":
                        if parent_category:
                            data = { 'id':record.id, 'name':record.name, 'modal':search,
                            'img': request.website.image_url(record, "image_256") }
                            results.append(data)
                        else:
                            data = { 'id':record.id, 'name':record.name, 'modal':search ,
                            'img': request.website.image_url(record, "image_256")}
                            results.append(data)
                    elif search == "blog.post":
                        data = { 'id':record.id, 'name':record.display_name, 'modal':search ,
                                'img': request.website.image_url(record, "author_avatar")}
                        results.append(data)
                    else:
                        data = { 'id':record.id, 'name':record.display_name, 'modal':search ,
                                'img': request.website.image_url(record, "image_256")}
                        results.append(data)

        return json.dumps(results)

    @route('/get_megamenu_snippet_template', auth='public', type="json", website=True)
    def getMegamenuSnippets(self, **kw):
        website = request.website
        website_domain = request.website.website_domain()
        snippet_type = kw.get("snippet", False)
        return_context = {}
        context = {}
        slider_config = {}

        if snippet_type:
            modal = kw.get("modal", False)
            configuration = kw.get("design_editor",{})

            col_item = int(configuration.get("col_item",4))

            if modal:
                if modal == "product.template":
                    website_domain += [('is_published','=',True)]

                ids = kw.get("record_ids",[0])
                get_default_record_ids = False

                if ids == [0]:
                    get_default_record_ids = request.env[modal].search(website_domain, limit=15)

                if configuration.get("active_view",False) == 'slider':
                    style = configuration.get("slider_style",'')
                    slider_config = {
                        'slidesPerView': 1.5,
                        'spaceBetween': 20,
                        'pagination': {
                        'el': ".swiper-pagination",
                            'clickable': True,
                        },
                        'breakpoints': {
                            767: {
                            'slidesPerView': 2,
                            },
                            1024: {
                            'slidesPerView': col_item,
                            },
                        },
                        'navigation': {
                            'nextEl': ".swiper-button-next",
                            'prevEl': ".swiper-button-prev",
                        },
                    }
                    if configuration.get("auto_slider",False):
                        slider_config.update({'autoplay': {'delay': int(configuration.get('slider_time',4)) * 1000}})
                else:

                    style = configuration.get("grid_style",'')
                    if col_item == 0:
                        col_item = 4

                    col_item = int(12 / col_item)

                if snippet_type in ["MegaMenuProduct", "megamenu_products","MegaMenuBrand", "megamenu_brand"]:
                    if get_default_record_ids:
                        record_ids = get_default_record_ids
                    else:
                        record_ids = request.env[modal].browse(ids)

                    context.update({'data':record_ids})
                    return_context.update({'record_ids':[i.id for i in record_ids]})
                elif snippet_type in ["MegaMenuCategory", "megamenu_category"]:
                    data = {}
                    sub_data = {}
                    extra_info = configuration.get("extra_info")

                    if get_default_record_ids:
                        record_ids = get_default_record_ids
                    else:
                        record_ids = request.env[modal].browse(ids)

                    if extra_info:
                        for cats in extra_info:
                            parent_id = request.env[modal].browse(cats['parent'])
                            child_ids = []
                            lst = [int(i) for i in cats['childs']]
                            if len(lst):
                                child_ids = request.env[modal].browse(lst)
                            sub_data.update({parent_id: child_ids})

                        for rec in record_ids:
                            parent_id = request.env[modal].browse([rec])

                            if rec in sub_data.keys():

                                data.update({rec: sub_data[rec]})
                            else:
                                data.update({rec: []})

                    else:
                        for rec in record_ids:

                            if rec in sub_data.keys():
                                data.update({rec: sub_data[rec]})
                            else:
                                data.update({rec: []})
                    # cat_ids = request.env[modal].browse(record_ids)
                    context.update({'data':data})
                    return_context.update({'record_ids':[i.id for i in record_ids]})



                template = False
                context.update({'style':style, 'col_item':col_item})

                if configuration.get("allow_link", False):
                    context.update({'allow_link':True})

                template = request.env['ir.ui.view']._render_template(configuration.get('template_id'), context)
                return_context.update({'template':template ,'slider_config':slider_config})

            return return_context

    @route('/get_snippet_template', auth='public', type="json", website=True)
    def getProductSnippets(self, **kw):
        website = request.website
        website_domain = request.website.website_domain()
        snippet_type = kw.get("snippet", False)
        return_context = {}
        context = {}
        slider_config = {}
        if snippet_type:
            modal = kw.get("modal", False)
            configuration = kw.get("design_editor",{})

            if modal:
                if modal == "product.template":
                    website_domain += [('is_published','=',True)]

                ids = kw.get("record_ids",[0])
                get_default_record_ids = False

                if ids == [0]:
                    get_default_record_ids = request.env[modal].search(website_domain, limit=15)

                if snippet_type in ["BestSellingProduct", "LatestProduct", "products", "product_banner", "ProductBanner", "ProductSlider"]:
                    if get_default_record_ids:
                        record_ids = get_default_record_ids
                    else:
                        record_ids = request.env[modal].browse(ids)
                    return_context.update({'record_ids':[i.id for i in record_ids]})

                elif snippet_type in ["BrandProduct", "brand_products"]:
                    if get_default_record_ids:
                        tab_ids = get_default_record_ids
                        domain = website_domain + [('product_brand_id', 'in', tab_ids.ids)]
                    else:
                        tab_ids = request.env[modal].browse(ids)
                        domain = website_domain + [('product_brand_id', 'in', ids)]

                    # record_ids = request.env['product.template'].search(domain)
                    record_ids = tab_ids
                    return_context.update({'record_ids':[i.id for i in record_ids]})
                    context.update({'tab_ids':tab_ids})

                elif snippet_type in ["CategoryProduct", "categories_products"]:
                    if get_default_record_ids:
                        tab_ids = get_default_record_ids
                        domain = website_domain + [('public_categ_ids', 'in', tab_ids.ids)]
                    else:
                        tab_ids = request.env[modal].browse(ids)
                        domain = website_domain + [('public_categ_ids', 'in', ids)]
                    # record_ids = request.env['product.template'].search(domain)
                    record_ids = tab_ids
                    return_context.update({'record_ids':[i.id for i in record_ids]})
                    context.update({'tab_ids':tab_ids})

                elif snippet_type in ["CategorySlider", "categories"]:
                    if get_default_record_ids:
                        category_ids = get_default_record_ids
                        domain = website_domain + [('public_categ_ids', 'in', category_ids.ids)]
                    else:
                        category_ids = request.env[modal].browse(ids)
                        domain = website_domain + [('public_categ_ids', 'in', ids)]

                    record_ids = request.env[modal].browse(category_ids.ids)
                    return_context.update({'record_ids':[i.id for i in record_ids]})

                elif snippet_type in ["BrandSlider", "brands"]:
                    if get_default_record_ids:
                        brand_ids = get_default_record_ids
                        domain = website_domain + [('product_brand_id', 'in', brand_ids.ids)]
                    else:
                        brand_ids = request.env[modal].browse(ids)
                        domain = website_domain + [('product_brand_id', 'in', ids)]

                    record_ids = request.env[modal].browse(brand_ids.ids)
                    return_context.update({'record_ids':[i.id for i in record_ids]})

                else:
                    if modal == "blog.post":
                        if get_default_record_ids:
                            record_ids = get_default_record_ids
                        else:
                            record_ids = request.env[modal].browse(ids)
                        if not request.env.user._is_internal():
                            record_ids = [blog for blog in record_ids if blog.sudo().is_published == True]
                    else:
                        if get_default_record_ids:
                            record_ids = get_default_record_ids
                        else:
                            record_ids = request.env[modal].browse(ids)
                    return_context.update({'record_ids':[i.id for i in record_ids]})

                template = False
                slider_config = {}
                context.update({'records':record_ids, 'configuration':configuration })

                template = request.env['ir.ui.view']._render_template(configuration.get('template_id'), context)
                # slider config
                return_context.update({'template':template ,'slider_config':slider_config})
                if configuration.get("active_view",False) == 'slider':
                    slider_config.update({
                        'loop':configuration.get("loop"),
                        'spaceBetween': 15,
                        'slidesPerView': configuration.get("default_col_mob"),
                        'navigation': {
                            'nextEl': ".swiper-button-next",
                            'prevEl': ".swiper-button-prev",
                        },
                        'breakpoints': {
                            640: {
                            'slidesPerView': configuration.get("default_col_mob"),
                            },
                            768: {
                            'slidesPerView': configuration.get("default_col_mob"),
                            },
                            1024: {
                            'slidesPerView': configuration.get("default_col_desk"),
                            },
                            1200: {
                            'slidesPerView': configuration.get("default_col_desk"),
                            },
                        },
                        'observer': True,
                        'observeSlideChildren': True,
                        'observeParents': True,
                    })
                    if configuration.get("auto_slider"):
                        slider_config.update({
                            'autoplay':{ 'delay': int(configuration.get("slider_time")) * 1000,
                                        'disableOnInteraction':False }
                        })
                    if configuration.get("pagination"):
                        pagination_style = {}
                        if configuration.get("pagination") == 'simple':
                            pagination_style = {
                                'el': ".swiper-pagination"
                            }
                        elif configuration.get("pagination") == 'dynamic':
                            pagination_style = {
                                'el': ".swiper-pagination",
                                'dynamicBullets': True,
                            }
                        elif configuration.get("pagination") == 'progress_bar':
                            pagination_style = {
                                'el': ".swiper-pagination",
                                'type': "progressbar",
                            }
                        elif configuration.get("pagination") == 'fraction':
                            pagination_style = {
                                'el': ".swiper-pagination",
                                'type': "fraction",
                            }
                        elif configuration.get("pagination") == 'scroll_bar':
                            pagination_style = {
                                'el': ".swiper-scrollbar",
                                'hide': True,
                            }
                        elif configuration.get("pagination") == 'coverflow':
                            pagination_style = {
                                'el': ".swiper-pagination",
                            }
                            slider_config.update({
                                "effect": "coverflow",
                                "grabCursor": True,
                                "centeredSlides": True,
                            })
                        elif configuration.get("pagination") == 'cards':
                            slider_config.update({
                                "effect": "cards",
                                "grabCursor": True,
                                "centeredSlides": True,
                            })
                        if configuration.get("pagination") == 'scroll_bar':
                            slider_config.update({'scrollbar':pagination_style })
                        else:
                            slider_config.update({'pagination':pagination_style })
                    return_context.update({'slider_config':slider_config})
                return return_context

    def sort_records(self, modal, sort, limit, domain, random_record=False):
        if modal in ["product.template", "blog.post"]:
            domain += [('is_published','=',True)]
        if sort:
            records = request.env[modal].search(domain, limit=limit, order=sort)
        else:
            if random_record:
                records = request.env[modal].search(domain)
                rec_lst = [{"id": rec.id, "display_name":rec.display_name,
                    "image": request.website.image_url(rec,"image_1024") }
                    for rec in records ]
                random.shuffle(rec_lst)
                return rec_lst[:16]
            else:
                records = request.env[modal].search(domain, limit=limit )
        return records

    @route('/get_quick_record', auth='public', type="json", website=True)
    def getQuickRecords(self, mode=False, model=False):
        website = request.website
        limit = 15
        from_date = 182
        website_domain = request.website.website_domain()
        records = [0]
        if model == "product.template":
            website_domain += [('is_published','=',True)]
        if model:
            if mode == "latest_product":
                records = self.sort_records(model, 'create_date DESC', limit, website_domain)
            elif mode == "top_related":
                records = self.sort_records(model, 'product_rating DESC', limit, website_domain)
            elif mode == "best_seller":
                records = request.env[model]._get_best_seller_product(from_date, website.id, limit)
            elif mode == "parent_category":
                website_domain = website_domain + [('parent_id','=', False)]
                records = self.sort_records(model, False, limit, website_domain)
            elif mode == "a_to_z":
                records = self.sort_records(model, 'name ASC', limit, website_domain)
            elif mode == "z_to_a":
                records = self.sort_records(model, 'name DESC', limit, website_domain)
            elif mode == "random":
                records = request.env[model].search(website_domain, limit=4)

        return [{"id": product_info.id, "display_name":product_info.display_name,
            "image": request.website.image_url(product_info,"image_1024") }
            for product_info in records ]


    @route('/get_records_details', auth='public', type="json", website=True)
    def getDetailsInfos(self, record_ids=[], model=False):
        if record_ids and model:
            record_ids = [int(i) for i in record_ids]
            rec_info = request.env[model].browse(record_ids)
            if model == "blog.post":
                return [{"id": rec.id, "display_name":rec.display_name,
                    "name":rec.name,
                    "image": request.website.image_url(rec,"author_avatar") }
                    for rec in rec_info ]
            else:
                return [{"id": rec.id, "display_name":rec.display_name,
                    "name":rec.name,
                    "image": request.website.image_url(rec,"image_1024") }
                    for rec in rec_info ]