import math
from odoo import models, fields, api
from datetime import timedelta


class OverstockReportLine(models.Model):
    _name = 'overstock.report.line'
    _description = 'Overstock Report Line'
    _rec_name = 'product_id'
    _order = 'excess_stock desc'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', readonly=True)
    net_stock = fields.Float(string='Net Stock', readonly=True)
    forecast_qty = fields.Float(string='Forecast Qty', readonly=True)
    safety_stock = fields.Float(string='Safety Stock', readonly=True)
    target_stock = fields.Float(string='Target Stock', readonly=True)
    excess_stock = fields.Float(string='Excess Stock', readonly=True)
    avg_daily_demand = fields.Float(string='Avg Daily Demand', readonly=True)
    days_of_inventory = fields.Float(string='Days of Inventory', readonly=True)
    excess_days = fields.Float(string='Excess Days', readonly=True)
    target_days = fields.Integer(string='Target Days', readonly=True)
    status = fields.Selection([
        ('overstock', 'Overstock'),
        ('normal', 'Normal'),
    ], string='Status', readonly=True)

    @api.model
    def _recompute_lines(self):
        """Wipe and recompute all overstock lines from current forecast lines."""
        self.search([]).unlink()

        forecast_lines = self.env['forecast.line'].search([])
        lines_to_create = []
        report_type =   self.env.context.get('report_type')

        for fl in forecast_lines:
            if not fl.product_id.active:
                continue

            # target_days comes from the rule's forecast_period
            target_days = fl.rule_id.forecast_period or 30

            avg_daily = round(fl.avg_daily_demand, 2) or 0
            target_stock = fl.forecast_qty  # + fl.safety_stock
            days_of_inv = math.floor(fl.net_stock / avg_daily) if avg_daily > 0 else 0
            excess = max(fl.net_stock - target_stock, 0)
            excess_days = max(days_of_inv - target_days, 0)
            if report_type == 'excess':
                status = 'overstock' if excess > 0 else 'normal'
            elif report_type == 'days':
                status = 'overstock' if excess_days > 0 else 'normal'
            else:
                status = 'normal'

            lines_to_create.append({
                'product_id': fl.product_id.id,
                'warehouse_id': fl.warehouse_id.id,
                'net_stock': fl.net_stock,
                'forecast_qty': fl.forecast_qty,
                'safety_stock': fl.safety_stock,
                'target_stock': target_stock,
                'excess_stock': excess,
                'avg_daily_demand': avg_daily,
                'days_of_inventory': days_of_inv,
                'excess_days': excess_days,
                'target_days': target_days,
                'status': status
            })

        if lines_to_create:
            self.create(lines_to_create)

    @api.model
    def action_open_excess_stock(self):
        """Recompute and open the Excess Stock list view."""
        self = self.with_context(report_type='excess')
        self._recompute_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Overstock Report — Excess Stock',
            'res_model': 'overstock.report.line',
            'view_mode': 'list',
            'views': [(self.env.ref(
                'forecasting_auto_replenishment.view_overstock_report_line_list_excess'
            ).id, 'list')],
            'target': 'current',
        }

    @api.model
    def action_open_days_of_inventory(self):
        """Recompute and open the Days of Inventory list view."""
        self = self.with_context(report_type='days')
        self._recompute_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Overstock Report — Days of Inventory',
            'res_model': 'overstock.report.line',
            'view_mode': 'list',
            'views': [(self.env.ref(
                'forecasting_auto_replenishment.view_overstock_report_line_list_days'
            ).id, 'list')],
            'target': 'current',
        }

    def action_print_excess_stock_pdf(self):
        """Print PDF for ALL overstock lines (ignores selection)."""
        all_records = self.search([])
        return self.env.ref(
            'forecasting_auto_replenishment.action_report_overstock_excess_new'
        ).report_action(all_records)

    def action_print_days_of_inventory_pdf(self):
        """Print PDF for ALL overstock lines (ignores selection)."""
        all_records = self.search([])
        return self.env.ref(
            'forecasting_auto_replenishment.action_report_overstock_days_new'
        ).report_action(all_records)


