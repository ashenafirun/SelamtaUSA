from odoo import fields, models ,api
from odoo.exceptions import UserError

class ForecastLine(models.Model):
    _name = "forecast.line"
    _description = "Forecast Line"
    _rec_name = "product_id"

    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product"
    )

    ## Forecast fields
    rule_id = fields.Many2one(
        comodel_name="forecast.rule",
        string="Forecast Rule"
    )
    warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Warehouse"
    )
    period_from = fields.Date(
        string="Forecast Start"
    )
    period_to = fields.Date(
        string="Forecast End"
    )
    forecast_qty = fields.Integer(
        string="Forecasted Quantity"
    )
    sold_qty = fields.Integer(
        string="Sold Quantity",
        help="Total sold quantities in sales history used for forecasting."
    )

    ## Stock analysis Fields
    avg_daily_demand= fields.Float(
        string="Average Daily Demand",
        help="Average quantity sold per day based on sales history used for forecasting."
    )
    lead_time_days = fields.Integer(
        string="Lead Time Days",
        help="Lead time days for the forecast rule."
    )
    lead_time_demand = fields.Integer(
        string="Lead Time Demand",
        help="Forecasted quantities for the lead time days."
    )
    order_cycle_days =  fields.Integer(
        string="Order Cycle Days",
        help="Order cycle days for the forecast rule."
    )
    order_cycle_demand = fields.Integer(
        string="Order Cycle Demand",
        help="Order cycle demand for order cycle days."
    )
    safety_stock = fields.Integer(
        string="Safety Stock",
        help="Extra buffer stock quantities to cover unexpected demand or delays."
    )
    current_stock = fields.Integer(
        string="Current Stock",
        help="Current On hand quantities for the warehouse."
    )
    incoming_qty = fields.Integer(
        string="Incoming Quantity"
    )
    reserved_qty = fields.Integer(
        string="Reserved Quantity"
    )
    net_stock = fields.Integer(
        string="Net Stock",
        help="Current Net Stock."
    )
    shortage_qty = fields.Integer(
        string="Shortage Quantity",
    )
    stock_status = fields.Selection(
        selection=[('shortage', 'Shortages'),
                   ('in_stock', 'In Stock')],
        string="Status",
        compute="_compute_stock_status",
        store=True
    )

    ## New PO related fields
    vendor_id = fields.Many2one(
        comodel_name="res.partner",
        string="Vendor",
        help="Select the Vendor for ordering this product."
    )
    vendor_domain_ids = fields.Many2many(
        comodel_name='res.partner',
        compute='_compute_vendor_domain_ids'
    )

    action_type = fields.Selection([
        ('transfer', 'Transfer'),
        ('po', 'Purchase Order'),
        ('partial', 'Transfer + Purchase Order'),
        ('none', 'None')
    ], string="Action Type", default='none', readonly=True
    )
    action_summary = fields.Text(
        string="Action Summary", readonly=True
    )
    transfer_plan = fields.Json(
        string="Transfer Plan Storage"
    )
    forecast_calculation = fields.Text(
        string="Forecast Calculation"
    )
    transfer_state =  fields.Selection(
        string = "Transfer State", selection=[('unprocessed','Unprocessed'),("processed","Processed")], default="unprocessed"
    )

    @api.depends('shortage_qty')
    def _compute_stock_status(self):
        for record in self:
            if record.shortage_qty > 0:
                record.stock_status = 'shortage'
            else:
                record.stock_status = 'in_stock'

    @api.depends('shortage_qty')
    def _compute_is_shortage(self):
        for record in self:
            record.is_shortage = record.shortage_qty > 0

    @api.depends('product_id')
    def _compute_vendor_domain_ids(self):
        for rec in self:
            rec.vendor_domain_ids = rec.product_id.seller_ids.mapped('partner_id')

    def create_purchase_order(self, order_qty):
        if not self.vendor_id:
            return False, 'Purchase order not created: No vendor configured for this product'

        picking_type_id = self.env['stock.picking.type'].search([('code','=','incoming'),('warehouse_id','=',self.rule_id.warehouse_id.id)],limit=1)
        vendor_id = self.vendor_id.id
        operation = "created"
        po = self.env['purchase.order'].search([('partner_id','=',vendor_id),('picking_type_id.warehouse_id','=', self.rule_id.warehouse_id.id),('state','in',['draft','sent'])],limit=1)
        if po:
            operation = "updated"
            po_line = po.order_line.filtered(lambda l:l.product_id.id == self.product_id.id)[:1]
            if po_line:
               po_line.product_qty += order_qty
            else:
                po.write({'order_line': [(0, 0, {
                    'product_id': self.product_id.id,
                    'product_qty':order_qty ,
                    'price_unit': self.product_id.standard_price,
                })]

            })
        else:
            po = self.env['purchase.order'].create({
                "partner_id": vendor_id,
                "date_order": fields.Date.today(),
                "company_id": self.rule_id.company_id.id,
                'picking_type_id': picking_type_id.id,
                'order_line': [(0, 0, {
                    'product_id': self.product_id.id,
                    'product_qty': order_qty,
                    'price_unit': self.product_id.standard_price,
                })]
            })

        return True, f"Purchase order : {po.name} {operation} with quantity {order_qty}"

    def action_create_transfer(self):
        self.ensure_one()
        if self.transfer_state == 'processed':
            raise UserError("Transfer has already been executed for this forecast line.")
        return self.rule_id.with_context(
            single_line_id=self.id
        ).create_transfer()
