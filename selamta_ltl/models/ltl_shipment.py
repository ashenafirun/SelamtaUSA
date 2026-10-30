# -*- coding: utf-8 -*-
import base64
from datetime import timedelta
import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.tools import float_round

from .ltl_common import FREIGHT_CLASSES, UNIT_TYPES, class_number, digits_only

_logger = logging.getLogger(__name__)

CUBIC_INCHES_PER_FOOT = 1728.0
DEFAULT_TOLERANCE = 1.0
INSIDE_DELIVERY_CODE = 'INSIDE_DEL'
# Labels printed per handling unit: one on each of two sides of a pallet, one per box.
# Change with system parameters selamta_ltl.pallet_label_copies / box_label_copies.
DEFAULT_LABEL_COPIES = {'pallet': 2, 'box': 1}


class LtlShipment(models.Model):
    _name = 'selamta.ltl.shipment'
    _description = 'LTL shipment'
    _inherit = ['mail.thread.main.attachment', 'mail.activity.mixin']
    _order = 'ship_date desc, id desc'

    name = fields.Char(
        'Reference', required=True, copy=False, readonly=True, index=True,
        default=lambda self: _('New'),
        help='Our shipment number. Printed as the BOL number unless the carrier or broker '
             'assigns its own.')
    company_id = fields.Many2one(
        'res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection(
        [
            ('draft', 'Not booked'),
            ('booked', 'Booked'),
            ('in_transit', 'Picked up'),
            ('delivered', 'Delivered'),
            ('cancel', 'Cancelled'),
        ],
        default='draft', required=True, tracking=True, copy=False, index=True)

    picking_ids = fields.One2many('stock.picking', 'ltl_shipment_id', 'Delivery orders')
    picking_count = fields.Integer(compute='_compute_picking_count')
    customer_ids = fields.Many2many(
        'res.partner', string='Customers', compute='_compute_customers',
        help='The customers whose orders are on this shipment.')
    consolidated = fields.Boolean(
        'Several customers', compute='_compute_customers',
        help='Orders for more than one customer, dropped at one place.')
    order_refs = fields.Char(
        'Order references', compute='_compute_order_refs',
        help='Sales orders and customer PO numbers of the delivery orders on this shipment.')

    shipper_id = fields.Many2one(
        'res.partner', 'Ship from', required=True,
        default=lambda self: self.env.company.partner_id)
    partner_id = fields.Many2one('res.partner', 'Consignee', required=True, tracking=True)
    receiving_hours = fields.Char(compute='_compute_receiving_hours')

    carrier_id = fields.Many2one(
        'delivery.carrier', 'Carrier', tracking=True, domain=[('ltl_enabled', '=', True)])
    vendor_id = fields.Many2one(
        'res.partner', 'Bills come from', compute='_compute_vendor_id', store=True,
        readonly=False, index=True, tracking=True,
        help='The vendor whose bill pays for this shipment. Taken from the carrier.')
    freight_terms = fields.Selection(
        [('prepaid', 'Prepaid'), ('collect', 'Collect'), ('third_party', 'Third party')],
        default='prepaid', required=True)
    ship_date = fields.Date(
        'Pickup date', default=lambda self: self._default_ship_date(), tracking=True,
        help='The day the carrier picks up. Sent with the rate request and the pickup booking.')
    pickup_ready_time = fields.Float(
        'Ready at', compute='_compute_pickup_times', store=True, readonly=False, tracking=True,
        help='When the freight is ready for the driver. Filled in from the carrier; change it '
             'before booking if needed.')
    pickup_close_time = fields.Float(
        'Dock closes', compute='_compute_pickup_times', store=True, readonly=False, tracking=True,
        help='Latest time the driver can pick up. Filled in from the carrier.')
    pickup_warning = fields.Char(compute='_compute_pickup_warning')
    delivered_date = fields.Date('Delivered on', tracking=True, copy=False)

    quote_source = fields.Selection(
        [('api', 'Carrier connection'), ('website', 'Carrier website'), ('phone', 'Phone / email')],
        'Quote from', copy=False)
    quote_number = fields.Char(tracking=True, copy=False)
    quote_expires = fields.Date(copy=False)
    transit_days = fields.Integer(copy=False)
    quoted_amount = fields.Monetary('Quoted', tracking=True, copy=False)
    charge_ids = fields.One2many(
        'selamta.ltl.shipment.charge', 'shipment_id', 'Quoted charges', copy=False)

    pro_number = fields.Char('PRO', tracking=True, copy=False, index=True)
    pro_digits = fields.Char(compute='_compute_digits', store=True, index=True)
    bol_number = fields.Char(
        'Carrier BOL number', copy=False, tracking=True,
        help='Only when the carrier or broker gives the load its own BOL number.')
    bol_reference = fields.Char('BOL number', compute='_compute_bol_reference')
    print_carrier_name = fields.Char(
        'Carrier on documents', compute='_compute_print_carrier',
        help='Carrier name printed on the BOL and labels. A broker connection (Priority1) '
             'prints the carrier that actually picks up.')
    print_carrier_scac = fields.Char('SCAC on documents', compute='_compute_print_carrier')
    bol_digits = fields.Char(compute='_compute_digits', store=True, index=True)
    pickup_number = fields.Char('Pickup confirmation', copy=False)
    tracking_status = fields.Char('Carrier status', copy=False)

    accessorial_ids = fields.Many2many(
        'selamta.ltl.accessorial', string='Services ordered',
        help='Extra services ordered from the carrier. Anything not listed is not authorized '
             'and is printed that way on the BOL.')
    special_instructions = fields.Text(
        'Delivery instructions',
        help='Printed in the Delivery Instructions box on the BOL, after the services ordered, '
             'e.g. dock door or who to call.')
    pickup_instructions = fields.Text(
        help='Printed in the Pickup Instructions box on the BOL, after the pickup number and '
             'quote number, e.g. dock hours or where the freight is.')
    inside_delivery_ordered = fields.Boolean(compute='_compute_inside_delivery_ordered')

    unit_ids = fields.One2many(
        'selamta.ltl.shipment.unit', 'shipment_id', 'Pallets and boxes', copy=True)
    total_units = fields.Integer('Handling units', compute='_compute_totals', store=True)
    total_weight = fields.Float('Weight (lb)', compute='_compute_totals', store=True)
    total_cube = fields.Float('Cube (ft³)', compute='_compute_totals', store=True, digits=(16, 2))
    density = fields.Float('Density (lb/ft³)', compute='_compute_totals', store=True, digits=(16, 2))
    class_warning = fields.Text(compute='_compute_class_warning', store=True)

    bill_ids = fields.Many2many(
        'account.move', 'selamta_ltl_shipment_move_rel', 'shipment_id', 'move_id',
        'Carrier bills', copy=False, domain=[('move_type', 'in', ('in_invoice', 'in_refund'))])
    bill_count = fields.Integer(compute='_compute_bill_count')
    billed_amount = fields.Monetary('Billed', compute='_compute_billing', store=True)
    variance = fields.Monetary(
        compute='_compute_billing', store=True,
        help='Billed minus quoted. Positive means the carrier billed more than the quote.')
    variance_percent = fields.Float('Variance %', compute='_compute_billing', store=True)
    bill_status = fields.Selection(
        [
            ('not_billed', 'Not billed'),
            ('ok', 'Billed as quoted'),
            ('over', 'Billed over quote'),
            ('under', 'Billed under quote'),
            ('no_quote', 'Billed, no quote on file'),
        ],
        compute='_compute_billing', store=True, index=True)

    # ------------------------------------------------------------------ computes

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for shipment in self:
            shipment.picking_count = len(shipment.picking_ids)

    @api.depends('picking_ids.partner_id.commercial_partner_id')
    def _compute_customers(self):
        for shipment in self:
            customers = shipment.picking_ids.mapped('partner_id.commercial_partner_id')
            shipment.customer_ids = customers
            shipment.consolidated = len(customers) > 1

    @api.depends('picking_ids.origin', 'picking_ids.sale_id.client_order_ref')
    def _compute_order_refs(self):
        for shipment in self:
            refs = []
            for picking in shipment.picking_ids:
                sale = picking.sale_id if 'sale_id' in picking._fields else False
                for ref in (picking.origin, sale and sale.client_order_ref):
                    if ref and ref not in refs:
                        refs.append(ref)
            shipment.order_refs = ', '.join(refs) or False

    @api.depends('partner_id')
    def _compute_receiving_hours(self):
        for shipment in self:
            business = shipment.partner_id.commercial_partner_id
            hours = False
            if business and 'selamta_receiving_hours' in business._fields:
                hours = business.selamta_receiving_hours or False
            shipment.receiving_hours = hours

    @api.depends('carrier_id')
    def _compute_pickup_times(self):
        for shipment in self:
            carrier = shipment.carrier_id
            if carrier:
                shipment.pickup_ready_time = carrier.ltl_ready_time
                shipment.pickup_close_time = carrier.ltl_close_time
            else:
                shipment.pickup_ready_time = shipment.pickup_ready_time or 10.0
                shipment.pickup_close_time = shipment.pickup_close_time or 16.0

    @api.depends('ship_date', 'pickup_ready_time', 'pickup_close_time', 'state')
    def _compute_pickup_warning(self):
        today = fields.Date.context_today(self)
        for shipment in self:
            warning = False
            if shipment.state == 'draft' and shipment.ship_date:
                if shipment.ship_date < today:
                    warning = _('The pickup date is in the past.')
                elif shipment.ship_date.weekday() >= 5:
                    warning = _('The pickup date is a %s: most LTL carriers do not pick up on weekends.',
                                shipment.ship_date.strftime('%A'))
            if shipment.pickup_close_time <= shipment.pickup_ready_time:
                warning = _('The dock closes before the freight is ready: check the pickup times.')
            shipment.pickup_warning = warning

    @api.model
    def _default_ship_date(self):
        """Today, or the next weekday when it is the weekend or already past 3 PM."""
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        day = now.date()
        if now.hour >= 15:
            day += timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        return day

    @api.model
    def _format_time(self, hours):
        """10.5 -> '10:30 AM'."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        suffix = 'AM' if hour % 24 < 12 else 'PM'
        return '%d:%02d %s' % ((hour % 12) or 12, minute, suffix)

    def _check_pickup(self):
        """Before booking: a pickup date that is not in the past and a sensible window."""
        today = fields.Date.context_today(self)
        for shipment in self:
            if not shipment.ship_date:
                raise UserError(_('Set the pickup date on %s.', shipment.name))
            if shipment.ship_date < today:
                raise UserError(_('The pickup date on %s is in the past.', shipment.name))
            if shipment.pickup_close_time <= shipment.pickup_ready_time:
                raise UserError(_('On %s the dock closes before the freight is ready.', shipment.name))

    @api.depends('carrier_id')
    def _compute_vendor_id(self):
        for shipment in self:
            vendor = shipment.carrier_id.ltl_vendor_id
            shipment.vendor_id = vendor.commercial_partner_id if vendor else shipment.vendor_id

    @api.depends('pro_number', 'bol_number', 'name')
    def _compute_digits(self):
        for shipment in self:
            shipment.pro_digits = digits_only(shipment.pro_number) or False
            shipment.bol_digits = digits_only(shipment.bol_number or shipment.name) or False

    @api.depends('carrier_id.name', 'carrier_id.ltl_scac')
    def _compute_print_carrier(self):
        for shipment in self:
            shipment.print_carrier_name = shipment.carrier_id.name or False
            shipment.print_carrier_scac = shipment.carrier_id.ltl_scac or False

    @api.depends('bol_number', 'name')
    def _compute_bol_reference(self):
        for shipment in self:
            shipment.bol_reference = shipment.bol_number or shipment.name

    @api.depends('unit_ids.quantity', 'unit_ids.weight', 'unit_ids.cube')
    def _compute_totals(self):
        for shipment in self:
            units = shipment.unit_ids
            shipment.total_units = sum(units.mapped('quantity'))
            shipment.total_weight = sum(units.mapped('weight'))
            shipment.total_cube = sum(units.mapped('cube'))
            shipment.density = (
                shipment.total_weight / shipment.total_cube if shipment.total_cube else 0.0)

    @api.depends('unit_ids.class_note', 'unit_ids.freight_class', 'unit_ids.sequence')
    def _compute_class_warning(self):
        for shipment in self:
            notes = []
            for index, unit in enumerate(shipment.unit_ids.sorted('sequence'), start=1):
                if unit.class_note:
                    notes.append(_('Line %(n)s: %(note)s', n=index, note=unit.class_note))
            shipment.class_warning = '\n'.join(notes) or False

    @api.depends('bill_ids')
    def _compute_bill_count(self):
        for shipment in self:
            shipment.bill_count = len(shipment.bill_ids)

    @api.depends(
        'quoted_amount', 'bill_ids.amount_total', 'bill_ids.state', 'bill_ids.move_type',
        'bill_ids.ltl_shipment_ids', 'bill_ids.ltl_shipment_ids.quoted_amount')
    def _compute_billing(self):
        tolerance = self._variance_tolerance()
        for shipment in self:
            billed = 0.0
            bills = shipment.bill_ids.filtered(lambda m: m.state != 'cancel')
            for bill in bills:
                sign = -1.0 if bill.move_type == 'in_refund' else 1.0
                billed += sign * bill.amount_total * shipment._bill_share(bill)
            billed = float_round(billed, precision_digits=2)
            shipment.billed_amount = billed
            if not bills:
                shipment.variance = 0.0
                shipment.variance_percent = 0.0
                shipment.bill_status = 'not_billed'
                continue
            if not shipment.quoted_amount:
                shipment.variance = 0.0
                shipment.variance_percent = 0.0
                shipment.bill_status = 'no_quote'
                continue
            variance = float_round(billed - shipment.quoted_amount, precision_digits=2)
            shipment.variance = variance
            shipment.variance_percent = variance / shipment.quoted_amount * 100.0
            if abs(variance) <= tolerance:
                shipment.bill_status = 'ok'
            else:
                shipment.bill_status = 'over' if variance > 0 else 'under'

    def _bill_share(self, bill):
        """Part of a bill that belongs to this shipment. A bill that covers several
        shipments (a statement) is split in proportion to their quotes, or evenly when a
        quote is missing."""
        self.ensure_one()
        shipments = bill.ltl_shipment_ids
        if len(shipments) <= 1:
            return 1.0
        quoted = shipments.mapped('quoted_amount')
        if all(q > 0 for q in quoted):
            return self.quoted_amount / sum(quoted)
        return 1.0 / len(shipments)

    @api.model
    def _variance_tolerance(self):
        value = self.env['ir.config_parameter'].sudo().get_param(
            'selamta_ltl.variance_tolerance', DEFAULT_TOLERANCE)
        try:
            return float(value)
        except (TypeError, ValueError):
            return DEFAULT_TOLERANCE

    # ------------------------------------------------------------------ CRUD

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('selamta.ltl.shipment') or _('New')
        shipments = super().create(vals_list)
        shipments._sync_pickings()
        return shipments

    def write(self, vals):
        res = super().write(vals)
        if {'pro_number', 'carrier_id'} & set(vals):
            self._sync_pickings()
        return res

    def _sync_pickings(self):
        """Keep the carrier and tracking reference on the delivery orders in step."""
        for shipment in self:
            for picking in shipment.picking_ids:
                vals = {}
                if shipment.carrier_id and picking.carrier_id != shipment.carrier_id:
                    vals['carrier_id'] = shipment.carrier_id.id
                if shipment.pro_number and picking.carrier_tracking_ref != shipment.pro_number:
                    vals['carrier_tracking_ref'] = shipment.pro_number
                if vals:
                    picking.write(vals)

    # ------------------------------------------------------------------ build from deliveries

    @api.model
    def _address_key(self, partner):
        """What makes two delivery addresses the same place."""
        def clean(value):
            return ' '.join((value or '').lower().replace('.', '').replace(',', '').split())
        return (clean(partner.street), clean(partner.street2), clean(partner.city),
                partner.state_id.id, clean(partner.zip)[:5], partner.country_id.id)

    @api.model
    def _needs_drop_choice(self, pickings, shipment=None):
        """True when the deliveries (and the shipment they would join) are not all going
        to the same address, so someone has to say where the truck delivers."""
        partners = pickings.filtered(lambda p: p.state != 'cancel').mapped('partner_id')
        if shipment:
            partners |= shipment.partner_id
        return len({self._address_key(p) for p in partners}) > 1

    @api.model
    def _create_from_pickings(self, pickings, consignee=None):
        """Put the delivery orders on one LTL shipment, with handling units from their
        packages, and return it.

        * If one of them is already on a shipment that has not been picked up, the others
          join that shipment.
        * Deliveries can be for different customers when the truck drops them all at one
          place (customers next to each other, or one receiving for another). When the
          addresses differ, ``consignee`` says where the truck delivers.
        """
        pickings = pickings.filtered(lambda p: p.state != 'cancel')
        if not pickings:
            raise UserError(_('Select at least one delivery order that is not cancelled.'))
        existing = pickings.mapped('ltl_shipment_id')
        if len(existing) > 1:
            raise UserError(_(
                'These delivery orders are already on different LTL shipments: %s',
                ', '.join(existing.mapped('name'))))
        if existing and existing.state not in ('draft', 'booked'):
            raise UserError(_(
                '%s has already been picked up; book the other deliveries on a new shipment.',
                existing.name))
        new = pickings.filtered(lambda p: not p.ltl_shipment_id)
        if not consignee and self._needs_drop_choice(pickings, existing or None):
            raise UserError(_(
                'These deliveries go to different addresses. Choose where the truck delivers.'))
        if existing:
            if new:
                existing._add_pickings(new, consignee)
            return existing

        first = pickings[0]
        consignee = consignee or first.partner_id
        warehouse_partner = first.picking_type_id.warehouse_id.partner_id
        vals = {
            'partner_id': consignee.id,
            'shipper_id': (warehouse_partner or first.company_id.partner_id).id,
            'company_id': first.company_id.id,
            'accessorial_ids': [(6, 0, self._accessorials_for(consignee).ids)],
            'unit_ids': [(0, 0, unit) for unit in self._units_from_pickings(pickings)],
        }
        carrier = pickings.mapped('carrier_id').filtered('ltl_enabled')[:1]
        if carrier:
            vals['carrier_id'] = carrier.id
        shipment = self.create(vals)
        pickings.write({'ltl_shipment_id': shipment.id})
        shipment._sync_pickings()
        return shipment

    def _add_pickings(self, pickings, consignee=None):
        """Add more delivery orders (and their pallets/boxes) to this shipment."""
        self.ensure_one()
        if self.state not in ('draft', 'booked'):
            raise UserError(_('%s has already been picked up.', self.name))
        pickings = pickings.filtered(lambda p: p.state != 'cancel' and p.ltl_shipment_id != self)
        taken = pickings.filtered('ltl_shipment_id')
        if taken:
            raise UserError(_(
                'These delivery orders are already on another LTL shipment: %s',
                ', '.join(taken.mapped('name'))))
        if not pickings:
            return self
        if not consignee and self._needs_drop_choice(pickings, self):
            raise UserError(_(
                'These deliveries go to a different address than %s. Choose where the truck delivers.',
                self.name))
        last = max(self.unit_ids.mapped('sequence') or [0])
        units = self._units_from_pickings(pickings)
        for unit in units:
            unit['sequence'] += last
        vals = {'unit_ids': [(0, 0, unit) for unit in units]}
        if consignee and consignee != self.partner_id:
            vals['partner_id'] = consignee.id
            vals['accessorial_ids'] = [(6, 0, self._accessorials_for(consignee).ids)]
        was_booked = self.state == 'booked'
        self.write(vals)
        pickings.write({'ltl_shipment_id': self.id})
        self._sync_pickings()
        note = _('Added %s to this shipment.', ', '.join(pickings.mapped('name')))
        if was_booked:
            note += ' ' + _(
                'It was already booked with fewer pallets: tell the carrier about the extra '
                'freight (or re-shop) before pickup, and print the BOL again.')
            self.activity_schedule(
                'mail.mail_activity_data_todo', summary=_('Update the carrier: freight added'),
                note=note)
        self.message_post(body=note)
        return self

    @api.model
    def _accessorials_for(self, consignee):
        """Services the delivery location needs, from its delivery services on the contact."""
        services = self.env['selamta.ltl.accessorial']
        business = consignee.commercial_partner_id
        if 'selamta_delivery_service_ids' in business._fields:
            services = services._from_service_names(
                business.selamta_delivery_service_ids.mapped('name'))
        return services

    @api.model
    def _units_from_pickings(self, pickings):
        """Handling unit lines for the delivery orders.

        * A package whose package type is marked as an LTL pallet or box (Inventory >
          Configuration > Package Types) becomes its own line, with that type's length and
          width and the package's weight. Such a package can hold several delivery orders.
        * Everything else (cases packed by product packaging, loose products) goes on one
          pallet line per delivery order with its total weight. Staff then set how many
          pallets it is and measure them.
        Lines start without height (and without length/width when the type has none):
        the class is worked out once they are measured.
        """
        to_inch = self.env.ref('uom.product_uom_inch')
        to_lb = self.env.ref('uom.product_uom_lb')
        product_tmpl = self.env['product.template']
        length_uom = product_tmpl._get_length_uom_id_from_ir_config_parameter()
        weight_uom = product_tmpl._get_weight_uom_id_from_ir_config_parameter()

        def inches(value):
            return float_round(length_uom._compute_quantity(value or 0.0, to_inch, round=False), 1)

        def pounds(value):
            return float_round(weight_uom._compute_quantity(value or 0.0, to_lb, round=False), 0)

        def line_qty(ml):
            return ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id, round=False)

        units = []
        nmfc_item, nmfc_sub = self._default_nmfc()
        all_lines = pickings.move_line_ids
        ltl_lines = all_lines.filtered(lambda ml: ml.result_package_id.package_type_id.ltl_unit_type)
        for package in ltl_lines.result_package_id:
            package_lines = ltl_lines.filtered(lambda ml, pkg=package: ml.result_package_id == pkg)
            package_type = package.package_type_id
            weight = package.shipping_weight or (package_type.base_weight or 0.0) + sum(
                line_qty(ml) * ml.product_id.weight for ml in package_lines)
            units.append({
                'quantity': 1,
                'unit_type': package_type.ltl_unit_type,
                'package_type_id': package_type.id,
                'package_id': package.id,
                'picking_ids': [(6, 0, package_lines.picking_id.ids)],
                'length': inches(package_type.packaging_length),
                'width': inches(package_type.width),
                'height': inches(package_type.height),
                'weight': pounds(weight),
                'description': self._describe(package_lines.product_id),
                'nmfc_item': nmfc_item,
                'nmfc_sub': nmfc_sub,
            })
        for picking in pickings:
            weight = 0.0
            products = self.env['product.product']
            for move in picking.move_ids.filtered(lambda m: m.state != 'cancel'):
                if move.move_line_ids:
                    qty = sum(line_qty(ml) for ml in move.move_line_ids - ltl_lines)
                else:
                    qty = move.product_qty
                if qty > 0:
                    weight += qty * move.product_id.weight
                    products |= move.product_id
            other_packages = (picking.move_line_ids - ltl_lines).result_package_id
            weight += sum(other_packages.mapped('package_type_id.base_weight'))
            if products:
                units.append({
                    'picking_ids': [(6, 0, picking.ids)],
                    'quantity': 1,
                    'unit_type': 'pallet',
                    'weight': pounds(weight),
                    'description': self._describe(products),
                    'nmfc_item': nmfc_item,
                    'nmfc_sub': nmfc_sub,
                })
        for sequence, unit in enumerate(units, start=1):
            unit['sequence'] = sequence * 10
        return units

    @api.model
    def _describe(self, products):
        names = [p.display_name for p in products[:3]]
        text = ', '.join(names)
        if len(products) > 3:
            text += _(' and %s more', len(products) - 3)
        return text[:120] or _('Freight')

    @api.model
    def _default_nmfc(self):
        params = self.env['ir.config_parameter'].sudo()
        return (params.get_param('selamta_ltl.default_nmfc_item') or False,
                params.get_param('selamta_ltl.default_nmfc_sub') or False)

    def _bol_pickup_lines(self):
        """Lines for the Pickup Instructions box on the BOL."""
        self.ensure_one()
        lines = []
        if self.pickup_number:
            lines.append(_('Pickup number: %s', self.pickup_number))
        if self.quote_number:
            lines.append(_('Carrier quote number: %s', self.quote_number))
        if self.ship_date:
            lines.append(_('Pickup %(day)s %(date)s, ready %(ready)s, dock closes %(close)s',
                           day=self.ship_date.strftime('%a'), date=self.ship_date.strftime('%m/%d/%Y'),
                           ready=self._format_time(self.pickup_ready_time),
                           close=self._format_time(self.pickup_close_time)))
        for service in self.accessorial_ids.filtered(lambda a: a.code.endswith('_PU')):
            lines.append(service.name.upper())
        if self.pickup_instructions:
            lines.extend(l.strip() for l in self.pickup_instructions.splitlines() if l.strip())
        return lines

    def _bol_delivery_lines(self):
        """Lines for the Delivery Instructions box on the BOL (and the carrier's own BOL):
        the delivery services ordered, NO INSIDE DELIVERY unless it was ordered, receiving
        hours, then the delivery instructions typed on the shipment."""
        self.ensure_one()
        lines = [service.name.upper() for service in
                 self.accessorial_ids.filtered(lambda a: not a.code.endswith('_PU'))]
        if not self.inside_delivery_ordered:
            lines.append(_('NO INSIDE DELIVERY'))
        if self.receiving_hours:
            lines.append(_('Receiving hours: %s', self.receiving_hours))
        if self.special_instructions:
            lines.extend(l.strip() for l in self.special_instructions.splitlines() if l.strip())
        return lines

    @api.depends('accessorial_ids.code')
    def _compute_inside_delivery_ordered(self):
        for shipment in self:
            shipment.inside_delivery_ordered = INSIDE_DELIVERY_CODE in shipment.accessorial_ids.mapped('code')

    # ------------------------------------------------------------------ actions

    def _open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('LTL shipment'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_add_deliveries(self):
        self.ensure_one()
        if self.state not in ('draft', 'booked'):
            raise UserError(_('%s has already been picked up.', self.name))
        wizard = self.env['selamta.ltl.drop.wizard'].create({
            'shipment_id': self.id, 'partner_id': self.partner_id.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add deliveries to %s', self.name),
            'res_model': 'selamta.ltl.drop.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_rate_shop(self):
        self.ensure_one()
        if self.state not in ('draft', 'booked'):
            raise UserError(_('Rates can only be shopped before pickup.'))
        if not self._units_complete() and not self._parcel_possible():
            self._check_units_complete()  # explains what to measure
        wizard = self.env['selamta.ltl.rate.wizard'].create({'shipment_id': self.id})
        wizard._fetch_rates()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rates for %s', self.name),
            'res_model': 'selamta.ltl.rate.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _units_complete(self):
        self.ensure_one()
        return bool(self.unit_ids) and not self.unit_ids.filtered(
            lambda u: not (u.length and u.width and u.height and u.weight))

    def _parcel_possible(self):
        """Light enough for a parcel quote, and a parcel carrier is set up (UPS...)."""
        self.ensure_one()
        limit = float(self.env['ir.config_parameter'].sudo().get_param('selamta_ltl.parcel_max_weight', 300) or 0)
        return bool(self.unit_ids) and bool(limit) and self.total_weight <= limit and bool(
            self.env['delivery.carrier'].search_count([('ltl_parcel', '=', True)]))

    def _check_units_complete(self):
        for shipment in self:
            if not shipment.unit_ids:
                raise UserError(_('Add the pallets or boxes on %s first.', shipment.name))
            missing = shipment.unit_ids.filtered(
                lambda u: not (u.length and u.width and u.height and u.weight))
            if missing:
                raise UserError(_(
                    'Measure every pallet or box on %(name)s first: length, width, height and '
                    'weight are needed to work out the class. Missing on: %(lines)s',
                    name=shipment.name, lines=', '.join(missing.mapped('description'))))

    def action_confirm_booking(self):
        for shipment in self:
            if not shipment.carrier_id:
                raise UserError(_('Choose the carrier on %s before confirming.', shipment.name))
            shipment._check_pickup()
            shipment._check_units_complete()
            shipment.state = 'booked'

    def action_mark_picked_up(self):
        self.filtered(lambda s: s.state in ('draft', 'booked')).write({'state': 'in_transit'})

    def action_mark_delivered(self):
        for shipment in self.filtered(lambda s: s.state != 'cancel'):
            shipment.write({
                'state': 'delivered',
                'delivered_date': shipment.delivered_date or fields.Date.context_today(shipment),
            })

    def action_cancel(self):
        """Cancel the shipment. A booked pickup is cancelled with the carrier first when its
        connection can do that; otherwise the shipment is cancelled in Odoo only and staff are
        told to call the carrier."""
        call_carrier = []
        odoo_only = self.env.context.get('ltl_odoo_only')
        for shipment in self:
            carrier = shipment.carrier_id
            booked = shipment.state in ('booked', 'in_transit')
            if booked and odoo_only:
                shipment.message_post(body=_(
                    'Cancelled in Odoo only; the pickup was cancelled with %s outside Odoo.',
                    carrier.name or _('the carrier')))
            elif booked and carrier and carrier.ltl_can('cancel'):
                try:
                    carrier.ltl_cancel(shipment)
                except UserError as error:
                    action = self.env.ref('selamta_ltl.action_server_ltl_cancel_odoo_only',
                                          raise_if_not_found=False)
                    message = _(
                        '%(carrier)s did not cancel the pickup: %(error)s\n\nThe shipment is still '
                        'booked. Cancel it with %(carrier)s by phone, then use "Cancel in Odoo only".',
                        carrier=carrier.name, error=error.args[0] if error.args else error)
                    if action:
                        raise RedirectWarning(message, action.id, _('Cancel in Odoo only'), {
                            'active_id': shipment.id, 'active_ids': shipment.ids,
                            'active_model': shipment._name}) from error
                    raise UserError(message) from error
                shipment.message_post(body=_('Pickup cancelled with %s.', carrier.name))
            elif booked:
                call_carrier.append(shipment)
                shipment.message_post(body=_(
                    'Cancelled in Odoo only. Call %(carrier)s to cancel the pickup%(pickup)s.',
                    carrier=carrier.name or _('the carrier'),
                    pickup=_(' (pickup number %s)', shipment.pickup_number) if shipment.pickup_number else ''))
        self.write({'state': 'cancel'})
        if call_carrier:
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {
                    'type': 'warning', 'sticky': True,
                    'message': _('Cancelled in Odoo only. Call the carrier to cancel the pickup: %s',
                                 ', '.join('%s (%s)' % (s.name, s.carrier_id.name) for s in call_carrier)),
                    'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
                },
            }
        return True

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_print_bol(self):
        self._check_units_complete()
        return self.env.ref('selamta_ltl.action_report_ltl_bol').report_action(self)

    def action_print_labels(self):
        for shipment in self:
            if not shipment.unit_ids:
                raise UserError(_('Add the pallets or boxes on %s first.', shipment.name))
        return self.env.ref('selamta_ltl.action_report_ltl_label').report_action(self)

    @api.model
    def _label_copies(self, unit_type):
        default = DEFAULT_LABEL_COPIES.get(unit_type, 1)
        value = self.env['ir.config_parameter'].sudo().get_param(
            'selamta_ltl.%s_label_copies' % unit_type, default)
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return default

    def _label_pieces(self):
        """One entry per label to print: every pallet and box is numbered (1 of N over
        the whole shipment); a pallet gets two identical labels, a box one."""
        self.ensure_one()
        pieces = []
        total = self.total_units
        number = 0
        for unit in self.unit_ids.sorted('sequence'):
            copies = self._label_copies(unit.unit_type)
            kind = _('PALLET') if unit.unit_type == 'pallet' else _('BOX')
            for _piece in range(unit.quantity or 0):
                number += 1
                for copy in range(1, copies + 1):
                    pieces.append({
                        'unit': unit, 'kind': kind, 'number': number, 'total': total,
                        'copy': copy, 'copies': copies,
                    })
        return pieces

    def action_view_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.picking_ids.ids)]
        if len(self.picking_ids) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')],
                           'res_id': self.picking_ids.id})
        return action

    def action_view_bills(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('account.action_move_in_invoice_type')
        action['domain'] = [('id', 'in', self.bill_ids.ids)]
        action['context'] = {'default_move_type': 'in_invoice'}
        if len(self.bill_ids) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')],
                           'res_id': self.bill_ids.id})
        return action

    def action_update_tracking(self):
        self._ltl_update_tracking(raise_if_unsupported=True)

    def action_fetch_documents(self):
        for shipment in self:
            carrier = shipment.carrier_id
            if not carrier or not carrier.ltl_can('documents'):
                raise UserError(_('%s has no carrier connection for documents yet.',
                                  carrier.name or shipment.name))
            shipment._attach_documents(carrier.ltl_documents(shipment), _('Documents from %s', carrier.name))

    # ------------------------------------------------------------------ carrier results

    def _apply_quote(self, rate, carrier, source):
        """Save a chosen rate on the shipment (replaces any earlier quote)."""
        self.ensure_one()
        charges = [(5, 0, 0)] + [
            (0, 0, {'code': c.get('code') or False, 'name': c.get('name') or c.get('code') or _('Charge'),
                    'amount': c.get('amount') or 0.0})
            for c in (rate.get('charges') or [])
        ]
        self.write({
            'carrier_id': carrier.id,
            # Keep the pickup window staff set; changing the carrier would otherwise reset it
            # to the carrier's defaults right before booking.
            'pickup_ready_time': self.pickup_ready_time,
            'pickup_close_time': self.pickup_close_time,
            'quote_source': source,
            'quoted_amount': rate.get('total') or 0.0,
            'quote_number': rate.get('quote_number') or False,
            'quote_expires': rate.get('expires') or False,
            'transit_days': rate.get('transit_days') or 0,
            'charge_ids': charges,
        })

    def _apply_booking(self, result):
        """Save what a carrier connection returned from booking."""
        self.ensure_one()
        vals = {'state': 'booked'}
        for key in ('pro_number', 'bol_number', 'pickup_number'):
            if result.get(key):
                vals[key] = result[key]
        self.write(vals)
        self._attach_documents(result.get('documents') or [], _('Booked with %s', self.carrier_id.name))
        self._attach_own_bol()

    def _attach_own_bol(self):
        """Attach our BOL (with the PRO, pickup window and instruction boxes) as the
        shipment's main document, so it is the one printed for the driver. The carrier's
        own BOL stays attached as the carrier copy. Never fails a booking."""
        self.ensure_one()
        try:
            pdf, _type = self.env['ir.actions.report']._render_qweb_pdf(
                'selamta_ltl.report_ltl_bol', self.ids)
        except Exception as error:  # the booking is already made at the carrier
            _logger.warning('Could not attach the BOL for %s: %s', self.name, error)
            return self.env['ir.attachment']
        attachment = self.env['ir.attachment'].create({
            'name': 'BOL %s.pdf' % (self.pro_number or self.bol_reference),
            'raw': pdf,
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.message_main_attachment_id = attachment
        self.message_post(body=_('BOL to print for the driver attached.'), attachment_ids=attachment.ids)
        return attachment

    def _attach_documents(self, documents, note):
        self.ensure_one()
        attachments = self.env['ir.attachment']
        for filename, content in documents or []:
            if isinstance(content, str):
                content = content.encode()
            attachments |= self.env['ir.attachment'].create({
                'name': filename,
                'datas': base64.b64encode(content),
                'res_model': self._name,
                'res_id': self.id,
            })
        if attachments:
            self.message_post(body=note, attachment_ids=attachments.ids)
        return attachments

    def _ltl_update_tracking(self, raise_if_unsupported=False):
        by_carrier = defaultdict(lambda: self.browse())
        for shipment in self:
            carrier = shipment.carrier_id
            if carrier and carrier.ltl_can('track'):
                by_carrier[carrier] |= shipment
            elif raise_if_unsupported:
                raise UserError(_('%s has no carrier connection for tracking yet.',
                                  carrier.name or shipment.name))
        for carrier, shipments in by_carrier.items():
            try:
                results = carrier.ltl_track(shipments) or {}
            except Exception as error:  # one carrier failing must not stop the others
                if raise_if_unsupported:
                    raise
                _logger.warning('LTL tracking failed for %s: %s', carrier.name, error)
                continue
            for shipment in shipments:
                info = results.get(shipment.id) or {}
                vals = {}
                if info.get('status'):
                    vals['tracking_status'] = info['status']
                if info.get('pro_number') and not shipment.pro_number:
                    vals['pro_number'] = info['pro_number']
                if info.get('state') in ('in_transit', 'delivered') and shipment.state != 'delivered':
                    vals['state'] = info['state']
                if info.get('delivered_date'):
                    vals['delivered_date'] = info['delivered_date']
                if vals:
                    shipment.write(vals)
                if info.get('state') == 'delivered' and carrier.ltl_can('documents'):
                    try:
                        shipment._attach_documents(
                            carrier.ltl_documents(shipment), _('Delivery documents from %s', carrier.name))
                    except Exception as error:
                        _logger.warning('LTL documents failed for %s: %s', shipment.name, error)

    @api.model
    def _cron_update_tracking(self):
        shipments = self.search([('state', 'in', ('booked', 'in_transit')),
                                 ('carrier_id', '!=', False)])
        shipments._ltl_update_tracking()


class LtlShipmentUnit(models.Model):
    """One line of pallets or boxes on a shipment. Its class comes from its own
    dimensions and weight (density), not from the products on it."""
    _name = 'selamta.ltl.shipment.unit'
    _description = 'LTL handling unit'
    _order = 'sequence, id'

    shipment_id = fields.Many2one(
        'selamta.ltl.shipment', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    unit_type = fields.Selection(UNIT_TYPES, 'Type', required=True, default='pallet')
    quantity = fields.Integer(
        'Count', default=1, required=True,
        help='Number of identical pallets or boxes on this line (same size and weight each).')
    package_type_id = fields.Many2one('stock.package.type', 'Package type')
    package_id = fields.Many2one('stock.quant.package', 'Package')
    picking_ids = fields.Many2many(
        'stock.picking', 'selamta_ltl_unit_picking_rel', 'unit_id', 'picking_id',
        'Orders on it',
        help='The delivery orders on this pallet or box. One pallet can carry several orders, '
             'also for different customers.')
    customer_ids = fields.Many2many(
        'res.partner', string='For', compute='_compute_for_text')
    for_text = fields.Char(
        'For customers', compute='_compute_for_text',
        help='Customer and order of everything on this pallet, as printed on the BOL.')
    description = fields.Char(required=True, default=lambda self: _('Freight'))
    length = fields.Float('L (in)', digits=(16, 1), help='Length of one pallet or box, inches.')
    width = fields.Float('W (in)', digits=(16, 1), help='Width of one pallet or box, inches.')
    height = fields.Float(
        'H (in)', digits=(16, 1),
        help='Height of one pallet or box in inches, measured with the freight on it, '
             'including the pallet.')
    weight = fields.Float(
        'Weight (lb)', digits=(16, 0),
        help='Total weight of this line in pounds (all pallets or boxes on it, including '
             'the pallets themselves).')
    nmfc_item = fields.Char('NMFC item')
    nmfc_sub = fields.Char('NMFC sub')
    cube = fields.Float('Cube (ft³)', compute='_compute_density', store=True, digits=(16, 2))
    density = fields.Float('Density (lb/ft³)', compute='_compute_density', store=True, digits=(16, 2))
    density_class = fields.Selection(
        FREIGHT_CLASSES, 'Calculated class', compute='_compute_density', store=True,
        help='Class for this density on the NMFC density scale.')
    class_override = fields.Selection(
        FREIGHT_CLASSES, 'Class override',
        help='Leave empty to use the calculated class. Fill in only when the carrier or the '
             'NMFC item calls for a different class.')
    freight_class = fields.Selection(
        FREIGHT_CLASSES, 'Class', compute='_compute_freight_class', store=True,
        help='Class printed on the BOL: the override if set, otherwise the calculated class.')
    class_note = fields.Char(compute='_compute_freight_class', store=True)

    @api.depends('picking_ids.partner_id.commercial_partner_id', 'picking_ids.origin')
    def _compute_for_text(self):
        for unit in self:
            unit.customer_ids = unit.picking_ids.mapped('partner_id.commercial_partner_id')
            parts = []
            for customer in unit.customer_ids:
                orders = unit.picking_ids.filtered(
                    lambda p, c=customer: p.partner_id.commercial_partner_id == c)
                refs = ', '.join(o.origin or o.name for o in orders)
                parts.append('%s (%s)' % (customer.name, refs) if refs else customer.name)
            unit.for_text = '; '.join(parts) or False

    @api.onchange('package_type_id')
    def _onchange_package_type_id(self):
        package_type = self.package_type_id
        if not package_type:
            return
        to_inch = self.env.ref('uom.product_uom_inch')
        length_uom = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()

        def inches(value):
            return float_round(length_uom._compute_quantity(value or 0.0, to_inch, round=False), 1)

        if package_type.ltl_unit_type:
            self.unit_type = package_type.ltl_unit_type
        self.length = inches(package_type.packaging_length) or self.length
        self.width = inches(package_type.width) or self.width
        if package_type.height:
            self.height = inches(package_type.height)

    @api.depends('quantity', 'length', 'width', 'height', 'weight', 'nmfc_item')
    def _compute_density(self):
        scale = self.env['selamta.ltl.density.scale']
        for unit in self:
            cube = (unit.quantity or 0) * unit.length * unit.width * unit.height / CUBIC_INCHES_PER_FOOT
            unit.cube = cube
            unit.density = unit.weight / cube if cube else 0.0
            unit.density_class = scale._class_for_density(unit.density, unit.nmfc_item) if cube and unit.weight else False

    @api.depends('class_override', 'density_class', 'cube', 'weight')
    def _compute_freight_class(self):
        for unit in self:
            unit.freight_class = unit.class_override or unit.density_class or False
            note = False
            if not unit.cube or not unit.weight:
                note = _('measure length, width, height and weight to work out the class')
            elif unit.class_override and unit.density_class and unit.class_override != unit.density_class:
                declared = class_number(unit.class_override)
                measured = class_number(unit.density_class)
                if declared < measured:
                    note = _('class %(declared)s declared, but it measures %(measured)s lb/ft³ '
                             '(class %(cls)s): expect the carrier to reclass it',
                             declared=unit.class_override, measured='%.2f' % unit.density,
                             cls=unit.density_class)
                else:
                    note = _('class %(declared)s declared, but it measures %(measured)s lb/ft³ '
                             '(class %(cls)s): we may be paying for a higher class than needed',
                             declared=unit.class_override, measured='%.2f' % unit.density,
                             cls=unit.density_class)
            unit.class_note = note


class LtlShipmentCharge(models.Model):
    _name = 'selamta.ltl.shipment.charge'
    _description = 'LTL quoted charge'
    _order = 'sequence, id'

    shipment_id = fields.Many2one(
        'selamta.ltl.shipment', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    code = fields.Char()
    name = fields.Char('Charge', required=True)
    currency_id = fields.Many2one(related='shipment_id.currency_id')
    amount = fields.Monetary()
