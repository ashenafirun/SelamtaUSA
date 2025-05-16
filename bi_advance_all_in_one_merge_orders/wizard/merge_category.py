# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MergeCategoryWizard(models.TransientModel):
    _name = 'merge.category.wizard'
    _description = 'Merge Category Wizard'

    operation_type = fields.Selection([
        ('create_all','Create all Internal Category on POS Category'),
        ('link_all_products','All product link with POS category')],
        string='Select Operation to do', default='create_all')
    category_ids = fields.Many2many('product.category','categ_id', 'prod_categ_change' ,string = "Product Category")
    avail_in_pos = fields.Boolean(string='Default check Available in POS Option in Product')


    def check_parent_category(self,new_category , parent_category):
        pos_parent_available = self.env['pos.category'].search([('complete_name','=',parent_category.complete_name)], limit = 1)
        if not pos_parent_available:
            pos_parent_category = self.env['pos.category'].create({
                'name' : parent_category.name,
                'internal_categ_id': parent_category.id})
            new_category.update({ 'parent_id' : pos_parent_category.id})
            parent_category.update({
                'pos_categ_id' : pos_parent_category.id
            })
            if parent_category.parent_id:
                parent_id = parent_category.parent_id
                self.check_parent_category(pos_parent_category , parent_id)
        else:
            new_category.update({'parent_id' : pos_parent_available.id})
            if parent_category.parent_id:
                parent_id = parent_category.parent_id
                self.check_parent_category(pos_parent_available , parent_id)
        return

    def update_changes(self):
        pos_cat = self.env['pos.category']
        if self.operation_type == "create_all":
            for cat in self.category_ids:
                if cat.avail_in_pos == True and cat.pos_categ_id:
                    pass
                else:
                    available = pos_cat.search([('complete_name','=',cat.complete_name)])
                    if not available:
                        new_category = pos_cat.create({
                            'name' : cat.name,
                            'internal_categ_id': cat.id
                        })
                        cat.update({
                            'pos_categ_id' : new_category.id
                        })
                        parent_id = cat.parent_id
                        if parent_id:
                            self.check_parent_category(new_category,parent_id)
                        cat.update({'avail_in_pos': True, 'pos_readonly_flag': True})
        if self.operation_type == "link_all_products":
            for cat in self.category_ids:
                category_available = pos_cat.search([('complete_name','=',cat.complete_name)])
                if not category_available:
                    new_category = pos_cat.create({
                        'name' : cat.name,
                        'internal_categ_id': cat.id
                    })
                    cat.update({
                        'pos_categ_id' : new_category.id
                    })
                    parent_id = cat.parent_id
                    if parent_id:
                        self.check_parent_category(new_category,parent_id)
            product_template_ids  = self.env['product.template'].search([])
            for template in product_template_ids:
                pos_cat = self.env['pos.category'].search([('complete_name' ,'=' , template.categ_id.complete_name)])
                template.update({
                    'pos_categ_ids' : pos_cat
                })
                if self.avail_in_pos:
                    template.update({
                        'available_in_pos' : self.avail_in_pos
                    })

