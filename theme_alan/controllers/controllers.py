# -*- coding: utf-8 -*-

import odoo
import datetime
import ast
import logging
import json

from odoo.http import request, route
from odoo import http, _, fields
from markupsafe import Markup

from odoo.exceptions import UserError
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db
from odoo.addons.website.controllers.main import Website
from odoo.addons.auth_oauth.controllers.main import OAuthLogin
from odoo.addons.auth_signup.models.res_users import SignupError
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.variant import WebsiteSaleVariantController
from odoo.addons.website_sale.controllers.product_configurator import ( WebsiteSaleProductConfiguratorController)

CREDENTIAL_PARAMS = ['login', 'password', 'type']

_logger = logging.getLogger(__name__)

class WebsiteSaleAlanShop(WebsiteSale):

    @route()
    def product(self, product, category='', search='', **kwargs):
        res = super(WebsiteSaleAlanShop, self).product(product, category, search, **kwargs)
        res.qcontext.update({'as_product_detail': True})
        domain = request.website.sale_product_domain() + [('active', '=', True),('website_published', '=', True)]
        prod_ids = product.search(domain, order="website_sequence").mapped("id")
        previous_product = next_product = False
        if product.id in prod_ids:
            current_idx = prod_ids.index(product.id)
            if current_idx < len(prod_ids) - 1:
                next_product = product.browse(prod_ids[current_idx + 1])
            if current_idx > 0:
                previous_product = product.browse(prod_ids[current_idx - 1])
            res.qcontext.update({'next_product': next_product, 'previous_product': previous_product})
        return res

    @http.route(['/product_queries'], type="json", auth='public', website=True)
    def product_queries(self, **kw):
        user = request.env.user.sudo()
        user_obj = user.partner_id.sudo()
        now = datetime.datetime.now()
        product_id = kw.get('product_id')
        product = request.env['product.template'].sudo().search([('id', '=', product_id)])
        inquiry_data = ast.literal_eval(user.inquiry_data or '{}')
        dialog_header = request.website.inquiry_header
        dialog_header_desc = request.website.inquiry_desc_info
        acknowledgement_message = request.website.acknowledgement_message
        context = {
            'user_id': user_obj.id,
            'user_name': user_obj.name,
            'user_email': user_obj.email,
            'dialog_header': dialog_header,
            'dialog_header_desc': dialog_header_desc,
            'acknowledgement_message': acknowledgement_message,
        }
        if not inquiry_data:
            return context
        product_inquiry_time = inquiry_data.get(str(product.id))
        if product_inquiry_time:
            date_time_compare = datetime.datetime.strptime(product_inquiry_time, "%Y-%m-%d %H:%M:%S.%f")
            if date_time_compare >= now:
                return False
        return context

    @http.route(['/send_queries_mail'], type="json", auth='public', website=True)
    def product_queries_send_mail(self,**kw):
        template = request.env.ref('theme_alan.email_template_product_queries')
        partner_id = request.env['res.partner'].sudo().search([['id', '=',kw.get('user_id')]])
        res_config = request.website.inquiry_submit_action
        user_question = kw.get('message')
        user_email =  kw.get('email')
        product_id = kw.get('product_id')
        contact_preference = kw.get('contact_preference')
        product = request.env['product.template'].sudo().search([('id','=',product_id)])
        user = request.env.user.sudo()
        now = datetime.datetime.now()
        product_id = product.id
        time_after_24_hours = now + datetime.timedelta(hours=24)
        inquiry_data = ast.literal_eval(user.inquiry_data or '{}')

        if str(product.id) in list(inquiry_data.keys()):
            produt_date_time_update = {str(product_id): str(time_after_24_hours)}
            inquiry_data.update(produt_date_time_update)
            user.inquiry_data = inquiry_data
        else:
            inquiry_data[product_id] = str(time_after_24_hours)
            updated_inquiry_data = json.dumps(inquiry_data)
            user.inquiry_data = updated_inquiry_data

        if contact_preference  == "Both":
            contact_preference = "Email OR Phone"

        crm_description = Markup('<h3>Product Inquiry - Your Assistance Needed</h3><br/><div>Product Name : %s</div><div>Question : %s</div><div>Contact Preference : %s</div>') % (product.name,user_question,contact_preference)

        if res_config == 'crm':
            sales_team_id = request.website.sales_team_id
            sales_person_id = request.website.sales_person_id
            if sales_team_id and sales_person_id:
                request.env['crm.lead'].sudo().create({
                'team_id':sales_team_id.id,
                'name': 'Product Inquiry',
                'email_from': user_email,
                'user_id':sales_person_id.id,
                'partner_id':partner_id.id,
                'description':crm_description,
            })

        if template and res_config == 'email':
            user_id = request.website.sudo().inquiry_recipient_id
            composer = request.env['mail.compose.message'].sudo().with_context(
                    message = user_question,
                    product = product.name,
                    partner_name = user_id.partner_id.name,
                    contact_preference = contact_preference,
                    default_force_send = True,
                    default_composition_mode = 'mass_mail',
                    default_model = 'res.partner',
                    default_res_ids = user_id.partner_id.ids,
                    default_template_id = template.id,
                    email_to = user_id.partner_id.email,
                    default_is_queries_mail = True
                ).create({
                    'message_type':'comment',
                })
            composer.sudo()._action_send_mail()

    @route('/advance/info/editor/<model("as.product.extra.info"):offer>', auth='user', type="http", website=True)
    def offer_design(self, offer):
        return request.render('theme_alan.as_product_advance_info_design', {'layout': offer})

