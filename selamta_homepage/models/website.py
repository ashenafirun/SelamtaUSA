# -*- coding: utf-8 -*-
import hashlib
import logging
from datetime import timedelta
from urllib.parse import quote

from lxml import etree, html as lxml_html

from odoo import api, fields, models, tools
from odoo.osv import expression

_logger = logging.getLogger(__name__)

# The homepage body is one website-builder area; its blocks are stored in a
# website-specific extension view, like the builder does when you click Save.
HOME_STRUCTURE_ID = 'oe_structure_selamta_home'
# Editable areas of the 1.1-1.4 layout, which no longer exist on the page.
OLD_STRUCTURE_IDS = [
    'oe_structure_selamta_hero_text', 'oe_structure_selamta_hero_photos',
    'oe_structure_selamta_why', 'oe_structure_selamta_how', 'oe_structure_selamta_cta',
]

# Homepage label, short description and preferred photo (product.template id)
# for each top-level eCommerce category, keyed by the category name in lower case.
# Categories are shown in this order; any other category with products comes after.
CATEGORY_HINTS = [
    ('spices flour grains', 'Spices, Flour & Grains', 'Berbere, mitmita, shiro, kolo', 1510),
    ('teff', 'Teff', 'Black & white teff flour, 25 lb', 1724),
    ('coffee and tea', 'Coffee & Tea', 'Tomoca coffee, Addis tea', 2577),
    ('beverages and biscuits', 'Beverages & Biscuits', 'Biscuits, cookies, drinks', 2568),
    ('coffee ceremony items', 'Coffee Ceremony', 'Rekebot sets, jebena, roasters', 1445),
    ('ceramic products', 'Ceramic Products', 'Coffee sets, dinnerware', 2058),
    ('clay products', 'Clay Products', 'Shekla pots, incense burners', 1560),
    ('handcraft', 'Handcraft', 'Mesob baskets, kebero, art', 1554),
    ('incense', 'Incense', 'Etan, bakhoor, burners', 1569),
    ('mix category', 'Household & More', 'Oils and everyday essentials', 1760),
]

BRANDS = [
    'Almi', 'Tomoca', 'Addis Tea', 'Girum Tea', 'Azmera', 'Ambo', 'Mulmul', 'Negus',
    'Tiru', 'Zenith', 'Nabeel', 'Nasaem', 'Seven Oceans', 'Abu Walad', 'Ziyad',
    'California Garden', 'Nido', 'Vimto', 'Mirinda',
]


