# -*- coding: utf-8 -*-
from odoo import fields, models


class SelamtaHomepageItem(models.Model):
    """A product picked by hand for a homepage section, in drag-and-drop order."""
    _name = 'selamta.homepage.item'
    _description = 'Homepage Product'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    section = fields.Selection(
        [('new_arrivals', 'New arrivals')],
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