class WebsiteSaleAlanVariant(WebsiteSaleVariantController):

    @route()
    def get_combination_info_website(self, *args, **kwargs):
        res = super().get_combination_info_website(*args, **kwargs)
        res.update({'bulk_save': False})
        if "product_id" in res.keys():
            product_id = request.env['product.product'].sudo().browse(res.get("product_id", 0))
            current_pricelist = request.website._get_current_pricelist()
            if current_pricelist:
                pricelist_item_ids = current_pricelist.sudo()._get_applicable_rules(product_id, fields.Date.today())
                template = request.env['ir.ui.view']._render_template("theme_alan.bulk_save_offers",{
                            'product': product_id,
                            'pricelist_item_ids': pricelist_item_ids })

                get_offer_date = product_id._get_offer_timing(current_pricelist)
                res.update({'bulk_save': template, 'offer_timer':get_offer_date})
            product_count =  product_id.get_sale_count_last_month()
            last_month_template =  request.env['ir.ui.view']._render_template("theme_alan.last_month_sold",{
                            'product_count': product_count})
            res.update({'default_code':product_id.default_code, 'last_month_count': last_month_template})
        return res


class LoginPopup(Home):

    @route('/get_login_popup', type='json', auth="public", website=True)
    def alan_login_popup(self, **kwargs):
        context = {}
        providers = OAuthLogin.list_providers(self)
        context.update(super().get_auth_signup_config())
        context.update({'providers':providers})
        signup_enabled = request.env['res.users']._get_signup_invitation_scope() == 'b2c'
        reset_password_enabled = request.env['ir.config_parameter'].sudo().get_param('auth_signup.reset_password') == 'True'
        website_logo = request.website.image_url(request.website,'logo')
        context.update({'signup_enabled':signup_enabled ,"reset_password_enabled":reset_password_enabled,'website_logo':website_logo})
        return context

    @route('/alan/login/authenticate', type='json', auth="none")
    def alan_login_authenticate(self, **kwargs):
        ''' Login Authentication '''
        ensure_db()
        request.params['login_success'] = False
        if not request.uid:
            request.update_env(user=odoo.SUPERUSER_ID)
        values = request.params.copy()
        if request.httprequest.method == 'POST':
            try:
                credential = {key: value for key, value in request.params.items() if key in CREDENTIAL_PARAMS}
                credential.setdefault('type', 'password')
                auth_info = request.session.authenticate(request.db, credential)
                request.params['login_success'] = True
                request.redirect(self._login_redirect(auth_info['uid'], redirect=None))
                return request.params
            except odoo.exceptions.AccessDenied as e:
                if e.args == odoo.exceptions.AccessDenied().args:
                    values['error'] = _("Wrong login/password")
                else:
                    values['error'] = e.args[0]
        if 'login' not in values and request.session.get('auth_login'):
            values['login'] = request.session.get('auth_login')

        return values

    @route('/alan/signup/authenticate', type="json", auth="public")
    def alan_signup_authenticate(self,*args, **kw):
        ''' Signup Authentication '''
        qcontext = super(LoginPopup,self).get_auth_signup_qcontext()
        if 'error' not in qcontext and request.httprequest.method == 'POST':
            try:
                super(LoginPopup,self).do_signup(qcontext)
                User = request.env['res.users']
                user_sudo = User.sudo().search(
                    User._get_login_domain(qcontext.get('login')), order=User._get_login_order(), limit=1
                )
                template = request.env.ref('auth_signup.mail_template_user_signup_account_created', raise_if_not_found=False)
                if user_sudo and template:
                    template.sudo().send_mail(user_sudo.id, force_send=True)
                return {'signup_success':True}
            except UserError as e:
                qcontext['error'] = e.args[0]
            except (SignupError, AssertionError) as e:
                if request.env['res.users'].sudo().search([('login', '=', qcontext.get('login'))]):
                    qcontext['error'] = _('Another user is already registered using this email address.')
                else:
                    _logger.error("%s", e)
                    qcontext['error'] = _('Could not create a new account.')
        return qcontext

