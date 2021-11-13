# -*- coding: utf-8 -*-

from odoo import models, fields, api

class ASProductTemplateExtend(models.Model):
    _inherit = 'product.template'

    product_rating = fields.Float(string='Product Rating', compute='_compute_product_rating', store=True)
    product_tab_description = fields.Html(string="Product Tab Description")

    @api.depends('message_ids')
    def _compute_product_rating(self):
        ''' Compute product rating '''
        for i in self:
            prodRating = round(i.sudo().rating_get_stats().get('avg') / 1 * 100) / 100
            i.product_rating = prodRating

    @api.model
    def _search_get_detail(self, website, order, options):
        ''' Add RBT domain '''
        res = super(ASProductTemplateExtend,self)._search_get_detail(website=website, order=order, options=options)
        base_domain = res.get("base_domain")
        if options.get("rating", False):
            base_domain.append([('product_rating','>=',options['rating'])])
            res.update({"base_domain":base_domain})
        if options.get("brand", False):
            base_domain.append([('product_brand_id','in',[int(i) for i in options['brand']])])
            res.update({"base_domain":base_domain})
        if options.get("tag", False):
            base_domain.append([('product_tags_ids','in',[int(i) for i in options['tag']])])
            res.update({"base_domain":base_domain})
        return res