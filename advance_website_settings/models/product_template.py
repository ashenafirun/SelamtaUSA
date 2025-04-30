from odoo import fields , models , api
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)
class ProductTemplateInherit(models.Model):
    _inherit = "product.template"

    minimum_product_quantity = fields.Integer(string="Minimum Product Quantity",default=-1)
    max_product_quantity = fields.Integer(string="Maxmium Product Quantity",default=-1)
    check_box = fields.Boolean('Enable Cart Limit')

    @api.model_create_multi
    def create(self,vals):
        rec = super(ProductTemplateInherit, self).create(vals)
        for val in vals:
            if 'minimum_product_quantity' in val and 'max_product_quantity' in val:
                if val["minimum_product_quantity"] or val["max_product_quantity"]:
                    if (val["minimum_product_quantity"] > val["max_product_quantity"]) and val["max_product_quantity"] != -1 :
                        raise ValidationError("Maximum product quantity should be more than minimum product qunatity")

                    elif val["minimum_product_quantity"] < -1 or val["max_product_quantity"] < -1:
                        raise ValidationError(" Value must be greater then -2")
                if val["minimum_product_quantity"]==0 or val["max_product_quantity"]==0:
                    raise ValidationError("Product quantity should not be zero. ")
        return rec

    def write(self,vals):
        rec = super(ProductTemplateInherit, self).write(vals)
        for val in vals:
            if 'minimum_product_quantity' in val and 'max_product_quantity' in val:
                if val["minimum_product_quantity"] or val["max_product_quantity"]:
                    if (val["minimum_product_quantity"] > val["max_product_quantity"]) and val[
                        "max_product_quantity"] != -1:
                        raise ValidationError("Maximum product quantity should be more than minimum product qunatity")

                    elif val["minimum_product_quantity"] < -1 or val["max_product_quantity"] < -1:
                        raise ValidationError(" Value must be greater then -2")
                if val["minimum_product_quantity"] == 0 or val["max_product_quantity"] == 0:
                    raise ValidationError("Product quantity should not be zero. ")
        return rec
    
    @api.onchange('check_box')
    def _onchange_check_box(self):
        for rec in self:
            rec.minimum_product_quantity=-1
            rec.max_product_quantity=-1