class B2BWebsite(Website):

    @route()
    def autocomplete(self, search_type=None, term=None, order=None, limit=5, max_nb_chars=999, options=None):
        result = super().autocomplete(search_type, term, order, limit, max_nb_chars, options)
        if request.env.user._is_public() and request.website.active_b2b_mode:
            result['parts']['is_b2b_mode'] = True
        else:
            result['parts']['is_b2b_mode'] = False
        return result

    @route()
    def hybrid_list(self, page=1, search='', search_type='all', **kw):
        result = super().hybrid_list(page, search, search_type, **kw)
        if request.env.user._is_public() and request.website.active_b2b_mode:
            result.qcontext['is_b2b_mode'] = True
        else:
            result.qcontext['is_b2b_mode'] = False
        return result

class AlanShops(http.Controller):

    @route(['/shop/brands', '/shop/brands/page/<int:page>'], type='http', auth="public", website=True)
    def BrandPage(self, page=0):
        domain = ['&',('active','=',True), ('website_id', 'in', (False, request.website.id))]
        brands = request.env['as.product.brand'].sudo().search(domain, order="name asc")
        total = brands.sudo().search_count([])
        pager = request.website.pager(
            url='/shop/brands',
            total=total,
            page=page,
            step=30,
        )
        offset = pager['offset']
        brands = brands[offset: offset + 30]
        return request.render("theme_alan.brand_list", {'brands':brands, 'pager': pager})

    def format_amount(self, amount):
        price_list = request.env['website'].get_current_website().pricelist_id.sudo().currency_id
        return f"{price_list.symbol} {amount:.2f}"

    @route('/get_mini_cart', auth='public', type="json", website=True)
    def mini_cart(self, **kw):
        website = request.env['website'].get_current_website()
        order = request.website.sale_get_order()
        suggested_products = order.sudo()._cart_accessories()
        as_free_shipping_details = order.sudo().get_shipping_details()
        # Product lines
        def format_product_line(line):
            return {
                'line_id': line.id,
                'product_id': line.product_id.id,
                'product_tmp_id': line.product_id.product_tmpl_id.id,
                'image_url': f"/web/image/product.product/{line.product_id.id}/image_512",
                'website_url': line.product_id.website_url,
                'discount': line.discount,
                'price_total': line.price_total,
                'display_name': line.product_id.with_context(display_default_code=False).display_name,
                'product_uom_qty': line.product_uom_qty,
                'description_sale': line.get_description_following_lines(),
                'formated_amount': self.format_amount(line.price_total),
            }

        # Suggested Product lines
        def format_suggested_product_line(prod):
            combination_info = prod._get_combination_info_variant()
            return {
                'product_id': prod.id,
                'product_name': prod.name,
                'has_discounted_price': combination_info['has_discounted_price'],
                'list_price': self.format_amount(combination_info['list_price']),
                'price': self.format_amount(combination_info['price']),
                'image_url': f"/web/image/product.product/{prod.id}/image_512",
                'website_url': prod.website_url,
            }

        website_order_lines = [format_product_line(line) for line in order.website_order_line]
        suggested_products_lines = [format_suggested_product_line(prod) for prod in suggested_products]

        # Cart summary
        cart_summary = {
            'reward_amount': self.format_amount(order.reward_amount) if order.reward_amount else 0,
            'carrier_id': order.carrier_id.id,
            'amount_delivery': self.format_amount(order.amount_delivery),
            'amount_untaxed': self.format_amount(order.amount_untaxed),
            'amount_tax': self.format_amount(order.amount_tax),
            'amount_total': self.format_amount(order.amount_total),
            'shipping_detail': {}
        }
        if as_free_shipping_details:
            cart_summary.update({
                'shipping_detail': {
                    'any_ns_product': as_free_shipping_details['any_ns_product'],
                    'carries_amount': as_free_shipping_details['carries_amount'],
                    'total_amount':as_free_shipping_details['total_amount'],
                    'status': as_free_shipping_details['status'],
                    'pending_amount': self.format_amount(as_free_shipping_details['pending_amount']),
                    'active_free_shipping': request.website.active_free_shipping,
                    }
                })

        context = {
            'cart_quantity': order.cart_quantity,
            'website_order_lines': website_order_lines,
            'suggested_products': suggested_products_lines,
            'cart_summary': cart_summary
        }
        return context

    @route('/as_clear_cart', type="json", auth="public", website=True)
    def as_clear_cart(self, **kw):
        order = request.website.sale_get_order()
        request.session['website_sale_cart_quantity'] = 0
        order.unlink()

    @route('/as_get_quick_view_templates', type="json", auth="public", website=True)
    def get_rating_template(self, **kw):

        website = request.website
        product_tmpl_id = request.env['product.template'].sudo().browse(kw.get('product_tmpl_id'))
        product_id = request.env['product.product'].sudo().browse(kw.get('product_id'))

        # Rating
        review_count = product_tmpl_id.rating_count
        rating_text = ("%d reviews" % review_count) if review_count > 1 else "%d review" % review_count

        # categories
        categories = product_tmpl_id.public_categ_ids.filtered(lambda x: x.website_id == website or not x.website_id).mapped('name')
        category_template = f"<div class='as-pd-cat-list as-pd-lists'><label>Category: </label> <span>{', '.join(categories)}</span></div>" if categories and website.active_product_category else ""

        # SKU Template
        sku_template = f" <div class='as_product_sku as-pd-lists'><label>SKU: </label><span>{product_id.default_code}</span></div>" if product_id.default_code and website.active_product_reference else ""

        # Bulk save view
        bulk_save_view = ""
        current_pricelist = website._get_current_pricelist()
        if current_pricelist:
            pricelist_item_ids = current_pricelist.sudo()._get_applicable_rules(product_id, fields.Date.today())
            if website.active_product_bulk_save and pricelist_item_ids:
                bulk_save_view = request.env['ir.ui.view']._render_template(
                    "theme_alan.bulk_save_offers", {'product': product_tmpl_id, 'pricelist_item_ids': pricelist_item_ids}
                )

        # Product comparison
        comparison_view = website.is_view_active('website_sale_comparison.product_add_to_compare')
        product_variant_id = product_tmpl_id.sudo()._get_first_possible_variant_id()
        show_compare = bool(categories and product_variant_id and comparison_view)
        render_if_active = website.is_view_active

        # Product Advance Info
        offer_ids = product_tmpl_id.product_offer_ids
        advance_info = {}

        for offer in offer_ids:
            if offer.types == 'offer' and website.active_product_advance_info:
                advance_info[offer.id] = {
                    'id':offer.id,
                    'name': offer.name,
                    'short_description': offer.short_description,
                    'icon': offer.icon
                }
        values = {
            'rating_template': render_if_active('website_sale.product_comment') and request.env['ir.ui.view']._render_template(
                "portal_rating.rating_widget_stars_static", {'rating_avg': product_tmpl_id.rating_avg, 'rating_count': rating_text}
            ) or "",
            'sale_count': product_id.get_sale_count_last_month(),
            'bulk_save_view': bulk_save_view,
            'show_compare': show_compare,
            'show_wishlist': render_if_active('website_sale_wishlist.product_add_to_wishlist'),
            'show_buy_now': render_if_active('website_sale.product_buy_now'),
            'category_template': category_template,
            'sku_template': sku_template,
            'tag_template': render_if_active('website_sale.product_tags') and request.env['ir.ui.view']._render_template(
                "website_sale.product_tags", {'all_product_tags': product_id.all_product_tag_ids}
            ) or "",
            'brand_template': request.env['ir.ui.view']._render_template("theme_alan.as_product_brand_info", {'product': product_tmpl_id}),
            'active_b2b_mode': bool(website.active_b2b_mode and request.env.user._is_public()) ,
            'active_login_popup': website.active_login_popup,
            'active_offer_timer': website.active_product_offer_timer,
            'offer_timing': product_id._get_offer_timing(website._get_current_pricelist()),
            'advance_info':advance_info
        }

        return values

    @route('/get_alan_configuration', auth='public', type="json", website=True)
    def get_alan_configuration(self, **kw):
        website = request.website
        data = {
            'active_login_popup':website.active_login_popup,
            'active_mini_cart':website.active_mini_cart,
            'active_scroll_top':website.active_scroll_top,
            'active_b2b_mode':website.active_b2b_mode,

            'active_shop_quick_view': website.active_shop_quick_view,
            'active_shop_rating': website.active_shop_rating,
            'active_shop_similar_product': website.active_shop_similar_product,
            'active_shop_offer_timer': website.active_shop_offer_timer ,
            'active_shop_color_variant': website.active_shop_color_variant,
            'active_shop_stock_info': website.active_shop_stock_info,
            'active_shop_brand_info': website.active_shop_brand_info,
            'active_shop_hover_image':website.active_shop_hover_image,
            'active_shop_label':website.active_shop_label,
            'active_shop_clear_filter':website.active_shop_clear_filter,
            'active_shop_ppg':website.active_shop_ppg,
            'active_stock_only':website.active_stock_only,
            'active_load_more':website.active_load_more,
            'active_brand_filter':website.active_brand_filter,
            'active_rating_filter':website.active_rating_filter,
            'active_attribute_count':website.active_attribute_count,
            'active_attribute_search':website.active_attribute_search,
            'active_hide_zero_attribute':website.active_hide_zero_attribute,
            'active_shop_product_reference':website.active_shop_product_reference,

            'active_product_label':website.active_product_label,
            'active_product_offer_timer':website.active_product_offer_timer,
            'active_product_reference':website.active_product_reference,
            'active_product_category':website.active_product_category,
            'active_product_brand':website.active_product_brand,
            'active_product_advance_info':website.active_product_advance_info,
            'active_product_variant_info':website.active_product_variant_info,
            'active_product_accessory':website.active_product_accessory,
            'active_product_alternative':website.active_product_alternative,
            'active_product_pager':website.active_product_pager,
            'active_product_sticky':website.active_product_sticky,
            'active_product_bulk_save':website.active_product_bulk_save,
            'active_last_month_count': website.active_last_month_count,
            'active_product_inquiry': website.active_product_inquiry,
            'active_product_discount': website.active_product_discount,
            'active_free_shipping':website.active_free_shipping,
        }
        return data

    @route('/set_alan_configuration', auth='public', type="json", website=True)
    def set_alan_configuration(self, is_active, setting):
        request.website.write({ setting: is_active })
        return True

    @route('/get_advance_info', auth='public', type="json", website=True)
    def get_advance_info(self, advance_info_id):
        offer = request.env['as.product.extra.info'].sudo().search([('id','=',advance_info_id)], limit=1)
        if offer.detail_description:
            return offer.detail_description
        return ""

