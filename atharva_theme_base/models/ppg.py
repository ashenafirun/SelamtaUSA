# -*- coding: utf-8 -*-

from odoo import models, fields

class ShopProductPerPage(models.Model):
    _name = 'as.ppg'
    _description = "Product Per Page Dropdown Shop"
    _order = "sequence,id"

    sequence = fields.Integer(string="Sequence")
    name = fields.Integer(string="PPG", default='10', required=True)

    _sql_constraints = [("name_uniqe", "unique (name)", "Value already exists.!")]