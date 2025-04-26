from odoo import fields , models , api
from odoo.exceptions import ValidationError


class Pricelist(models.Model):
    _inherit = "product.pricelist"

    minimum_price = fields.Float(string ='Minimum price Value To Validate Order')

