from odoo import api, fields, models


class TransferLog(models.Model):
    _name = 'transfer.log'
    _description = 'Transfer Log'
    _rec_name = 'name'

    name=fields.Char(string='Name')
    rule_id = fields.Many2one('forecast.rule', string='Rule')
    transfer_date = fields.Datetime(string='Transfer Date', default=fields.Datetime.now)
    total_products = fields.Integer(string='Total Products',compute='_compute_totals')
    total_failed = fields.Integer(string='Failed Products',compute='_compute_totals')
    line_ids = fields.One2many('transfer.log.line', inverse_name='log_id',string='Log Lines')

    @api.depends('line_ids.status')
    def _compute_totals(self):
        for rec in self:
            product_lines = rec.line_ids.filtered(lambda l:l.product_id)
            rec.total_products = len(product_lines)
            rec.total_failed = len(
                product_lines.filtered(lambda l: l.status == 'failed')
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sequence = self.env.ref('forecasting_auto_replenishment.forecast_transfer_log_sequence')
            name = sequence and sequence.next_by_id() or '/'
            if type(vals) == dict:
                vals.update({'name': name})
        return super().create(vals_list)



class TransferLogLine(models.Model):
    _name = 'transfer.log.line'
    _description = 'Transfer Log Line'
    _rec_name = 'product_id'

    log_id = fields.Many2one('transfer.log', string='Log')
    product_id = fields.Many2one('product.product', string='Product')
    category_id = fields.Many2one('product.category', string='Category')
    status = fields.Selection([('success','Success'),('partial','Partial'),('failed','Failed')], string='Status')
    reason = fields.Text(string='Information')
