from odoo import fields , models , api
from odoo.exceptions import ValidationError
import logging

class MinMaxQuantity(models.Model):
    _inherit = "product.product"

    minimum_product_quantity = fields.Integer(string="Minimum Product Quantity",default=-1)
    max_product_quantity = fields.Integer(string="Maxmium Product Quantity",default=-1)
    check_box = fields.Boolean('Enable Cart Limit')

    @api.model_create_multi
    def create(self,vals):
        rec = super().create(vals)
        if vals["minimum_product_quantity"] or vals["max_product_quantity"]:
            if (vals["minimum_product_quantity"] > vals["max_product_quantity"])  and vals["max_product_quantity"] != -1:
                raise ValidationError("Maximum product quantity should be more than minimum product qunatity")
        
            elif vals["minimum_product_quantity"] < -1 or vals["max_product_quantity"] < -1:
                raise ValidationError(" Value must be greater then -2")
            
        if vals["minimum_product_quantity"]==0 or vals["max_product_quantity"]==0:
            raise ValidationError("Product quantity should not be zero.")
        return rec
        
    def write(self,vals):
        rec = super().write(vals)
        if self.minimum_product_quantity or self.max_product_quantity:
            if (self.minimum_product_quantity > self.max_product_quantity) and self.max_product_quantity != -1:
                raise ValidationError("Maximum product quantity should be more than minimum product qunatity")
            elif self.minimum_product_quantity < -1 or self.max_product_quantity < -1:
                raise ValidationError(" Value must be greater then -2")
        if self.minimum_product_quantity == 0 or self.max_product_quantity == 0:
            raise ValidationError("Product quantity should not be zero.")
        return rec
    
    @api.onchange('check_box')
    def _onchange_check_box(self):
        for rec in self:
            rec.minimum_product_quantity=-1
            rec.max_product_quantity=-1


