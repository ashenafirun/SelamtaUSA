from odoo import fields, models, api, _


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    p_weight = fields.Float(string="Weight(kg)", related='product_id.weight')
    p_volume = fields.Float(string="Volume(m³)", related='product_id.volume')

    weight = fields.Float(string="Total Weight(kg)", compute="_compute_weight", store=True)
    volume = fields.Float(string="Total Volume(m³)", compute="_compute_volume", store=True)

    @api.onchange('product_id', 'product_uom_qty')
    def onchange_product_weight(self):
        for product in self:
            product.weight = product.p_weight * product.product_uom_qty
            product.volume = product.p_volume * product.product_uom_qty

    @api.depends('product_uom_qty', 'product_id')
    def _compute_volume(self):
        for line in self:
            volume = 0
            if line.product_id and line.product_id.volume:
                volume += line.product_id.volume * line.product_uom_qty
            line.volume = volume

    @api.depends('product_uom_qty', 'product_id')
    def _compute_weight(self):
        for line in self:
            weight = 0
            if line.product_id and line.product_id.weight:
                weight += line.product_id.weight * line.product_uom_qty
            line.weight = weight

    def _prepare_procurement_values(self, group_id=False):
        res = super(SaleOrderLine, self)._prepare_procurement_values(group_id)
        res.update({
            'weight': self.weight,
            'volume': self.volume
        })
        return res


class SaleOrder(models.Model):
    _inherit = "sale.order"

    total_volume = fields.Float(string="Total Volume(m³)", readonly=True, compute='_compute_total_volume')
    total_weight = fields.Float(string="Total Weight(kg)", readonly=True, compute='_compute_total_weight')
    weight_unit = fields.Char(string="kg", readonly=True)
    volume_unit = fields.Char(string="m³", readonly=True)

    def _compute_total_volume(self):
        for rec in self:
            total_volume = 0
            for line in rec.order_line:
                total_volume += line.volume or 0.0
            rec.total_volume = total_volume

    def _compute_total_weight(self):
        for rec in self:
            total_weight = 0
            for line in rec.order_line:
                total_weight += line.weight or 0.0
            rec.total_weight = total_weight
