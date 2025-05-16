# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model_create_multi
    def create(self, vals):
        res = super(ProductTemplate, self).create(vals)
        setting = self.env['res.config.settings'].search([], limit=1, order="id desc")
        if res:
            if setting.sync_product and res.available_in_pos:
                prod_category = self.env['pos.category'].search([('complete_name','=',res.categ_id.complete_name)], limit=1)
                if prod_category:
                    res.update({
                        'pos_categ_id' : prod_category.id
                    })
        return res

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)
        setting = self.env['res.config.settings'].search([], limit=1, order="id desc")
        if setting.sync_product and 'categ_id' in vals:
            if self.available_in_pos:
                prod_category = self.env['pos.category'].search([('complete_name','=',self.categ_id.complete_name)], limit=1)
                if prod_category:
                    self.update({
                        'pos_categ_id' : prod_category.id
                    })
        return res



class PosCategory(models.Model):
    _inherit = "pos.category"

    internal_categ_id = fields.Many2one('product.category' , string = "Product Category")
    complete_name = fields.Char(
        'Complete Name', compute='_compute_complete_name',
        store=True)

    @api.depends('name', 'parent_id')
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = '%s / %s' % (category.parent_id.complete_name, category.name)
            else:
                category.complete_name = category.name



class Productcategory(models.Model):
    _inherit = "product.category"

    pos_categ_id = fields.Many2one('pos.category' , string = 'POS category')
    avail_in_pos = fields. Boolean(string='Sync with POS Category')
    pos_readonly_flag = fields.Boolean(string="Make POS option Readonly")
    create_pos_categ = fields.Boolean(compute='_is_sync_category_checked')

    @api.depends('name', 'parent_id','property_cost_method')
    def _is_sync_category_checked(self):
        setting = self.env['res.config.settings'].search([], limit=1, order="id desc")
        for rec in self:
            if setting.sync_category:
                rec.create_pos_categ = True
            else:
                rec.create_pos_categ = False


    @api.model_create_multi
    def create(self, vals):
        res = super(Productcategory, self).create(vals)
        if res:
            setting = self.env['res.config.settings'].search([], limit=1, order="id desc")
            pos_categ = self.env['pos.category']
            if setting.sync_category and res.avail_in_pos == True:
                for category in res:
                    category_available = pos_categ.search([('name','=',category.name)])
                    if not category_available:
                        new_category = pos_categ.create({
                            'name' : category.name,
                            'internal_categ_id' : category.id
                        })
                        category.update({'pos_categ_id' : new_category.id})
                        parent_id = category.parent_id
                        if parent_id:
                            self.check_parent_category(new_category,parent_id)

        return res

    def check_parent_category(self,new_categ , parent_categ):
        pos_parent_available = self.env['pos.category'].search([('name','=',parent_categ.name)], limit=1)
        if not pos_parent_available:
            pos_parent = self.env['pos.category'].create({'name' : parent_categ.name,'internal_categ_id' : parent_categ.id})
            new_categ.update({ 'parent_id' : pos_parent.id})
            parent_categ.update({'pos_categ_id' : pos_parent.id})
            if parent_categ.parent_id:
                parent_id = parent_categ.parent_id
                self.check_parent_category(pos_parent , parent_id)
        else:
            new_categ.update({'parent_id' : pos_parent_available.id,'internal_categ_id' : parent_categ.id})
            if parent_categ.parent_id:
                parent_id = parent_categ.parent_id
                self.check_parent_category(pos_parent_available , parent_id)
        return

    def write(self, vals):
        if self.avail_in_pos == True:
            vals['pos_readonly_flag'] = True
        res =  super(Productcategory, self).write(vals)
        setting = self.env['res.config.settings'].search([], limit=1, order="id desc")
        if setting.sync_category and self.avail_in_pos == True:
            pos_categ = self.env['pos.category']
            for category in self:
                if self.pos_categ_id:
                    if self.pos_categ_id.name != self.name:
                        self.pos_categ_id.name =  self.name
                    if self.pos_categ_id.parent_id.name != self.parent_id.name:
                        pos_parent_available = self.env['pos.category'].search([('complete_name','=',self.parent_id.complete_name)], limit=1)
                        if pos_parent_available:
                            self.pos_categ_id.parent_id = pos_parent_available.id
                        else:
                            self.check_parent_category(self.pos_categ_id , self.parent_id)
                else:
                    category_available = pos_categ.search([('name','=',category.name)])
                    if not category_available:
                        new_category = pos_categ.create({
                            'name' : category.name,
                            'internal_categ_id' : category.id
                        })
                        category.update({'pos_categ_id' : new_category.id})
                        parent_id = category.parent_id
                        if parent_id:
                            self.check_parent_category(new_category,parent_id)

        return res