class WebsiteSaleStockProductConfiguratorController(WebsiteSaleProductConfiguratorController):

    def _get_product_information(
        self,
        product_template,
        combination,
        currency,
        pricelist,
        so_date,
        quantity=1,
        product_uom_id=None,
        parent_combination=None,
        **kwargs,
    ):
        product_uom = request.env['uom.uom'].browse(product_uom_id)
        product = product_template._get_variant_for_combination(combination)
        attribute_exclusions = product_template._get_attribute_exclusions(
            parent_combination=parent_combination,
            combination_ids=combination.ids,
        )
        product_or_template = product or product_template
        try:
            show_variant_info = request.website.active_product_variant_info
        except:
            show_variant_info = False
        return dict(
            product_tmpl_id=product_template.id,
            **self._get_basic_product_information(
                product_or_template,
                pricelist,
                combination,
                quantity=quantity,
                uom=product_uom,
                currency=currency,
                date=so_date,
                **kwargs,
            ),
            quantity=quantity,
            attribute_lines=[dict(
                id=ptal.id,
                attribute=dict(**ptal.attribute_id.read(['id', 'name', 'display_type', 'attribute_extra_info_id'])[0]),
                attribute_values=[
                    dict(
                        **ptav.read(['name', 'html_color', 'image', 'is_custom'])[0],
                        price_extra=self._get_ptav_price_extra(
                            ptav, currency, so_date, product_or_template
                        ),
                    ) for ptav in ptal.product_template_value_ids
                    if ptav.ptav_active or combination and ptav.id in combination.ids
                ],
                selected_attribute_value_ids=combination.filtered(
                    lambda c: ptal in c.attribute_line_id
                ).ids,
                active_product_variant_info = show_variant_info,
                create_variant=ptal.attribute_id.create_variant,
            ) for ptal in product_template.attribute_line_ids],
            exclusions=attribute_exclusions['exclusions'],
            archived_combinations=attribute_exclusions['archived_combinations'],
            parent_exclusions=attribute_exclusions['parent_exclusions'],
        )

class B2BWebsite(Website):
    @route()
    def autocomplete(self, search_type=None, term=None, order=None, limit=5, max_nb_chars=999, options=None):
        result = super().autocomplete(search_type, term, order, limit, max_nb_chars, options)
        if request.env.user._is_public() and request.website.active_b2b_mode:
            result['parts']['is_b2b_mode'] = True
        else:
            result['parts']['is_b2b_mode'] = False
        return result
    @route()
    def hybrid_list(self, page=1, search='', search_type='all', **kw):
        result = super().hybrid_list(page, search, search_type, **kw)
        if request.env.user._is_public() and request.website.active_b2b_mode:
            result.qcontext['is_b2b_mode'] = True
        else:
            result.qcontext['is_b2b_mode'] = False
        return result
