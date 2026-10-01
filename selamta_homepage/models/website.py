# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from urllib.parse import quote

from odoo import fields, models, tools
from odoo.osv import expression

_logger = logging.getLogger(__name__)

# Product photos used in the hero collage (product.template ids on selamtausa.com):
# 23 PCS Coffee Set (Large Telet), Almi black teff 25 LB, Berbere 1 KG, Kolo Almi 1 KG.
# Missing or unpublished ids are skipped and the gap is filled from best sellers.
HERO_PRODUCT_IDS = [1439, 1724, 1510, 1608]

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

    def _selamta_best_sellers(self, limit=6):
        self.ensure_one()
        ranked_ids = list(self._selamta_best_seller_ids(fields.Date.context_today(self)))
        if not ranked_ids:
            return []
        products = self.env['product.template'].search(
            expression.AND([self._selamta_product_domain(), [('id', 'in', ranked_ids)]])
        )
        by_id = {p.id: p for p in products}
        ordered = [by_id[pid] for pid in ranked_ids if pid in by_id][:limit]
        return [self._selamta_product_card(p) for p in ordered]

    def _selamta_new_arrivals(self, limit=6):
        self.ensure_one()
        products = self.env['product.template'].search(
            self._selamta_product_domain(), order='create_date desc, id desc', limit=limit,
        )
        return [self._selamta_product_card(p) for p in products]

    def _selamta_hero_images(self):
        self.ensure_one()
        Product = self.env['product.template']
        products = Product.search(
            expression.AND([self._selamta_product_domain(), [('id', 'in', HERO_PRODUCT_IDS)]])
        )
        by_id = {p.id: p for p in products}
        chosen = [by_id[pid] for pid in HERO_PRODUCT_IDS if pid in by_id]
        if len(chosen) < 4:
            extra_ids = [c['id'] for c in self._selamta_best_sellers(8) if c['id'] not in by_id]
            chosen += list(Product.browse(extra_ids[:4 - len(chosen)]))
        return [{
            'name': (p.name or '').strip(),
            'image': '/web/image/product.template/%d/image_1024' % p.id,
        } for p in chosen]

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

    def _selamta_brands(self):
        return [{'name': name, 'url': '/shop?search=%s' % quote(name)} for name in BRANDS]
