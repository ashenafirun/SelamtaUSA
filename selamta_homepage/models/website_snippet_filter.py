# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.osv import expression


class WebsiteSnippetFilter(models.Model):
    _inherit = 'website.snippet.filter'

    # ------------------------------------------------------------------
    # Product filters for Odoo's "Products" block
    # (see data/snippet_filter_data.xml). Called by website_sale's
    # _get_products('selamta_best_sellers' / 'selamta_new_arrivals').
    # ------------------------------------------------------------------

    def _get_products_selamta_best_sellers(self, website, limit, domain, **kwargs):
        return self._selamta_section_variants(website, 'best_sellers', limit, domain)

    def _get_products_selamta_new_arrivals(self, website, limit, domain, **kwargs):
        return self._selamta_section_variants(website, 'new_arrivals', limit, domain)

    def _selamta_section_variants(self, website, section, limit, domain):
        """Products of a homepage list (hand-picked, else automatic), in list order,
        as product.product records restricted to the block's domain (published,
        website, company and the block's own category/tag/name options)."""
        Variant = self.env['product.product'].with_context(display_default_code=False)
        limit = limit or 16
        templates = website._selamta_section_products(section, 16)
        variants = templates.product_variant_id
        if not variants:
            return Variant
        allowed = set(Variant._search(expression.AND([domain, [('id', 'in', variants.ids)]])))
        return Variant.browse([variant.id for variant in variants if variant.id in allowed][:limit])

    # ------------------------------------------------------------------
    # Brand filter for Odoo's "Dynamic Content" block
    # (dynamic_filter_brand_tiles in data/snippet_filter_data.xml)
    # ------------------------------------------------------------------

    @api.model
    def _selamta_get_brands(self):
        """All brands of Product Brands in their drag-and-drop order. The block's
        'Fetched Elements' limit (max 16) is ignored on purpose so every brand shows."""
        dynamic_filter = self.env.context.get('dynamic_filter')
        brands = self.env['website'].get_current_website()._selamta_brand_records()
        if not dynamic_filter or brands is None:
            return []
        return dynamic_filter._filter_records_to_values(brands)
