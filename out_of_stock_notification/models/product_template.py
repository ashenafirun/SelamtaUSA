from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _get_combination_info(self, combination=False, product_id=False, add_qty=1, pricelist=False, parent_combination=False, only_template=False):
        combination_info = super(ProductTemplate, self)._get_combination_info(
            combination=combination,
            product_id=product_id,
            add_qty=add_qty,
            pricelist=pricelist,
            parent_combination=parent_combination,
            only_template=only_template,
        )

        if not self.env.context.get('back_to_stock_notification'):
            return combination_info

        if combination_info['product_id']:
            combination_info['back_to_stock'] = self.env['product.back.to.stock'].sudo().is_in_list(combination_info["product_id"])

        return combination_info