class Website(models.Model):
    _inherit = 'website'

    # ------------------------------------------------------------------
    # Helpers used by the selamta_homepage QWeb templates
    # ------------------------------------------------------------------

    def _selamta_product_domain(self):
        self.ensure_one()
        return expression.AND([
            self.sale_product_domain(),
            [('is_published', '=', True)],
        ])

    def _selamta_product_card(self, product):
        """Plain dict for one product card. Prices only for signed-in users (B2B mode)."""
        self.ensure_one()
        url = product.website_url or '/shop'
        card = {
            'id': product.id,
            'name': (product.name or '').strip(),
            'url': url,
            'image': '/web/image/product.template/%d/image_512' % product.id,
            'login_url': '/web/login?redirect=%s' % quote(url, safe='/'),
            'price': False,
        }
        if not self.env.user._is_public():
            try:
                info = product._get_combination_info(only_template=True)
                currency = info.get('currency') or self.currency_id
                card['price'] = tools.format_amount(self.env, info['price'], currency)
            except Exception:  # never break the homepage over a price
                _logger.exception('selamta_homepage: could not compute price for product %s', product.id)
        return card

    @tools.ormcache('self.id', 'day')
    def _selamta_best_seller_ids(self, day):
        """Product template ids ordered by quantity sold over the last 365 days.
        Cached per website and per day."""
        date_from = fields.Datetime.now() - timedelta(days=365)
        groups = self.env['sale.report'].sudo()._read_group(
            [('date', '>=', date_from), ('state', '=', 'sale'), ('product_tmpl_id', '!=', False)],
            groupby=['product_tmpl_id'],
            aggregates=['product_uom_qty:sum'],
            order='product_uom_qty:sum desc',
            limit=60,
        )
        return tuple(tmpl.id for tmpl, _qty in groups)

    def _selamta_picked_products(self, section, limit=6):
        """Published products picked for a homepage section under
        Website > eCommerce > Products (Homepage Best Sellers / Homepage New Arrivals),
        in their drag-and-drop order. Empty when nothing usable is picked."""
        self.ensure_one()
        picked_ids = self.env['selamta.homepage.item'].sudo().search(
            [('section', '=', section)],
        ).mapped('product_tmpl_id').ids
        if not picked_ids:
            return self.env['product.template']
        visible = self.env['product.template'].search(
            expression.AND([self._selamta_product_domain(), [('id', 'in', picked_ids)]])
        )
        by_id = {p.id: p for p in visible}
        return self.env['product.template'].concat(*[by_id[pid] for pid in picked_ids if pid in by_id][:limit])

    def _selamta_auto_products(self, section, limit=6):
        """What a homepage section shows when its hand-picked list is empty:
        best sellers = most sold over the last 12 months, new arrivals = newest products."""
        self.ensure_one()
        Product = self.env['product.template']
        if section == 'best_sellers':
            ranked_ids = list(self._selamta_best_seller_ids(fields.Date.context_today(self)))
            if not ranked_ids:
                return Product
            products = Product.search(
                expression.AND([self._selamta_product_domain(), [('id', 'in', ranked_ids)]])
            )
            by_id = {p.id: p for p in products}
            return Product.concat(*[by_id[pid] for pid in ranked_ids if pid in by_id][:limit])
        return Product.search(
            self._selamta_product_domain(), order='create_date desc, id desc', limit=limit,
        )

    def _selamta_section_products(self, section, limit=6):
        """The hand-picked list when it has published products, otherwise the automatic one."""
        self.ensure_one()
        return self._selamta_picked_products(section, limit) or self._selamta_auto_products(section, limit)

    def _selamta_dynamic_product_card(self, data, is_sample=False):
        """Card dict for one record of Odoo's Products block (selamta card template)."""
        self.ensure_one()
        if is_sample:
            return {
                'id': 0, 'name': data.get('display_name') or 'Sample product', 'url': '#',
                'image': data.get('image_512') or '/web/image', 'login_url': '#', 'price': False,
            }
        record = data['_record']
        template = record.product_tmpl_id if record._name == 'product.product' else record
        return self._selamta_product_card(template)

    def _selamta_categories(self):
        self.ensure_one()
        Category = self.env['product.public.category']
        Product = self.env['product.template']
        categories = Category.search(
            [('parent_id', '=', False)] + self.website_domain(), order='sequence, id',
        )
        hints = {key: (label, subtitle, pid) for key, label, subtitle, pid in CATEGORY_HINTS}
        order = {key: index for index, (key, *_rest) in enumerate(CATEGORY_HINTS)}
        product_domain = self._selamta_product_domain()
        tiles = []
        for category in categories:
            key = (category.name or '').strip().lower()
            label, subtitle, preferred_id = hints.get(key, (category.name, '', False))
            in_category = expression.AND([product_domain, [('public_categ_ids', 'child_of', category.id)]])
            if not Product.search_count(in_category, limit=1):
                continue  # skip empty categories such as "Feature Product"
            if category.image_128:
                image = '/web/image/product.public.category/%d/image_512' % category.id
            else:
                photo = Product.browse()
                if preferred_id:
                    photo = Product.search(expression.AND([in_category, [('id', '=', preferred_id)]]), limit=1)
                if not photo:
                    photo = Product.search(in_category, order='website_sequence, id', limit=1)
                image = '/web/image/product.template/%d/image_512' % photo.id
            tiles.append({
                'sort': order.get(key, len(order)),
                'label': label,
                'subtitle': subtitle,
                'url': '/shop/category/%s' % self.env['ir.http']._slug(category),
                'image': image,
            })
        tiles.sort(key=lambda tile: tile['sort'])
        return tiles

    def _selamta_brand_records(self):
        """Brands of Website > eCommerce > Products > Product Brands (theme_alan),
        in their drag-and-drop order, or None without the theme's brand list."""
        self.ensure_one()
        if 'as.product.brand' not in self.env:
            return None
        return self.env['as.product.brand'].sudo().search(self.website_domain())

    def _selamta_brand_card(self, brand):
        """A brand with a logo shows the logo. The link opens the shop filtered by that
        brand when products are assigned to it, otherwise a shop search for its name."""
        self.ensure_one()
        Product = self.env['product.template']
        url = '/shop?search=%s' % quote(brand.name or '')
        if 'product_brand_id' in Product._fields and Product.search_count(
                expression.AND([self._selamta_product_domain(), [('product_brand_id', '=', brand.id)]]), limit=1):
            url = '/shop?brand=%d' % brand.id
        return {
            'name': brand.name,
            'url': url,
            'logo': '/web/image/as.product.brand/%d/image_256' % brand.id if brand.image_128 else False,
        }

    def _selamta_dynamic_brand_card(self, data, is_sample=False):
        """Card dict for one record of the brands Dynamic Content block."""
        self.ensure_one()
        if is_sample:
            return {'name': data.get('name') or 'Brand', 'url': '#', 'logo': False}
        return self._selamta_brand_card(data['_record'])

    @api.model
    def _selamta_ensure_brand_filter(self):
        """Filter "Product Brands (homepage)" for Odoo's Dynamic Content block. Created in
        code because the brand model comes from theme_alan, which this module does not
        depend on. Returns the filter, or an empty recordset without the brand model."""
        SnippetFilter = self.env['website.snippet.filter'].sudo()
        if 'as.product.brand' not in self.env:
            return SnippetFilter
        snippet_filter = self.env.ref('selamta_homepage.dynamic_filter_brands', raise_if_not_found=False)
        if snippet_filter:
            return snippet_filter.sudo()
        action = self.env['ir.actions.server'].sudo().create({
            'name': 'Selamta: Product Brands',
            'model_id': self.env['ir.model']._get_id('as.product.brand'),
            'state': 'code',
            'code': "response = model.env['website.snippet.filter']._selamta_get_brands()",
        })
        snippet_filter = SnippetFilter.create({
            'name': 'Product Brands (homepage)',
            'action_server_id': action.id,
            'field_names': 'name,image_256',
            'limit': 16,
        })
        # noupdate so module upgrades do not delete them as obsolete records
        self.env['ir.model.data'].sudo().create([
            {'module': 'selamta_homepage', 'name': 'snippet_action_brands', 'model': 'ir.actions.server',
             'res_id': action.id, 'noupdate': True},
            {'module': 'selamta_homepage', 'name': 'dynamic_filter_brands', 'model': 'website.snippet.filter',
             'res_id': snippet_filter.id, 'noupdate': True},
        ])
        return snippet_filter

    # ------------------------------------------------------------------
    # Homepage blocks (website builder content)
    # ------------------------------------------------------------------

    def _selamta_home_default_html(self):
        """The default homepage blocks for this website, rendered to static HTML."""
        self.ensure_one()
        website = self.with_context(website_id=self.id)
        brand_filter = website._selamta_ensure_brand_filter()
        values = {
            'sel_categories': website._selamta_categories(),
            'sel_best_filter_id': self.env.ref('selamta_homepage.dynamic_filter_best_sellers').id,
            'sel_new_filter_id': self.env.ref('selamta_homepage.dynamic_filter_new_arrivals').id,
            'sel_brand_filter_id': brand_filter.id or False,
            'sel_brand_links': [{'name': name, 'url': '/shop?search=%s' % quote(name)} for name in BRANDS],
        }
        return self.env['ir.qweb'].with_context(website_id=self.id, inherit_branding=False)._render(
            'selamta_homepage.home_default_content', values)

    def _selamta_home_content_arch(self):
        """Extension arch filling the homepage area with the default blocks, in the same
        shape the website builder saves (xpath replace of the oe_structure)."""
        self.ensure_one()
        fragment = lxml_html.fragment_fromstring(str(self._selamta_home_default_html()), create_parent='div')
        arch = etree.Element('data')
        xpath = etree.SubElement(arch, 'xpath', {
            'expr': "//*[hasclass('oe_structure')][@id='%s']" % HOME_STRUCTURE_ID,
            'position': 'replace',
        })
        structure = etree.SubElement(xpath, 'div', {'class': 'oe_structure', 'id': HOME_STRUCTURE_ID})
        structure.text = fragment.text
        for child in fragment:
            structure.append(child)
        return etree.tostring(arch, encoding='unicode')

    @api.model
    def _selamta_arch_hash(self, arch):
        return hashlib.sha1((arch or '').encode('utf-8')).hexdigest()

    @api.model
    def _selamta_home_ensure_content(self):
        """Install/upgrade: give every website the default homepage blocks, unless the
        page was already edited and saved in the website builder (then it is left alone)."""
        View = self.env['ir.ui.view'].sudo()
        Params = self.env['ir.config_parameter'].sudo()
        generic = self.env.ref('selamta_homepage.homepage').sudo()
        content_key = '%s_%s' % (generic.key, HOME_STRUCTURE_ID)
        View.with_context(active_test=False).search([
            ('key', 'in', ['%s_%s' % (generic.key, sid) for sid in OLD_STRUCTURE_IDS]),
        ]).unlink()
        for website in self.sudo().search([]):
            parent = View.search([('key', '=', generic.key), ('website_id', '=', website.id)], limit=1)
            if parent and HOME_STRUCTURE_ID not in (parent.arch_db or ''):
                # website copy still holding the old layout (saved in the builder before 1.5)
                parent.with_context(no_cow=True).write({'arch_db': generic.arch_db})
            parent = parent or generic
            content_view = View.search([('key', '=', content_key), ('website_id', '=', website.id)], limit=1)
            param = 'selamta_homepage.home_content_hash.%d' % website.id
            if content_view and Params.get_param(param) != self._selamta_arch_hash(content_view.arch_db):
                continue  # edited in the website builder: keep the customer's page
            arch = website._selamta_home_content_arch()
            if content_view:
                content_view.write({'arch': arch, 'inherit_id': parent.id})
            else:
                content_view = View.create({
                    'name': '%s (%s)' % (generic.name, HOME_STRUCTURE_ID),
                    'key': content_key,
                    'type': 'qweb',
                    'mode': 'extension',
                    'inherit_id': parent.id,
                    'website_id': website.id,
                    'arch': arch,
                })
            content_view.invalidate_recordset(['arch_db'])
            Params.set_param(param, self._selamta_arch_hash(content_view.arch_db))

    @api.model
    def _selamta_seed_brands(self):
        """Create the starter brand list once, only if the theme's brand list is empty,
        so it can then be reordered, edited or archived from Odoo."""
        if 'as.product.brand' not in self.env:
            return
        Brand = self.env['as.product.brand'].sudo().with_context(active_test=False)
        if Brand.search_count([]):
            return
        for index, name in enumerate(BRANDS):
            Brand.create({'name': name, 'sequence': (index + 1) * 10})
            # theme_alan's stored compute on as.product.brand (_get_logo) only works on one
            # record at a time, so flush after each create instead of creating in one batch.
            Brand.env.flush_all()
