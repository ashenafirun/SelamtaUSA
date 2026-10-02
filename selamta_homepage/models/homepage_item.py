# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SelamtaHomepageItem(models.Model):
    """A product picked by hand for a homepage section, in drag-and-drop order."""
    _name = 'selamta.homepage.item'
    _description = 'Homepage Product'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    section = fields.Selection(
        [('best_sellers', 'Best sellers'), ('new_arrivals', 'New arrivals')],
        required=True, default='new_arrivals',
    )
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', required=True, ondelete='cascade',
        domain=[('sale_ok', '=', True)],
    )
    image_128 = fields.Image(related='product_tmpl_id.image_128', string='Image')
    is_published = fields.Boolean(related='product_tmpl_id.is_published', string='Published on website')

    _sql_constraints = [
        ('section_product_unique', 'unique (section, product_tmpl_id)',
         'This product is already in that homepage section.'),
    ]

    @api.model
    def _selamta_fill_automatic(self, section):
        """Replace a section's list with the products chosen automatically
        (top sellers of the last 12 months, or the newest products)."""
        website = self.env['website'].get_current_website()
        products = website._selamta_auto_products(section, 6)
        self.search([('section', '=', section)]).unlink()
        self.create([
            {'section': section, 'product_tmpl_id': product.id, 'sequence': (index + 1) * 10}
            for index, product in enumerate(products)
        ])

    def action_selamta_reset_automatic(self):
        """List button "Reset to automatic list" (works with or without selected rows)."""
        section = self.env.context.get('default_section')
        if section in dict(self._fields['section'].selection):
            self._selamta_fill_automatic(section)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model
    def _selamta_seed_lists(self):
        """On install/upgrade: fill each list once with what the homepage shows,
        so the lists start out filled in instead of blank."""
        params = self.env['ir.config_parameter'].sudo()
        for section in ('best_sellers', 'new_arrivals'):
            key = 'selamta_homepage.seeded_%s' % section
            if params.get_param(key):
                continue
            if not self.search_count([('section', '=', section)]):
                self._selamta_fill_automatic(section)
            params.set_param(key, '1')
