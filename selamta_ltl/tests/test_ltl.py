# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestLtl(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        Partner = env['res.partner']
        cls.tforce = Partner.create({'name': 'TForce Freight', 'is_company': True})
        cls.aaa = Partner.create({'name': 'AAA Cooper', 'is_company': True})
        cls.gtz = Partner.create({'name': 'GlobalTranz', 'is_company': True})
        cls.p1 = Partner.create({'name': 'Priority1', 'is_company': True})
        cls.customer = Partner.create({
            'name': 'Test Market', 'is_company': True, 'street': '1 Main St',
            'city': 'Atlanta', 'zip': '30303', 'country_id': env.ref('base.us').id,
        })
        freight_product = env['product.product'].create({'name': 'Freight', 'type': 'service'})

        def carrier(name, vendor, match_on='pro'):
            return env['delivery.carrier'].create({
                'name': name, 'product_id': freight_product.id, 'ltl_enabled': True,
                'ltl_vendor_id': vendor.id, 'ltl_match_on': match_on,
            })

        cls.c_tforce = carrier('TForce', cls.tforce)
        cls.c_aaa = carrier('AAA Cooper', cls.aaa)
        cls.c_gtz = carrier('GlobalTranz', cls.gtz, 'bol')
        cls.c_p1 = carrier('Priority1 / XPO', cls.p1, 'manual')

    # ------------------------------------------------------------------ helpers

    def _shipment(self, carrier, pro=False, quoted=0.0, **units):
        unit = {'quantity': 1, 'unit_type': 'pallet', 'description': 'Spices',
                'length': 48, 'width': 40, 'height': 60, 'weight': 900}
        unit.update(units)
        return self.env['selamta.ltl.shipment'].create({
            'partner_id': self.customer.id,
            'carrier_id': carrier.id,
            'pro_number': pro,
            'quoted_amount': quoted,
            'unit_ids': [(0, 0, unit)],
        })

    def _bill(self, vendor, ref, amount, move_type='in_invoice', post=True):
        bill = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': vendor.id,
            'invoice_date': fields.Date.today(),
            'ref': ref,
            'invoice_line_ids': [(0, 0, {
                'name': 'Freight', 'quantity': 1, 'price_unit': amount, 'tax_ids': [(6, 0, [])],
            })],
        })
        if post:
            bill.action_post()
        return bill

    # ------------------------------------------------------------------ class from dimensions

    def test_class_from_pallet_dimensions(self):
        shipment = self._shipment(self.c_tforce)  # 48x40x60 in, 900 lb
        unit = shipment.unit_ids
        self.assertAlmostEqual(unit.cube, 66.67, places=2)
        self.assertAlmostEqual(unit.density, 13.5, places=2)
        self.assertEqual(unit.density_class, '85')  # 12 to <15 lb/ft3
        self.assertEqual(unit.freight_class, '85')
        self.assertFalse(unit.class_note)
        self.assertFalse(shipment.class_warning)

        unit.write({'height': 48, 'weight': 1000})  # 53.33 ft3 -> 18.75 lb/ft3
        self.assertEqual(unit.freight_class, '70')

    def test_density_scale_edges(self):
        scale = self.env['selamta.ltl.density.scale']
        self.assertEqual(scale._class_for_density(0.5), '400')
        self.assertEqual(scale._class_for_density(15.0), '70')
        self.assertEqual(scale._class_for_density(14.99), '85')
        self.assertEqual(scale._class_for_density(50.0), '50')
        self.assertFalse(scale._class_for_density(0))

    def test_box_and_count(self):
        shipment = self._shipment(self.c_tforce, unit_type='box', quantity=4,
                                  length=24, width=20, height=20, weight=300)
        unit = shipment.unit_ids
        self.assertAlmostEqual(unit.cube, 22.22, places=2)  # 4 x 24x20x20 in
        self.assertAlmostEqual(unit.density, 13.5, places=2)  # 300 lb / 22.22 ft3
        self.assertEqual(unit.freight_class, '85')

    def test_class_override_notes(self):
        shipment = self._shipment(self.c_tforce)  # measures 13.5 -> class 85
        unit = shipment.unit_ids
        unit.class_override = '70'
        self.assertEqual(unit.freight_class, '70')
        self.assertIn('reclass', unit.class_note)
        self.assertTrue(shipment.class_warning)
        unit.class_override = '100'
        self.assertIn('higher class', unit.class_note)
        unit.class_override = '85'
        self.assertFalse(unit.class_note)

    def test_nmfc_item_own_scale(self):
        Scale = self.env['selamta.ltl.density.scale']
        Scale.create([
            {'nmfc_item': '99999', 'min_density': 0, 'freight_class': '100'},
            {'nmfc_item': '99999', 'min_density': 13.5, 'freight_class': '77.5'},
        ])
        shipment = self._shipment(self.c_tforce, nmfc_item='99999', height=58)  # 13.97 lb/ft3
        self.assertEqual(shipment.unit_ids.freight_class, '77.5')

    def test_missing_dimensions(self):
        shipment = self._shipment(self.c_tforce, height=0)
        self.assertFalse(shipment.unit_ids.freight_class)
        self.assertIn('measure', shipment.unit_ids.class_note)
        with self.assertRaises(Exception):
            shipment.action_confirm_booking()

    # ------------------------------------------------------------------ bill matching

    def test_match_exact_and_variance(self):
        shipment = self._shipment(self.c_tforce, pro='123456789', quoted=500)
        bill = self._bill(self.tforce, '123456789', 560)
        self.assertEqual(bill.ltl_shipment_ids, shipment)
        self.assertEqual(shipment.billed_amount, 560)
        self.assertEqual(shipment.variance, 60)
        self.assertEqual(shipment.bill_status, 'over')
        self.assertEqual(bill.ltl_variance, 60)

    def test_match_within_tolerance(self):
        shipment = self._shipment(self.c_tforce, pro='223456789', quoted=500)
        self._bill(self.tforce, '223456789', 500.75)
        self.assertEqual(shipment.bill_status, 'ok')

    def test_match_check_digit_on_booking(self):
        shipment = self._shipment(self.c_aaa, pro='77637580-0', quoted=400)
        bill = self._bill(self.aaa, '77637580', 400)
        self.assertEqual(bill.ltl_shipment_ids, shipment)
        self.assertIn('check digit on booking', bill.ltl_match_note)

    def test_match_dash_and_leading_one(self):
        dashed = self._shipment(self.c_tforce, pro='476103633', quoted=100)
        bill = self._bill(self.tforce, '476-103633', 100)
        self.assertEqual(bill.ltl_shipment_ids, dashed)
        short = self._shipment(self.c_tforce, pro='23456700', quoted=100)
        bill2 = self._bill(self.tforce, '123456700', 100)
        self.assertEqual(bill2.ltl_shipment_ids, short)
        self.assertIn('leading 1 on bill', bill2.ltl_match_note)

    def test_exact_wins_over_check_digit(self):
        exact = self._shipment(self.c_tforce, pro='888888888', quoted=100)
        self._shipment(self.c_tforce, pro='8888888881', quoted=100)
        bill = self._bill(self.tforce, '888888888', 100)
        self.assertEqual(bill.ltl_shipment_ids, exact)

    def test_ambiguous_is_left_alone(self):
        self._shipment(self.c_tforce, pro='555555551', quoted=100)
        self._shipment(self.c_tforce, pro='555555552', quoted=100)
        bill = self._bill(self.tforce, '55555555', 100)
        self.assertFalse(bill.ltl_shipment_ids)
        self.assertIn('Several', bill.ltl_match_note)

    def test_other_vendor_and_cancelled_not_matched(self):
        self._shipment(self.c_tforce, pro='333333333', quoted=100)
        bill = self._bill(self.aaa, '333333333', 100)
        self.assertFalse(bill.ltl_shipment_ids)
        cancelled = self._shipment(self.c_aaa, pro='444444444', quoted=100)
        cancelled.action_cancel()
        bill2 = self._bill(self.aaa, '444444444', 100)
        self.assertFalse(bill2.ltl_shipment_ids)

    def test_match_on_bol_number(self):
        shipment = self._shipment(self.c_gtz, quoted=250)
        bill = self._bill(self.gtz, shipment.name, 250)
        self.assertEqual(bill.ltl_shipment_ids, shipment)
        self.assertEqual(shipment.bill_status, 'ok')

    def test_manual_vendor_not_auto_matched(self):
        self._shipment(self.c_p1, pro='666666666', quoted=300)
        bill = self._bill(self.p1, '666666666', 300)
        self.assertFalse(bill.ltl_shipment_ids)

    def test_statement_split_and_refund(self):
        first = self._shipment(self.c_aaa, pro='710000001', quoted=100)
        second = self._shipment(self.c_aaa, pro='710000002', quoted=300)
        statement = self._bill(self.aaa, 'STATEMENT', 480, post=False)
        statement.ltl_shipment_ids = [(6, 0, (first | second).ids)]
        statement.action_post()
        self.assertAlmostEqual(first.billed_amount, 120)
        self.assertAlmostEqual(second.billed_amount, 360)
        credit = self._bill(self.aaa, '710000001', 20, move_type='in_refund')
        self.assertEqual(credit.ltl_shipment_ids, first)
        self.assertAlmostEqual(first.billed_amount, 100)
        self.assertEqual(first.bill_status, 'ok')

    def test_cron_matches_draft_bills(self):
        shipment = self._shipment(self.c_tforce, pro='909090909', quoted=200)
        bill = self._bill(self.tforce, '909090909', 200, post=False)
        self.assertFalse(bill.ltl_shipment_ids)
        self.env['account.move']._cron_ltl_match_bills()
        self.assertEqual(bill.ltl_shipment_ids, shipment)

    # ------------------------------------------------------------------ deliveries, BOL, rate shop

    def _delivery(self, partner, qty=10, origin=False):
        product = self.env['product.product'].create({
            'name': 'Shiro %s' % qty, 'is_storable': True, 'weight': 10.0})
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        customers = self.env.ref('stock.stock_location_customers')
        return self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'partner_id': partner.id,
            'origin': origin,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': customers.id,
            'move_ids': [(0, 0, {
                'name': product.name, 'product_id': product.id, 'product_uom_qty': qty,
                'product_uom': product.uom_id.id,
                'location_id': warehouse.lot_stock_id.id, 'location_dest_id': customers.id,
            })],
        })

    def _neighbor(self, street='2 Main St'):
        return self.env['res.partner'].create({
            'name': 'Neighbor Store', 'is_company': True, 'street': street,
            'city': 'Atlanta', 'zip': '30303', 'country_id': self.env.ref('base.us').id,
        })

    def test_two_deliveries_same_customer_one_shipment(self):
        first = self._delivery(self.customer, 10, 'S00101')
        second = self._delivery(self.customer, 20, 'S00102')
        (first | second).action_ltl_shipment()
        shipment = first.ltl_shipment_id
        self.assertEqual(second.ltl_shipment_id, shipment)
        self.assertEqual(len(shipment.unit_ids), 2)
        self.assertEqual(shipment.unit_ids.mapped('picking_ids'), first | second)
        self.assertIn('S00101', shipment.order_refs)
        self.assertIn('S00102', shipment.order_refs)
        self.assertFalse(shipment.consolidated)
        shipment.pro_number = '777000111'
        self.assertEqual(set((first | second).mapped('carrier_tracking_ref')), {'777000111'})
        shipment.write({'carrier_id': self.c_tforce.id, 'quoted_amount': 300})
        bill = self._bill(self.tforce, '777000111', 300)  # one carrier bill for both orders
        self.assertEqual(bill.ltl_shipment_ids, shipment)
        self.assertEqual(shipment.bill_status, 'ok')

    def test_two_customers_dropped_at_one_place(self):
        neighbor = self._neighbor()
        ours = self._delivery(self.customer, 10, 'S00201')
        theirs = self._delivery(neighbor, 20, 'S00202')
        action = (ours | theirs).action_ltl_shipment()
        self.assertEqual(action['res_model'], 'selamta.ltl.drop.wizard')
        wizard = self.env['selamta.ltl.drop.wizard'].browse(action['res_id'])
        self.assertTrue(wizard.different_addresses)
        wizard.partner_id = neighbor
        wizard.action_confirm()
        shipment = ours.ltl_shipment_id
        self.assertEqual(theirs.ltl_shipment_id, shipment)
        self.assertEqual(shipment.partner_id, neighbor)
        self.assertTrue(shipment.consolidated)
        self.assertEqual(shipment.customer_ids, self.customer | neighbor)
        self.assertEqual(ours.partner_id, self.customer)  # the delivery order keeps its customer
        shipment.unit_ids.write({'length': 48, 'width': 40, 'height': 50})
        html = self.env['ir.actions.report']._render_qweb_html(
            'selamta_ltl.report_ltl_bol', shipment.ids)[0].decode()
        self.assertIn('One stop, orders for', html)
        self.assertIn('Test Market (S00201)', html)
        self.assertIn('Neighbor Store (S00202)', html)

    def test_one_pallet_with_two_customers_orders(self):
        neighbor = self._neighbor()
        ours = self._delivery(self.customer, 10, 'S00401')
        theirs = self._delivery(neighbor, 20, 'S00402')
        (ours | theirs).action_confirm()
        stock = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1).lot_stock_id
        for move in (ours | theirs).move_ids:
            self.env['stock.quant']._update_available_quantity(move.product_id, stock, 100)
        (ours | theirs).action_assign()
        pallet_type = self.env['stock.package.type'].create({
            'name': 'Pallet', 'ltl_unit_type': 'pallet', 'base_weight': 20.0})
        pallet = self.env['stock.quant.package'].create({'package_type_id': pallet_type.id})
        (ours | theirs).move_line_ids.write({'result_package_id': pallet.id})
        shipment = self.env['selamta.ltl.shipment']._create_from_pickings(ours | theirs, consignee=neighbor)
        self.assertEqual(len(shipment.unit_ids), 1)  # one pallet, both orders
        unit = shipment.unit_ids
        self.assertEqual(unit.picking_ids, ours | theirs)
        self.assertEqual(unit.customer_ids, self.customer | neighbor)
        self.assertIn('Test Market (S00401)', unit.for_text)
        self.assertIn('Neighbor Store (S00402)', unit.for_text)
        weight_uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        expected = weight_uom._compute_quantity(20 + 10 * 10 + 20 * 10, self.env.ref('uom.product_uom_lb'), round=False)
        self.assertAlmostEqual(unit.weight, round(expected), places=0)
        unit.write({'length': 48, 'width': 40, 'height': 50})
        html = self.env['ir.actions.report']._render_qweb_html(
            'selamta_ltl.report_ltl_bol', shipment.ids)[0].decode()
        self.assertIn('Test Market (S00401); Neighbor Store (S00402)', html)

    def test_cases_packed_by_packaging_become_one_pallet_line(self):
        # Cases put in packages without an LTL package type (how product packaging splits
        # deliveries) must not each become a pallet.
        picking = self._delivery(self.customer, 6, 'S00601')
        picking.action_confirm()
        stock = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1).lot_stock_id
        self.env['stock.quant']._update_available_quantity(picking.move_ids.product_id, stock, 100)
        picking.action_assign()
        line = picking.move_line_ids
        line.quantity = 2
        for qty in (2, 2):
            line.copy({'quantity': qty})
        for ml in picking.move_line_ids:
            ml.result_package_id = self.env['stock.quant.package'].create({})
        self.assertEqual(len(picking.move_line_ids.result_package_id), 3)
        shipment = self.env['selamta.ltl.shipment']._create_from_pickings(picking)
        self.assertEqual(len(shipment.unit_ids), 1)
        weight_uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        expected = weight_uom._compute_quantity(60.0, self.env.ref('uom.product_uom_lb'), round=False)
        self.assertAlmostEqual(shipment.unit_ids.weight, round(expected), places=0)
        self.assertEqual(shipment.unit_ids.unit_type, 'pallet')
        self.assertFalse(shipment.unit_ids.height)

    def test_combine_two_order_lines_on_one_pallet(self):
        neighbor = self._neighbor()
        ours = self._delivery(self.customer, 10, 'S00501')
        theirs = self._delivery(neighbor, 20, 'S00502')
        shipment = self.env['selamta.ltl.shipment']._create_from_pickings(ours | theirs, consignee=self.customer)
        self.assertEqual(len(shipment.unit_ids), 2)  # loose freight: one line per order
        keep, extra = shipment.unit_ids.sorted('sequence')
        keep.write({'picking_ids': [(6, 0, (ours | theirs).ids)], 'weight': 660})
        extra.unlink()
        self.assertEqual(shipment.unit_ids.customer_ids, self.customer | neighbor)
        self.assertEqual(shipment.total_weight, 660)

    def test_different_addresses_need_a_drop_choice(self):
        other = self._delivery(self._neighbor('9 Far Rd'), 10)
        mine = self._delivery(self.customer, 10)
        with self.assertRaises(Exception):
            self.env['selamta.ltl.shipment']._create_from_pickings(mine | other)

    def test_add_delivery_later(self):
        first = self._delivery(self.customer, 10, 'S00301')
        first.action_ltl_shipment()
        shipment = first.ltl_shipment_id
        shipment.unit_ids.write({'length': 48, 'width': 40, 'height': 50})
        shipment.carrier_id = self.c_tforce
        shipment.action_confirm_booking()
        later = self._delivery(self.customer, 15, 'S00302')
        action = shipment.action_add_deliveries()
        wizard = self.env['selamta.ltl.drop.wizard'].browse(action['res_id'])
        wizard.picking_ids = later
        wizard.action_confirm()
        self.assertEqual(later.ltl_shipment_id, shipment)
        self.assertEqual(len(shipment.unit_ids), 2)
        self.assertTrue(shipment.activity_ids)  # booked already: reminder to tell the carrier
        shipment.action_mark_picked_up()
        too_late = self._delivery(self.customer, 5)
        with self.assertRaises(Exception):
            shipment._add_pickings(too_late)

    def test_from_delivery_order(self):
        product = self.env['product.product'].create({
            'name': 'Berbere 1 lb', 'is_storable': True, 'weight': 10.0})
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'partner_id': self.customer.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [(0, 0, {
                'name': product.name, 'product_id': product.id, 'product_uom_qty': 20,
                'product_uom': product.uom_id.id,
                'location_id': warehouse.lot_stock_id.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            })],
        })
        picking.carrier_id = self.c_tforce
        picking.action_ltl_shipment()
        shipment = picking.ltl_shipment_id
        self.assertTrue(shipment)
        self.assertEqual(shipment.carrier_id, self.c_tforce)
        self.assertEqual(len(shipment.unit_ids), 1)
        weight_uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        expected = weight_uom._compute_quantity(200.0, self.env.ref('uom.product_uom_lb'), round=False)
        self.assertAlmostEqual(shipment.unit_ids.weight, round(expected), places=0)
        self.assertEqual(shipment.unit_ids.unit_type, 'pallet')
        shipment.pro_number = '135792468'
        self.assertEqual(picking.carrier_tracking_ref, '135792468')
        # Same delivery again opens the same shipment.
        picking.action_ltl_shipment()
        self.assertEqual(self.env['selamta.ltl.shipment'].search_count(
            [('picking_ids', 'in', picking.ids)]), 1)

    def test_package_type_fills_unit(self):
        package_type = self.env['stock.package.type'].create({
            'name': 'GMA pallet', 'ltl_unit_type': 'pallet',
            'packaging_length': 48, 'width': 40, 'height': 0,
        })
        unit = self.env['selamta.ltl.shipment.unit'].new({'package_type_id': package_type.id})
        unit._onchange_package_type_id()
        to_inch = self.env.ref('uom.product_uom_inch')
        length_uom = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()
        self.assertAlmostEqual(unit.length, round(length_uom._compute_quantity(48, to_inch, round=False), 1))
        self.assertEqual(unit.unit_type, 'pallet')

    def test_labels_two_per_pallet_one_per_box(self):
        shipment = self._shipment(self.c_tforce, pro='246813579', quantity=2)
        shipment.unit_ids = [(0, 0, {'quantity': 3, 'unit_type': 'box', 'description': 'Coffee',
                                     'length': 24, 'width': 16, 'height': 12, 'weight': 150})]
        pieces = shipment._label_pieces()
        self.assertEqual(len(pieces), 2 * 2 + 3 * 1)  # 2 pallets x 2 labels + 3 boxes x 1
        self.assertEqual([p['number'] for p in pieces], [1, 1, 2, 2, 3, 4, 5])
        self.assertEqual({p['total'] for p in pieces}, {5})
        html = self.env['ir.actions.report']._render_qweb_html(
            'selamta_ltl.report_ltl_label', shipment.ids)[0].decode()
        self.assertEqual(html.count('class="ltl-label"'), 7)
        flat = ' '.join(html.split())
        self.assertIn('<div class="ll-kind">PALLET</div> <div class="ll-num">2 OF 5</div>', flat)
        self.assertIn('<div class="ll-kind">BOX</div> <div class="ll-num">5 OF 5</div>', flat)
        self.assertIn('246813579', html)
        self.assertIn('data:image/png;base64', html)  # PRO barcode
        self.env['ir.config_parameter'].sudo().set_param('selamta_ltl.pallet_label_copies', '1')
        self.assertEqual(len(shipment._label_pieces()), 5)

    def test_pickup_date_and_window(self):
        Shipment = self.env['selamta.ltl.shipment']
        self.assertEqual(Shipment._format_time(10.5), '10:30 AM')
        self.assertEqual(Shipment._format_time(16.0), '4:00 PM')
        self.assertEqual(Shipment._format_time(12.0), '12:00 PM')
        self.assertLess(Shipment._default_ship_date().weekday(), 5)
        self.c_tforce.write({'ltl_ready_time': 9.5, 'ltl_close_time': 15.0})
        shipment = self._shipment(self.c_tforce)
        self.assertEqual((shipment.pickup_ready_time, shipment.pickup_close_time), (9.5, 15.0))
        shipment.write({'ship_date': fields.Date.subtract(fields.Date.today(), days=1)})
        self.assertIn('past', shipment.pickup_warning)
        with self.assertRaisesRegex(Exception, 'past'):
            shipment.action_confirm_booking()
        monday = fields.Date.add(fields.Date.today(), days=(7 - fields.Date.today().weekday()))
        shipment.write({'ship_date': monday, 'pickup_ready_time': 14.0, 'pickup_close_time': 13.0})
        with self.assertRaisesRegex(Exception, 'closes before'):
            shipment.action_confirm_booking()
        shipment.write({'pickup_ready_time': 13.5, 'pickup_close_time': 17.0})
        self.assertIn('ready 1:30 PM, dock closes 5:00 PM', ' '.join(shipment._bol_pickup_lines()))
        # Choosing a rate (same or another carrier) keeps the window staff set.
        shipment._apply_quote({'total': 300.0}, self.c_aaa, 'website')
        self.assertEqual((shipment.carrier_id, shipment.pickup_ready_time, shipment.pickup_close_time),
                         (self.c_aaa, 13.5, 17.0))
        shipment._apply_quote({'total': 290.0}, self.c_tforce, 'website')
        self.assertEqual((shipment.pickup_ready_time, shipment.pickup_close_time), (13.5, 17.0))
        saturday = fields.Date.add(monday, days=5)
        shipment.ship_date = saturday
        self.assertIn('Saturday', shipment.pickup_warning)
        shipment.ship_date = monday
        shipment.action_confirm_booking()
        self.assertEqual(shipment.state, 'booked')

    def test_default_pickup_window_9_to_1730(self):
        carrier = self.env['delivery.carrier'].create({
            'name': 'New LTL', 'product_id': self.c_tforce.product_id.id, 'ltl_enabled': True,
            'ltl_vendor_id': self.tforce.id,
        })
        self.assertEqual((carrier.ltl_ready_time, carrier.ltl_close_time), (9.0, 17.5))
        shipment = self._shipment(carrier)
        self.assertEqual((shipment.pickup_ready_time, shipment.pickup_close_time), (9.0, 17.5))
        no_carrier = self.env['selamta.ltl.shipment'].create({'partner_id': self.customer.id})
        self.assertEqual((no_carrier.pickup_ready_time, no_carrier.pickup_close_time), (9.0, 17.5))
        self.assertIn('ready 9:00 AM, dock closes 5:30 PM', ' '.join(shipment._bol_pickup_lines()))

    def test_pallet_description_foodstuff(self):
        ours = self._delivery(self.customer, 10, 'S00701')
        second = self._delivery(self.customer, 5, 'S00702')
        shipment = self.env['selamta.ltl.shipment']._create_from_pickings(ours | second)
        self.assertEqual(shipment.unit_ids.mapped('description'), ['Foodstuff', 'Foodstuff'])
        # A line added by hand starts as Foodstuff too, and staff can change it.
        shipment.unit_ids = [(0, 0, {'quantity': 1, 'unit_type': 'box', 'weight': 40})]
        added = shipment.unit_ids.sorted('id')[-1]
        self.assertEqual(added.description, 'Foodstuff')
        added.description = 'Coffee beans'
        html = self.env['ir.actions.report']._render_qweb_html(
            'selamta_ltl.report_ltl_bol', shipment.ids)[0].decode()
        self.assertIn('Foodstuff', html)
        self.assertIn('Coffee beans', html)
        # Another default for every new line, from the system parameter.
        self.env['ir.config_parameter'].sudo().set_param('selamta_ltl.default_description', 'Groceries')
        other = self.env['selamta.ltl.shipment']._create_from_pickings(self._delivery(self.customer, 3, 'S00703'))
        self.assertEqual(other.unit_ids.description, 'Groceries')
        # Picking the order on a line shows the sales order with the delivery.
        labelled = ours.with_context(ltl_show_order=True)
        self.assertEqual(labelled.display_name, 'S00701 (%s)' % ours.name)
        self.assertEqual(ours.display_name, ours.name)

    def test_bol_renders(self):
        shipment = self._shipment(self.c_tforce, pro='246813579', quoted=300)
        shipment.accessorial_ids = self.env.ref('selamta_ltl.accessorial_liftgate_delivery')
        html = self.env['ir.actions.report']._render_qweb_html(
            'selamta_ltl.report_ltl_bol', shipment.ids)[0].decode()
        self.assertIn(shipment.name, html)
        self.assertIn('246813579', html)
        self.assertIn('Pickup instructions', html)
        self.assertIn('Delivery instructions', html)
        self.assertIn('NO INSIDE DELIVERY', html)
        self.assertIn('LIFTGATE AT DELIVERY', html)
        self.assertEqual(shipment._bol_delivery_lines()[:2], ['LIFTGATE AT DELIVERY', 'NO INSIDE DELIVERY'])
        shipment.write({'pickup_number': 'WBU41464319', 'quote_number': '800389657',
                        'pickup_instructions': 'Freight at door 2'})
        pickup = shipment._bol_pickup_lines()
        self.assertEqual(pickup[:2], ['Pickup number: WBU41464319', 'Carrier quote number: 800389657'])
        self.assertEqual(pickup[-1], 'Freight at door 2')
        self.assertIn('>85<', html)

    def test_rate_shop_and_booking_through_connection(self):
        shipment = self._shipment(self.c_tforce)
        Carrier = type(self.env['delivery.carrier'])

        def fake_rate(carrier, shipment):
            if carrier == self.c_tforce:
                return [{'total': 412.5, 'transit_days': 2, 'quote_number': 'Q1',
                         'charges': [{'code': 'GFC', 'name': 'Linehaul', 'amount': 412.5}]}]
            return [{'total': 999.0, 'transit_days': 1}]

        def fake_book(carrier, shipment, rate):
            return {'pro_number': '900000001', 'pickup_number': 'PU77',
                    'documents': [('BOL.pdf', b'%PDF-1.4 test')]}

        with patch.object(Carrier, 'fixed_ltl_rate', fake_rate, create=True), \
                patch.object(Carrier, 'fixed_ltl_book', fake_book, create=True):
            action = shipment.action_open_rate_shop()
            wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
            cheapest = wizard.line_ids.sorted('total')[0]
            self.assertEqual(cheapest.carrier_id, self.c_tforce)
            cheapest.action_choose()

        self.assertEqual(shipment.state, 'booked')
        self.assertEqual(shipment.quoted_amount, 412.5)
        self.assertEqual(shipment.quote_number, 'Q1')
        self.assertEqual(shipment.pro_number, '900000001')
        self.assertEqual(shipment.pickup_number, 'PU77')
        self.assertEqual(len(shipment.charge_ids), 1)
        attachments = self.env['ir.attachment'].search(
            [('res_model', '=', shipment._name), ('res_id', '=', shipment.id)])
        self.assertIn('BOL.pdf', attachments.mapped('name'))
        self.assertIn('BOL 900000001.pdf', attachments.mapped('name'))
        self.assertEqual(shipment.message_main_attachment_id.name, 'BOL 900000001.pdf')

    def test_rate_shop_without_connections(self):
        shipment = self._shipment(self.c_tforce)
        action = shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        self.assertFalse(wizard.line_ids)
        self.assertTrue(wizard.message)
        line = self.env['selamta.ltl.rate.wizard.line'].create({
            'wizard_id': wizard.id, 'carrier_id': self.c_aaa.id, 'source': 'website',
            'total': 350.0, 'quote_number': 'WEB-1'})
        line.action_choose()
        self.assertEqual(shipment.state, 'draft')
        self.assertEqual(shipment.carrier_id, self.c_aaa)
        self.assertEqual(shipment.vendor_id, self.aaa)
        self.assertEqual(shipment.quoted_amount, 350.0)

    def test_cancel_without_carrier_connection_says_to_call(self):
        shipment = self._shipment(self.c_aaa, pro='111222333', quoted=300)
        shipment.write({'state': 'booked', 'pickup_number': 'PU55'})
        action = shipment.action_cancel()
        self.assertEqual(shipment.state, 'cancel')
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('Call the carrier', action['params']['message'])
        self.assertIn('pickup number PU55', ' '.join(shipment.message_ids.mapped('body')))
        draft = self._shipment(self.c_aaa)
        self.assertTrue(draft.action_cancel())  # nothing booked: nothing to call about
        self.assertEqual(draft.state, 'cancel')