class DeadstockReportLine(models.Model):
    _name = 'deadstock.report.line'
    _description = 'Deadstock Report Line'
    _rec_name = 'product_id'
    _order = 'days_since_movement desc'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', readonly=True)
    current_stock = fields.Float(string='Current Stock', readonly=True)
    last_movement = fields.Date(string='Last Movement', readonly=True)
    days_since_movement = fields.Integer(string='Days Since Movement', readonly=True)
    status = fields.Selection([
        ('deadstock', 'Deadstock'),
        ('very_slow', 'Very Slow Moving'),
        ('slow', 'Slow Moving'),
        ('active', 'Active'),
    ], string='Status', readonly=True)

    @api.model
    def _get_status(self, days):
        if days >= 120:
            return 'deadstock'
        elif days >= 60:
            return 'very_slow'
        elif days >= 30:
            return 'slow'
        return 'active'

    @api.model
    def action_open_deadstock(self):
        """Recompute and open the Deadstock list view."""
        self.search([]).unlink()

        # All active products with on-hand stock in internal locations
        quants = self.env['stock.quant'].read_group(
            [
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
                ('product_id.active', '=', True),
            ],
            ['product_id', 'location_id', 'quantity:sum'],
            ['product_id', 'location_id'],
            lazy=False,
        )

        # Map (product_id, warehouse_id) -> total stock
        product_warehouse_stock = {}
        for q in quants:
            product_id = q['product_id'][0]
            location_id = q['location_id'][0]

            location = self.env['stock.location'].browse(location_id)
            warehouse = self.env['stock.warehouse'].search(
                [('lot_stock_id', 'parent_of', location.id)], limit=1
            )
            if not warehouse:
                continue

            key = (product_id, warehouse.id)
            product_warehouse_stock[key] = product_warehouse_stock.get(key, 0) + q['quantity']

        today = fields.Date.today()
        lines_to_create = []

        for (product_id, warehouse_id), stock_qty in product_warehouse_stock.items():
            last_move = self.env['stock.move'].search([
                ('product_id', '=', product_id),
                ('state', '=', 'done'),
                ('location_id.usage', '=', 'internal'),
            ], order='date desc', limit=1)

            if last_move:
                days_since = (today - last_move.date.date()).days
                last_movement_date = last_move.date.date()
            else:
                days_since = 999  # Never moved — sorts to top
                last_movement_date = False

            lines_to_create.append({
                'product_id': product_id,
                'warehouse_id': warehouse_id,
                'current_stock': stock_qty,
                'last_movement': last_movement_date,
                'days_since_movement': days_since,
                'status': self._get_status(days_since),
            })

        lines_to_create.sort(key=lambda x: x['days_since_movement'], reverse=True)

        if lines_to_create:
            self.create(lines_to_create)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Deadstock Report',
            'res_model': 'deadstock.report.line',
            'view_mode': 'list',
            'views': [(self.env.ref(
                'forecasting_auto_replenishment.view_deadstock_report_line_list'
            ).id, 'list')],
            'target': 'current',
        }

    def action_print_deadstock_pdf(self):
        """Print PDF for ALL deadstock lines (ignores selection)."""
        all_records = self.search([])
        return self.env.ref(
            'forecasting_auto_replenishment.action_report_deadstock_new'
        ).report_action(all_records)


class FastMovingReportLine(models.Model):
    _name = 'fastmoving.report.line'
    _description = 'Fast Moving Report Line'
    _rec_name = 'product_id'
    _order = 'monthly_movement desc'

    product_id = fields.Many2one(comodel_name='product.product', string='Product', readonly=True)
    warehouse_id = fields.Many2one(comodel_name='stock.warehouse', string='Warehouse', readonly=True)

    monthly_movement = fields.Float(string='Monthly Movement', readonly=True)
    daily_velocity = fields.Float(string='Daily Velocity', readonly=True)

    status = fields.Selection(selection=[
        ('fast', 'Fast Moving'),
        ('medium', 'Medium Moving'),
        ('slow', 'Slow Moving'),
    ], string='Status', readonly=True)

    @api.model
    def action_open_fast_moving(self):
        """Recompute and open Fast Moving Report based on last 30 days outgoing moves."""

        # Step 1: Delete Existing Lines
        self.search([]).unlink()

        today = fields.Date.today()
        start_date = today - timedelta(days=30)

        # Step 2: Aggregate outgoing moves
        grouped_moves = self.env['stock.move'].read_group(
            [
                ('state', '=', 'done'),
                ('date', '>=', start_date),
                ('location_id.usage', '=', 'internal'),
                ('location_dest_id.usage', '=', 'customer'),
                ('product_id.active', '=', True),
            ],
            ['product_id', 'location_id', 'product_uom_qty:sum'],
            ['product_id', 'location_id'],
            lazy=False,
        )

        # Step 3: Map (product, warehouse) → movement
        product_warehouse_movement = {}

        for gm in grouped_moves:
            product_id = gm['product_id'][0]
            location_id = gm['location_id'][0]
            qty = gm['product_uom_qty']

            location = self.env['stock.location'].browse(location_id)

            warehouse = location.warehouse_id

            # warehouse = self.env['stock.warehouse'].search(
            #     [('lot_stock_id', 'parent_of', location.id)], limit=1
            # )
            if not warehouse:
                continue

            key = (product_id, warehouse.id)
            product_warehouse_movement[key] = product_warehouse_movement.get(key, 0) + qty

        # Step 4: Convert to list
        data = []
        for (product_id, warehouse_id), qty in product_warehouse_movement.items():
            if qty <= 0:
                continue

            data.append({
                'product_id': product_id,
                'warehouse_id': warehouse_id,
                'monthly_movement': qty,
                'daily_velocity': qty / 30,
            })

        # Step 5: Sort DESC (core ranking)
        data.sort(key=lambda x: x['monthly_movement'], reverse=True)

        # Step 6: Assign percentile-based status
        total = len(data) or 1
        lines_to_create = []

        for index, item in enumerate(data):
            percentile = index / total

            if percentile <= 0.2:
                status = 'fast'
            elif percentile <= 0.6:
                status = 'medium'
            else:
                status = 'slow'

            lines_to_create.append({
                'product_id': item['product_id'],
                'warehouse_id': item['warehouse_id'],
                'monthly_movement': item['monthly_movement'],
                'daily_velocity': round(item['daily_velocity'], 2),
                'status': status,
            })

        # Step 7: Bulk create
        if lines_to_create:
            self.create(lines_to_create)

        # Step 8: Return action (same pattern as yours)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fast Moving Report',
            'res_model': 'fastmoving.report.line',
            'view_mode': 'list',
            'views': [(self.env.ref(
                'forecasting_auto_replenishment.view_fastmoving_report_line_list'
            ).id, 'list')],
            'target': 'current',
        }

    def action_print_fastmoving_pdf(self):
        """Print PDF for ALL fast moving lines."""
        all_records = self.search([])
        return self.env.ref(
            'forecasting_auto_replenishment.action_report_fastmoving_new'
        ).report_action(all_records)
