from odoo import fields, models, api
from datetime import timedelta
from odoo.exceptions import ValidationError


class ForecastDeadstockWizard(models.TransientModel):
    _name = 'forecast.deadstock.wizard'
    _description = 'Forecast Deadstock Wizard'
    _rec_name = 'id'

    inactive_days = fields.Integer(string='Inactive Days', default=30)

    # Fields for list view display
    product = fields.Char(string='Product', compute='_compute_report_data', store=False)
    warehouse = fields.Char(string='Warehouse', compute='_compute_report_data', store=False)
    current_stock = fields.Float(string='Current Stock', compute='_compute_report_data', store=False)
    last_movement = fields.Date(string='Last Movement', compute='_compute_report_data', store=False)
    days_since_movement = fields.Integer(string='Days Since Movement', compute='_compute_report_data', store=False)
    status = fields.Char(string='Status', compute='_compute_report_data', store=False)
    report_lines = fields.Binary(compute='_compute_report_data', store=False)

    def get_status(self, days_since_movement):
        if days_since_movement >= 120:
            return 'Deadstock'
        elif days_since_movement >= 60:
            return 'Very Slow Moving'
        elif days_since_movement >= 30:
            return 'Slow Moving'
        return 'Active'

    def prepare_report_lines(self):
        active_ids = self.env.context.get('active_ids')
        ForecastLine = self.env['forecast.line']
        records = ForecastLine.browse(active_ids) if active_ids else ForecastLine.search([])

        cutoff_date = fields.Date.today() - timedelta(days=self.inactive_days)
        lines = []

        for line in records:
            product = line.product_id

            # Check if product is archived - skip if archived
            if product.active is False:
                continue

            # calculate days since last movement
            last_move = self.env['stock.move'].search([
                ('product_id', '=', product.id),
                ('state', '=', 'done'),
                ('location_id.usage', '=', 'internal'),
            ], order='date desc', limit=1)

            if last_move:
                days_since = (fields.Date.today() - last_move.date.date()).days
                last_movement_date = last_move.date.date()
            else:
                days_since = 999  # never moved
                last_movement_date = False

            status = self.get_status(days_since)

            lines.append({
                'product': product.display_name,
                'warehouse': line.warehouse_id.display_name,
                'current_stock': line.current_stock,
                'last_movement': last_movement_date,
                'days_since_movement': days_since,
                'status': status,
                'is_deadstock': days_since >= 120,
            })

        # sort by days_since_movement descending
        lines.sort(key=lambda x: x['days_since_movement'], reverse=True)
        return lines

    @api.depends('inactive_days')
    def _compute_report_data(self):
        """Compute report data for list view"""
        for wizard in self:
            lines = wizard.prepare_report_lines()
            if lines:
                # Store lines data for the list view
                wizard.product = lines[0]['product'] if lines else False
                wizard.warehouse = lines[0]['warehouse'] if lines else False
                wizard.current_stock = lines[0]['current_stock'] if lines else 0
                wizard.last_movement = lines[0]['last_movement'] if lines else False
                wizard.days_since_movement = lines[0]['days_since_movement'] if lines else 0
                wizard.status = lines[0]['status'] if lines else False
                wizard.report_lines = lines
            else:
                wizard.product = False
                wizard.warehouse = False
                wizard.current_stock = 0
                wizard.last_movement = False
                wizard.days_since_movement = 0
                wizard.status = False

    def action_generate_deadstock_report(self):
        self.ensure_one()
        lines = self.prepare_report_lines()
        if not lines:
            raise ValidationError("No Data")
        report_data = {
            'lines': lines,
            'target_days': self.inactive_days,
        }
        report_xml_id = "forecasting_auto_replenishment.action_report_deadstock"
        return self.env.ref(report_xml_id).report_action(self, data=report_data)

    def action_open_list_view(self):
        """Open list view with report data"""
        self.ensure_one()
        lines = self.prepare_report_lines()

        if not lines:
            raise ValidationError("No data found for deadstock report")

        # Create a new record with the computed data
        # This is a simplified approach - in production you might want to use a different method
        return {
            'type': 'ir.actions.act_window',
            'name': 'Deadstock Report',
            'res_model': 'forecast.deadstock.wizard',
            'view_mode': 'list',
            'target': 'current',
            'context': self.env.context,
        }
