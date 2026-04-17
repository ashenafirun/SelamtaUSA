import math
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ForecastOverstockWizard(models.TransientModel):
    _name = 'forecast.overstock.wizard'
    _description = 'Overstock Report Wizard'
    _rec_name = 'id'

    method = fields.Selection([
        ('excess_stock', 'Excess Stock'),
        ('days_of_inventory', 'Days of Inventory'),
    ], string="Report Method", default='excess_stock')

    target_days = fields.Integer(
        string="Target Coverage Days",
        default=60,
        help="Products with days of inventory above this are overstocked."
    )

    # Fields for list view display
    product = fields.Char(string='Product', compute='_compute_report_data', store=False)
    warehouse = fields.Char(string='Warehouse', compute='_compute_report_data', store=False)
    net_stock = fields.Float(string='Net Stock', compute='_compute_report_data', store=False)
    forecast_qty = fields.Float(string='Forecast Qty', compute='_compute_report_data', store=False)
    safety_stock = fields.Float(string='Safety Stock', compute='_compute_report_data', store=False)
    target_stock = fields.Float(string='Target Stock', compute='_compute_report_data', store=False)
    excess_stock = fields.Float(string='Excess Stock', compute='_compute_report_data', store=False)
    excess_days = fields.Float(string='Excess Days', compute='_compute_report_data', store=False)
    avg_daily_demand = fields.Float(string='Avg Daily Demand', compute='_compute_report_data', store=False)
    days_of_inventory = fields.Float(string='Days of Inventory', compute='_compute_report_data', store=False)
    status = fields.Char(string='Status', compute='_compute_report_data', store=False)

    def _prepare_report_lines(self):
        ForecastLine = self.env['forecast.line']
        active_ids = self.env.context.get('active_ids')
        records = ForecastLine.browse(active_ids) if active_ids else ForecastLine.search([])

        lines = []
        for l in records:
            # Skip archived products
            if l.product_id.active is False:
                continue

            avg_daily = round(l.avg_daily_demand, 2) or 0
            target_stock = l.forecast_qty + l.safety_stock
            days_of_inv = math.floor(l.net_stock / avg_daily) if avg_daily > 0 else 0
            excess = max(l.net_stock - target_stock, 0)

            lines.append({
                'product': l.product_id.display_name,
                'warehouse': l.warehouse_id.display_name,
                'net_stock': l.net_stock,
                'forecast_qty': l.forecast_qty,
                'safety_stock': l.safety_stock,
                'target_stock': target_stock,
                'excess_stock': excess,
                'excess_days': max(days_of_inv - self.target_days, 0),
                'avg_daily_demand': avg_daily,
                'days_of_inventory': days_of_inv,
                'status': 'Overstock' if excess > 0 else 'Normal',
            })
        return lines

    @api.depends('method', 'target_days')
    def _compute_report_data(self):
        """Compute report data for list view"""
        for wizard in self:
            lines = wizard._prepare_report_lines()
            if lines:
                wizard.product = lines[0]['product']
                wizard.warehouse = lines[0]['warehouse']
                wizard.net_stock = lines[0]['net_stock']
                wizard.forecast_qty = lines[0]['forecast_qty']
                wizard.safety_stock = lines[0]['safety_stock']
                wizard.target_stock = lines[0]['target_stock']
                wizard.excess_stock = lines[0]['excess_stock']
                wizard.excess_days = lines[0]['excess_days']
                wizard.avg_daily_demand = lines[0]['avg_daily_demand']
                wizard.days_of_inventory = lines[0]['days_of_inventory']
                wizard.status = lines[0]['status']
            else:
                wizard.product = False
                wizard.warehouse = False
                wizard.net_stock = 0
                wizard.forecast_qty = 0
                wizard.safety_stock = 0
                wizard.target_stock = 0
                wizard.excess_stock = 0
                wizard.excess_days = 0
                wizard.avg_daily_demand = 0
                wizard.days_of_inventory = 0
                wizard.status = False

    def action_generate_overstock_report(self):
        self.ensure_one()
        lines = self._prepare_report_lines()
        if not lines:
            raise ValidationError("No data to print.")

        report_data = {
            'lines': lines,
            'target_days': self.target_days,
        }

        report_xml_id = (
            'forecasting_auto_replenishment.action_report_overstock_excess'
            if self.method == 'excess_stock'
            else 'forecasting_auto_replenishment.action_report_overstock_days'
        )

        return self.env.ref(report_xml_id).report_action(self, data=report_data)
