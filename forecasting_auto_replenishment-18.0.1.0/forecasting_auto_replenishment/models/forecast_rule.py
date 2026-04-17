from odoo import models, fields
from datetime import timedelta , datetime
import calendar
import math

class ForecastRule(models.Model):
    _name = 'forecast.rule'
    _description = 'Forecast Rule'

    name = fields.Char(
        string="Rule Name"
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string="Company",
        default=lambda self: self.env.company
    )
    warehouse_id = fields.Many2one(
        comodel_name='stock.warehouse',
        string="Warehouse"
    )
    product_ids = fields.Many2many(
        comodel_name="product.product",
        string="Products"
    )
    forecast_rule_config_selection = fields.Selection(
        selection=[('template', 'Product Templates'), ('vendor', 'Vendor'), ('category', 'Product Category')],
        string="Product Selection",
    )
    product_categ_ids = fields.Many2many(
        comodel_name='product.category',
        string="Product Categories"
    )
    forecast_rule_product_template_ids = fields.Many2many(
        comodel_name="product.template",
        string="Product Templates"
    )
    forecast_rule_vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string="Vendor"
    )

    ## Forecast Fields
    forecast_period = fields.Integer(
        string="Forecast Days",
        default='30',
        help="Number of future days to forecast demand for."
    )
    sales_history_days = fields.Integer(
        string="Sales History Days",
        default=90,
        help="Number of past days to consider for sales history analysis"
    )
    FORECAST_METHOD_SELECTION = [
        ('avg_daily', 'Average Daily Sales'),
        ('avg_monthly', 'Average Monthly Sales'),
        ('same_period_last_year', 'Same Period Last Year'),
    ]
    forecast_method = fields.Selection(
        selection=FORECAST_METHOD_SELECTION,
        string='Forecast Method',
        default='avg_daily',
        help="Select the Method to calculate the Forecast.\n"
             "1. Average Daily Sales: Calculates the forecast based on average DAILY sales.\n"
             "2. Average Monthly Sales: Calculates the forecast based on average MONTHLY sales.\n"
             "3. Same Period Last Year: Calculates the forecast based on last year sales data of the forecast period.\n"
    )

    ## Supply planning
    lead_time_days = fields.Integer(
        string="Lead Time Days",
        help="Lead time for Product Category/Product."
    )
    safety_stock_days = fields.Integer(
        string="Safety Stock Days",
        help="Extra buffer stock in days to cover unexpected demand or delays."
    )
    order_cycle_days = fields.Integer(
        string="Order Cycle Days",
        help="How frequently do you order (in Days)."
    )
    reordering_rule_selection = fields.Selection(
        selection=[('use_existing_rules_from_product', 'Use Products Existing Reordering Rules'),
                   ('define_reorder_qty_here', 'Define Reorder Quantities Here')],
        string="Reorder Rules",
        default='define_reorder_qty_here',
        help='1.Use Products Existing Reordering Rules: Choose this option if you want to use reorder multiple and minimum quantity defined in the products reordering rules.\n'
             '2.Define Reorder Quantities Here: Use the reorder multiple and minimum quantity you define here.'
    )
    min_reorder_qty = fields.Integer(
        string="Minimum Reorder Quantity",
        help="Minimum quantity you have to order."
    )
    reorder_multiple = fields.Integer(
        string="Reorder Multiple",
        default=1,
        help="Reorder Multiple for Forecasted Quantity."
    )
    max_stock_limit = fields.Integer(
        string="Maximum Stock Limit",
        help="Maximum stock limit for the warehouse."
    )

    ## Seasonality
    use_seasonality = fields.Boolean(
        string="Use Seasonality",
        help="Enable to apply monthly seasonal factors to the forecast quantity."
    )
    seasonality_id = fields.Many2one(
        comodel_name="forecast.seasonality",
        string="Seasonality"
    )

    ## Internal Transfer Fields
    source_warehouse_ids = fields.Many2many(
        comodel_name="stock.warehouse",
        string="Source Warehouse",
        help="From which warehouses you want to transfer quantity to destination warehouse (Highest Priority First)."
    )
    picking_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        string="Operation Type",
        help="select the type of operation you want to crate for the internal transfer."
    )
    required_qty = fields.Integer(
        string="Source Required Quantity",
        help="Minimum quantity required in source warehouse."
    )
    min_transfer_qty = fields.Integer(
        string="Minimum Transfer Quantity",
        help="Minimum quantity required to transfer form source to destination warehouse."
    )

    def action_generate_forecast(self):
        ForecastLine = self.env['forecast.line']
        ForecastRule=self.env['forecast.rule']

        forecast_rules = ForecastRule.search([('company_id','=',self.env.company.id)])

        for rule in forecast_rules:
            # remove previous lines
            ForecastLine.search([('rule_id', '=', rule.id)]).unlink()
            forecast_days = rule.forecast_period

            period_from = fields.Date.today()
            period_to = period_from + timedelta(days=forecast_days)

            sale_to = fields.Date.today()
            sale_from = sale_to - timedelta(days=rule.sales_history_days)
            history_days = rule.sales_history_days

            # specific_products = rule.product_ids
            specific_products = self.env['product.product']
            forecast_vendor_id =  self.env['res.partner']
            if rule.forecast_rule_config_selection == 'template':
                for template in rule.forecast_rule_product_template_ids:
                    specific_products += template.product_variant_ids

            elif rule.forecast_rule_config_selection == 'category':
                specific_products = self.env['product.product'].search([
                    ('categ_id', 'child_of', rule.product_categ_ids.ids),
                ])

            else:
                forecast_vendor_id = rule.forecast_rule_vendor_id
                vendor_related_product_records = self.env['product.supplierinfo'].search([
                    ('partner_id', '=', forecast_vendor_id.id)
                ])
                direct_products = vendor_related_product_records.mapped('product_id')
                templates_with_supplier = vendor_related_product_records.mapped('product_tmpl_id')
                variants_from_templates = self.env['product.product'].search([
                    ('product_tmpl_id', 'in', templates_with_supplier.ids)
                ])
                specific_products = direct_products | variants_from_templates

            # category_products = self.env['product.product'].search([
            #     ('categ_id', 'child_of', rule.product_categ_ids.ids),
            #     ('id','not in', specific_products.ids )
            # ])
            # products = specific_products | category_products
            if not specific_products:
                continue

            rule.generate_product_forecast(specific_products, period_from, period_to, history_days, sale_from, sale_to, forecast_vendor_id)
            rule.compute_transfer_decisions()

    def get_out_of_stock_days(self, product, sale_from, sale_to,current_stock):
        warehouse_loc = self.warehouse_id.lot_stock_id

        MoveLine = self.env['stock.move.line']

        warehouse_ids = self.env['stock.location'].search([
            ('id', 'child_of', warehouse_loc.id)
        ]).ids

        move_lines = MoveLine.search([
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('date', '>=', sale_from),
            ('date', '<=', sale_to),
            ('company_id', '=', self.company_id.id),
            '|',
            ('location_id', 'in', warehouse_ids),
            ('location_dest_id', 'in', warehouse_ids),
        ], order='date asc, id asc')

        opening_qty = current_stock

        # reverse to get stock at sale_from
        for line in reversed(move_lines):
            qty = line.qty_done

            if line.location_dest_id.id in warehouse_ids:
                opening_qty -= qty

            if line.location_id.id in warehouse_ids:
                opening_qty += qty

        running_qty = opening_qty
        zero_days = 0
        last_day = sale_from

        if not move_lines:
            if running_qty <= 0:
                return (sale_to - sale_from).days
            return 0

        # forward calculation
        for line in move_lines:
            move_day = line.date.date()
            qty = line.qty_done

            if running_qty <= 0:
                zero_days += (move_day - last_day).days

            if line.location_id.id in warehouse_ids:
                running_qty -= qty

            if line.location_dest_id.id in warehouse_ids:
                running_qty += qty

            last_day = move_day

        if running_qty <= 0:
            zero_days += (sale_to - last_day).days
        return max(zero_days, 0)

    def generate_product_forecast(self, products, period_from, period_to, history_days, sale_from,sale_to, forecast_vendor_id):
        ForecastLine = self.env['forecast.line']
        sales_map = self.get_sales_history(products, sale_from, sale_to)

        if sales_map:
            stock_map = self.get_stock_data(products)
            incoming_map = self.get_incoming_qty(products)

            lines = []

            for product in products:
                sold_qty = sales_map.get(product.id, 0)
                stock = stock_map.get(product.id, {})
                current_stock = stock.get('on_hand', 0)
                reserved = stock.get('reserved', 0)
                incoming = incoming_map.get(product.id, 0)
                if forecast_vendor_id:
                    vendor_id = forecast_vendor_id.id
                else:
                    vendor_id = product.seller_ids[:1].partner_id.id if product.seller_ids else False
                if not sold_qty:
                    continue
                existing_purchase_order = self.env['purchase.order.line'].search(
                    [('product_id', '=', product.id), ('order_id.partner_id','=',vendor_id),
                     ('order_id.state', '=', 'draft'), ("order_id.company_id",'=',self.company_id.id), ('order_id.picking_type_id.warehouse_id','=', self.warehouse_id.id)], limit=1)
                if existing_purchase_order:
                    po_date = existing_purchase_order.order_id.date_order
                    today = datetime.today()
                    remaining_order_cycle_days =  self.order_cycle_days  - (today - po_date).days
                    order_cycle_days = max(remaining_order_cycle_days,0)
                else:
                    order_cycle_days = self.order_cycle_days


                out_of_stock_days = self.get_out_of_stock_days(product, sale_from, sale_to,current_stock)
                effective_days = history_days - out_of_stock_days
                avg_daily = round(sold_qty/effective_days,2) if effective_days else 0
                base_forecast_qty , forecast_qty = self.calculate_forecast(product, sold_qty, avg_daily, period_from, period_to)

                net_stock = current_stock + incoming - reserved
                lead_time_days = self.lead_time_days
                lead_time_demand= math.ceil(lead_time_days * avg_daily)
                safety_stock = math.ceil(avg_daily * self.safety_stock_days)
                order_cycle_days = order_cycle_days
                cycle_demand = math.ceil(avg_daily * order_cycle_days)
                total_forecast_qty = forecast_qty + safety_stock + cycle_demand + lead_time_demand
                shortage_qty = max(total_forecast_qty - net_stock, 0)

                if self.use_seasonality and self.seasonality_id:
                    forecast_calculation = (
                        f"Base forecast: {base_forecast_qty} + Seasonality Factor: {forecast_qty - base_forecast_qty}"
                        f" + Safety stock: {safety_stock}"
                        f" + Order cycle demand: {cycle_demand}"
                        f" + Lead time demand: {lead_time_demand}"
                        f" = {total_forecast_qty}"
                    )
                else:
                    forecast_calculation = (
                        f"Base Forecast : {forecast_qty}"
                        f" + Safety stock: {safety_stock}"
                        f" + Order cycle demand: {cycle_demand}"
                        f" + Lead time demand: {lead_time_demand}"
                        f" = Total: {total_forecast_qty}"
                    )

                vals = {
                    'rule_id': self.id,
                    'warehouse_id': self.warehouse_id.id,
                    'product_id': product.id,
                    'period_from': period_from,
                    'period_to': period_to,
                    'sold_qty': sold_qty,
                    'avg_daily_demand': avg_daily,
                    'forecast_qty': total_forecast_qty,
                    'lead_time_days': lead_time_days,
                    'order_cycle_days': order_cycle_days,
                    'order_cycle_demand': cycle_demand,
                    'safety_stock': safety_stock,
                    'current_stock':current_stock,
                    'reserved_qty':reserved,
                    'incoming_qty': incoming,
                    'lead_time_demand': lead_time_demand,
                    'net_stock': net_stock,
                    'shortage_qty': shortage_qty,
                    "vendor_id": vendor_id,
                    "forecast_calculation": forecast_calculation
                }
                lines.append(vals)
            ForecastLine.create(lines)

    def get_sales_history(self, products, sale_from, sale_to):
        SaleLine = self.env['sale.order.line']
        sales = SaleLine.read_group(
            [('product_id', 'in', products.ids),
                ('order_id.state', 'in', ['sale', 'done']),
                ('order_id.date_order', '>=', sale_from),
                ('order_id.date_order', '<=', sale_to),
                ('order_id.warehouse_id', '=', self.warehouse_id.id),
                ('company_id','=',self.company_id.id),],
            ['product_id', 'product_uom_qty:sum'],
            ['product_id']
        )
        sales_map = {}
        for sale in sales:
            product_id = sale['product_id'][0]
            qty = sale['product_uom_qty']
            sales_map[product_id] = qty
        return sales_map

    def get_stock_data(self, products):
        StockQuant = self.env['stock.quant']
        quants = StockQuant.read_group(
            [('product_id', 'in', products.ids),
                ('location_id', 'child_of', self.warehouse_id.lot_stock_id.id),
             ('company_id','=',self.company_id.id),],
            ['product_id', 'quantity:sum', 'reserved_quantity:sum'],
            ['product_id']
        )
        stock_map = {}
        for q in quants:
            product_id = q['product_id'][0]
            stock_map[product_id] = {
                'on_hand': q['quantity'],
                'reserved': q['reserved_quantity']
            }
        return stock_map

    def get_incoming_qty(self, products):
        moves = self.env['stock.move'].read_group(
            [
                ('product_id', 'in', products.ids),
                ('state', 'in', ['confirmed', 'waiting', 'assigned']),
                ('location_dest_id', 'child_of', self.warehouse_id.lot_stock_id.id),
                ('company_id','=',self.company_id.id),
            ],
            ['product_id', 'product_uom_qty:sum'],
            ['product_id']
        )

        incoming_map = {}
        for m in moves:
            product_id = m['product_id'][0]
            incoming_map[product_id] = m['product_uom_qty']

        return incoming_map

    def calculate_forecast(self ,product, sold_qty, avg_daily, period_from, period_to):
        forecast_days = self.forecast_period
        history_days = self.sales_history_days
        base_forecast = 0
        if self.forecast_method == "avg_daily":
            base_forecast = math.ceil(avg_daily * forecast_days)

        elif self.forecast_method == 'avg_monthly':
            history_months = history_days / 30 if history_days else 1
            avg_monthly = sold_qty / history_months
            # forecast_months = math.ceil(forecast_days / 30)
            forecast_months = forecast_days / 30
            base_forecast = math.ceil(avg_monthly * forecast_months)

        elif self.forecast_method == 'same_period_last_year':
            last_year_from = period_from.replace(year=period_from.year - 1)
            last_year_to = period_to.replace(year=period_to.year - 1)
            SaleLine = self.env['sale.order.line']
            result = SaleLine.read_group(
                [('product_id', '=', product.id),
                 ('order_id.state', 'in', ['sale', 'done']),
                 ('order_id.date_order', '>=', last_year_from),
                 ('order_id.date_order', '<=', last_year_to),
                 ('company_id', '=', self.company_id.id),
                 ('order_id.warehouse_id', '=', self.warehouse_id.id)],
                ['product_uom_qty:sum'], []
            )
            qty = result[0]['product_uom_qty'] if result else 0
            base_forecast = qty

        if self.use_seasonality and self.seasonality_id:
            adjusted_forecast =  self.calculate_seasonality(base_forecast, period_from, period_to)
            return base_forecast, adjusted_forecast
        else:
            return base_forecast , base_forecast

    def calculate_seasonality(self, base_forecast, period_from, period_to):
        seasonality = {int(l.month): l.factor for l in self.seasonality_id.line_ids}
        total_days = (period_to - period_from).days + 1
        daily_base = base_forecast / total_days if total_days else 0
        forecast_qty = 0
        current = period_from

        while current <= period_to:
            month_end = current.replace(day=calendar.monthrange(current.year, current.month)[1])
            month_end = min(month_end, period_to)
            days = (month_end - current).days + 1
            factor = seasonality.get(current.month, 1)
            forecast_qty += daily_base * factor * days
            current = month_end + timedelta(days=1)

        return math.ceil(forecast_qty)

    def compute_transfer_decisions(self):
        for rule in self:
            forecast_lines = self.env['forecast.line'].search([('rule_id', '=', rule.id)])
            if not forecast_lines:
               self.create_log(rule,[{
                   'status': "failed",
                   'reason': "No forecast lines found"
               }])

            if not rule.source_warehouse_ids:
                for line in forecast_lines:
                    if rule.reordering_rule_selection == 'define_reorder_qty_here':
                        min_reorder = rule.min_reorder_qty or 0
                        reorder_multiple = rule.reorder_multiple or 1
                    else:
                        reorder_rule_from_product = self.env['stock.warehouse.orderpoint'].search([
                            ('product_id', '=', line.product_id.id),
                            ('location_id.warehouse_id', '=', rule.warehouse_id.id)
                        ], limit=1)
                        if reorder_rule_from_product:
                            min_reorder = reorder_rule_from_product.product_min_qty or 0
                            reorder_multiple = reorder_rule_from_product.qty_multiple or 1
                        else:
                            min_reorder = 0
                            reorder_multiple = 1

                    raw_qty = line.shortage_qty
                    po_qty = max(raw_qty, min_reorder)
                    if reorder_multiple > 1:
                        po_qty = math.ceil(po_qty / reorder_multiple) * reorder_multiple
                    line.write({
                        'action_type': 'po',
                        'action_summary': f"Purchase order Required: {po_qty}",
                        'transfer_plan': {
                            'transfers': [],
                            'po_qty': po_qty,
                            'orig_forecast_qty': raw_qty
                        }
                    })
                continue

            if not rule.picking_type_id:
                for line in forecast_lines:
                    line.write({
                        'action_type': 'none',
                        'action_summary': 'No Operation Type configured for this rule',
                        'transfer_plan': {}
                    })
                continue

            product_ids = forecast_lines.mapped('product_id').ids
            source_warehouse_stock_map = {}

            for source_wh in rule.source_warehouse_ids:
                source_warehouse_stock_map[source_wh.id] = {}
                source_quants = self.env['stock.quant'].read_group(
                    domain=[
                        ('location_id', '=', source_wh.lot_stock_id.id),
                        ('product_id', 'in', product_ids),
                        ('company_id','=',rule.company_id.id),
                    ],
                    fields=['product_id', 'quantity:sum'],
                    groupby=['product_id']
                )
                for res in source_quants:
                    if res.get('product_id'):
                        p_id = res['product_id'][0]
                        source_warehouse_stock_map[source_wh.id][p_id] = res['quantity']

            destination_stock_map = {}
            dest_quants = self.env['stock.quant'].read_group(
                domain=[
                    ('location_id', '=', rule.warehouse_id.lot_stock_id.id),
                    ('product_id', 'in', product_ids),
                    ('company_id', '=', rule.company_id.id),
                ],
                fields=['product_id', 'quantity:sum'],
                groupby=['product_id']
            )
            for res in dest_quants:
                if res.get('product_id'):
                    p_id = res['product_id'][0]
                    destination_stock_map[p_id] = res['quantity']

            for forecast in forecast_lines:
                product = forecast.product_id
                shortage_qty = forecast.shortage_qty or 0.0
                current_dest_stock = destination_stock_map.get(product.id, 0.0)

                if shortage_qty <= 0:
                    forecast.write({'action_type': 'none', 'action_summary': 'Shortage quantity is 0'})
                    continue

                remaining_qty_to_fulfill = shortage_qty
                if rule.min_transfer_qty and remaining_qty_to_fulfill < rule.min_transfer_qty:
                    remaining_qty_to_fulfill = rule.min_transfer_qty

                if rule.max_stock_limit and rule.max_stock_limit > 0:
                    space = rule.max_stock_limit - current_dest_stock
                    if space <= 0:
                        forecast.write({
                            'action_type': 'none',
                            'action_summary': f"Max stock limit reached in {rule.warehouse_id.name}"
                        })
                        continue

                transfer_details_list = []
                action_summary_list=[]
                total_qty_from_transfers = 0.0

                for wh in rule.source_warehouse_ids:
                    if remaining_qty_to_fulfill <= 0:
                        break

                    wh_stock = source_warehouse_stock_map[wh.id].get(product.id, 0.0)
                    required = rule.required_qty or 0.0

                    if wh_stock <= required:
                        continue

                    available_source = wh_stock - required

                    existing_forecast_line = self.env['forecast.line'].search([
                        ('warehouse_id', '=', wh.id),
                        ('product_id', '=', product.id),
                    ], limit=1)

                    if existing_forecast_line:
                        excess = existing_forecast_line.net_stock - existing_forecast_line.forecast_qty
                        if excess <= 0:
                            continue
                        available_excess = excess
                    else:
                        available_excess = available_source

                    if rule.max_stock_limit:
                        dest_space = rule.max_stock_limit - current_dest_stock
                        if dest_space <= 0:
                            break
                    else:
                        dest_space = remaining_qty_to_fulfill

                    take = min(
                        remaining_qty_to_fulfill,
                        available_source,
                        available_excess,
                        dest_space
                    )

                    if take <= 0:
                        continue

                    reason = None

                    if take < remaining_qty_to_fulfill:
                        if take == dest_space:
                            reason = "Destination max stock limit reached"
                        elif take == available_source:
                            reason = "Source min required quantity not met"
                        elif take == available_excess:
                            reason = "Limited by excess stock"

                    action_summary_list.append(f"Transfer {take} from {wh.name}")

                    transfer_details_list.append({
                        'wh_id': wh.id,
                        'wh_name': wh.name,
                        'qty': take,
                        'reason': reason or "",
                    })

                    remaining_qty_to_fulfill -= take
                    current_dest_stock += take
                    total_qty_from_transfers += take

                po_qty_needed = remaining_qty_to_fulfill if remaining_qty_to_fulfill > 0 else 0
                if po_qty_needed > 0:
                    if rule.reordering_rule_selection == 'define_reorder_qty_here':
                        min_reorder = rule.min_reorder_qty or 0
                        reorder_multiple = rule.reorder_multiple or 1
                    else:
                        reorder_rule_from_product = self.env['stock.warehouse.orderpoint'].search([
                            ('product_id', '=', product.id),
                            ('location_id.warehouse_id', '=', rule.warehouse_id.id)
                        ], limit=1)
                        if reorder_rule_from_product:
                            min_reorder = reorder_rule_from_product.product_min_qty or 0
                            reorder_multiple = reorder_rule_from_product.qty_multiple or 1
                        else:
                            min_reorder = 0
                            reorder_multiple = 1

                    # min_reorder = rule.min_reorder_qty or 0
                    # reorder_multiple = rule.reorder_multiple or 1
                    po_qty_needed = max(po_qty_needed, min_reorder)
                    if reorder_multiple > 1:
                        po_qty_needed = math.ceil(po_qty_needed / reorder_multiple) * reorder_multiple
                    action_summary_list.append(f"Purchase order to create with quantity : {po_qty_needed}")

                if total_qty_from_transfers > 0 and po_qty_needed > 0:
                    a_type = 'partial'
                elif total_qty_from_transfers > 0:
                    a_type = 'transfer'
                elif po_qty_needed > 0:
                    a_type = 'po'
                else:
                    a_type = 'none'

                forecast.write({
                    'action_type': a_type,
                    'action_summary': "\n".join(action_summary_list),
                    'transfer_plan': {
                        'transfers': transfer_details_list,
                        'po_qty': po_qty_needed,
                        'orig_forecast_qty': shortage_qty,
                    }
                })

    def create_transfer(self):
        single_line_id = self.env.context.get('single_line_id')
        if single_line_id:
            line = self.env['forecast.line'].browse(single_line_id).exists()
            rules = line.rule_id
        else:
            rules = self.env['forecast.rule'].search([
                ('company_id', '=', self.env.company.id)
            ])

        for rule in rules:
            if single_line_id:
                forecast_lines = line
            else:
                forecast_lines = self.env['forecast.line'].search([
                    ('rule_id', '=', rule.id),
                    ('action_type', 'in', ['transfer','po','partial'])
                ])
            if not forecast_lines:
                self.create_log(rule, [{
                    'status': "failed",
                    'reason': "No forecast lines found"
                }])
                continue

            warehouse_map = {wh.id: wh for wh in rule.source_warehouse_ids}
            wh_move_vals = {wh.id: [] for wh in rule.source_warehouse_ids}
            dest_wh_name = rule.warehouse_id.name

            for line in forecast_lines:
                plan = line.transfer_plan or {}
                for t in plan.get('transfers', []):
                    wh_id = t['wh_id']
                    if wh_id not in wh_move_vals:
                        continue

                    wh_move_vals[wh_id].append((0, 0, {
                        'name': line.product_id.display_name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': t['qty'],
                        'product_uom': line.product_id.uom_id.id,
                        'location_id': warehouse_map[wh_id].lot_stock_id.id,
                        'location_dest_id': rule.warehouse_id.lot_stock_id.id,
                        'company_id': self.env.company.id,
                    }))

            picking_id_to_name = {}
            for wh_id, moves in wh_move_vals.items():
                if not moves:
                    continue

                src_location_id = warehouse_map[wh_id].lot_stock_id.id
                dest_location_id = rule.warehouse_id.lot_stock_id.id

                existing_picking = self.env['stock.picking'].search([
                    ('picking_type_id', '=', rule.picking_type_id.id),
                    ('location_id', '=', src_location_id),
                    ('location_dest_id', '=', dest_location_id),
                    ('state', 'in', ['draft', 'confirmed', 'assigned']),
                    ('company_id', '=', self.env.company.id),
                ], limit=1)

                if existing_picking:
                    for move_tuple in moves:
                        move_vals = move_tuple[2]
                        existing_move = existing_picking.move_ids.filtered(
                            lambda m: m.product_id.id == move_vals['product_id']
                        )[:1]
                        if existing_move:
                            existing_move.product_uom_qty += move_vals['product_uom_qty']
                        else:
                            existing_picking.write({'move_ids': [(0, 0, move_vals)]})
                    picking_id_to_name[wh_id] = existing_picking.name
                else:
                    picking = self.env['stock.picking'].create({
                        'picking_type_id': rule.picking_type_id.id,
                        'location_id': src_location_id,
                        'location_dest_id': dest_location_id,
                        'origin': rule.name,
                        'company_id': self.env.company.id,
                        'move_ids': moves,
                    })
                    picking.action_confirm()
                    picking_id_to_name[wh_id] = picking.name

            execution_log_lines = []

            for line in forecast_lines:
                plan = line.transfer_plan or {}

                final_log_lines = []
                total_taken = 0.0

                for t in plan.get('transfers', []):
                    wh_id = t['wh_id']
                    qty = t['qty']
                    total_taken += qty

                    pick_name = picking_id_to_name.get(wh_id, "N/A")
                    msg = f"Internal Transfer : {t['wh_name']} --> {dest_wh_name} {qty} quantity ({pick_name})"
                    if t.get('reason'):
                        msg += f" {t['reason']}"

                    final_log_lines.append(msg)

                po_qty = plan.get('po_qty', 0)
                po_flag = False

                if po_qty > 0:
                    po_flag, po_msg = line.create_purchase_order(po_qty)
                    final_log_lines.append(po_msg)

                orig_qty = plan.get('orig_forecast_qty', 0)
                status = 'success' if (total_taken >= orig_qty or po_flag) else 'partial'
                line.transfer_state="processed"

                execution_log_lines.append({
                    'product_id': line.product_id.id,
                    'category_id': line.product_id.categ_id.id,
                    'status': status,
                    'reason': "\n".join(final_log_lines)
                })

            self.create_log(rule, execution_log_lines)

    def create_log(self, rule, log_lines):
        log = self.env['transfer.log'].create({'rule_id': rule.id})
        for line in log_lines:
            line['log_id'] = log.id
        self.env['transfer.log.line'].create(log_lines)

