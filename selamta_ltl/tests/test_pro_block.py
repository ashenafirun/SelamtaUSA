# -*- coding: utf-8 -*-
"""Pre-assigned PRO blocks (Daylight's electronic PROs)."""
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.selamta_ltl.models.ltl_pro_block import full_pro, luhn_check_digit, pro_passes_check_digit


@tagged('post_install', '-at_install')
class TestProBlock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.customer = env['res.partner'].create({
            'name': 'Test Market', 'is_company': True, 'street': '1 Main St',
            'city': 'Atlanta', 'zip': '30303', 'country_id': env.ref('base.us').id,
        })
        vendor = env['res.partner'].create({'name': 'Daylight Transport', 'is_company': True})
        other = env['res.partner'].create({'name': 'TForce Freight', 'is_company': True})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.daylight = env['delivery.carrier'].create({
            'name': 'Daylight', 'product_id': product.id, 'ltl_enabled': True,
            'ltl_vendor_id': vendor.id, 'ltl_scac': 'DYLT'})
        cls.tforce = env['delivery.carrier'].create({
            'name': 'TForce', 'product_id': product.id, 'ltl_enabled': True, 'ltl_vendor_id': other.id})
        # Daylight's current block as FreightPOP holds it: 184176931-184191922, used up to 184177491.
        cls.block = env['selamta.ltl.pro.block'].create({
            'carrier_id': cls.daylight.id, 'first_base': '18417693', 'last_base': '18419192',
            'next_base': '18417750'})

    def _shipment(self, carrier=None, pro=False):
        return self.env['selamta.ltl.shipment'].create({
            'partner_id': self.customer.id,
            'carrier_id': (carrier or self.daylight).id,
            'pro_number': pro,
            'unit_ids': [(0, 0, {'quantity': 1, 'unit_type': 'pallet', 'description': 'Spices',
                                 'length': 48, 'width': 40, 'height': 60, 'weight': 900})],
        })

    def _book(self, shipment, result=None):
        """Book through a fake carrier connection that returns no PRO (like Daylight)."""
        Carrier = type(self.env['delivery.carrier'])
        answer = result or {'pickup_number': '5896084'}
        with patch.object(Carrier, 'fixed_ltl_rate', lambda c, s: [{'total': 300.0}], create=True), \
                patch.object(Carrier, 'fixed_ltl_book', lambda c, s, r: dict(answer), create=True):
            action = shipment.action_open_rate_shop()
            wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
            wizard.line_ids.filtered(lambda l: l.carrier_id == shipment.carrier_id).action_choose()
        return shipment

    # ------------------------------------------------------------------ check digit

    def test_check_digit_matches_daylight(self):
        # The two worked examples in Daylight's "Algorithm to calculate check digit".
        self.assertEqual(luhn_check_digit('2191167'), 2)
        self.assertEqual(luhn_check_digit('21911684'), 5)
        # The first 16 PROs of the FreightPOP list, from base 18417750 on.
        listed = ['184177509', '184177517', '184177525', '184177533', '184177541', '184177558',
                  '184177566', '184177574', '184177582', '184177590', '184177608', '184177616',
                  '184177624', '184177632', '184177640', '184177657']
        self.assertEqual([full_pro(18417750 + i) for i in range(16)], listed)
        self.assertTrue(pro_passes_check_digit('175642396'))  # one Daylight gave a driver
        self.assertFalse(pro_passes_check_digit('175642397'))
        self.assertEqual(full_pro('1234', 'none'), '1234')

    def test_block_counts(self):
        block = self.block
        self.assertEqual((block.first_pro, block.last_pro, block.next_pro),
                         ('184176931', '184191922', '184177509'))
        self.assertEqual((block.quantity, block.remaining), (1500, 1443))
        self.assertEqual(block.name, '184176931 - 184191922')
        self.assertEqual(self.daylight.ltl_pro_remaining, 1443)
        fresh = self.env['selamta.ltl.pro.block'].create({
            'carrier_id': self.tforce.id, 'first_base': ' 500 ', 'last_base': '509'})
        self.assertEqual((fresh.next_base, fresh.quantity, fresh.remaining), ('500', 10, 10))

    def test_block_checks(self):
        Block = self.env['selamta.ltl.pro.block']
        with self.assertRaises(ValidationError):
            Block.create({'carrier_id': self.daylight.id, 'first_base': '18419000', 'last_base': '18419500'})
        with self.assertRaises(ValidationError):
            Block.create({'carrier_id': self.tforce.id, 'first_base': '20', 'last_base': '10'})
        with self.assertRaises(ValidationError):
            Block.create({'carrier_id': self.tforce.id, 'first_base': '10', 'last_base': '20', 'next_base': '30'})
        with self.assertRaises(ValidationError):
            Block.create({'carrier_id': self.tforce.id, 'first_base': '18-41', 'last_base': '20'})
        # Another carrier may use the same numbers; an archived block does not count.
        Block.create({'carrier_id': self.tforce.id, 'first_base': '18419000', 'last_base': '18419500'})
        self.block.active = False
        Block.create({'carrier_id': self.daylight.id, 'first_base': '18419000', 'last_base': '18419500'})

    # ------------------------------------------------------------------ handing out

    def test_booking_puts_next_pro_on_the_bol(self):
        first = self._book(self._shipment())
        self.assertEqual(first.state, 'booked')
        self.assertEqual(first.pro_number, '184177509')
        self.assertTrue(first.pro_preassigned)
        self.assertEqual(first.pickup_number, '5896084')
        # Our BOL is drawn after the PRO is set, so it is named after (and prints) the PRO.
        self.assertEqual(first.message_main_attachment_id.name, 'BOL 184177509.pdf')
        second = self._book(self._shipment())
        self.assertEqual(second.pro_number, '184177517')
        self.assertEqual(self.block.next_base, '18417752')
        self.assertEqual(self.block.remaining, 1441)

    def test_carrier_pro_and_typed_pro_are_kept(self):
        typed = self._book(self._shipment(pro='175642396'))
        self.assertEqual(typed.pro_number, '175642396')
        self.assertFalse(typed.pro_preassigned)
        given = self._book(self._shipment(), {'pro_number': '123456789'})
        self.assertEqual(given.pro_number, '123456789')
        self.assertEqual(self.block.next_base, '18417750')  # nothing taken

    def test_numbers_already_used_are_skipped(self):
        self._shipment(pro='184177509')  # typed by hand earlier
        self._shipment(pro='18417751-7')
        shipment = self._book(self._shipment())
        self.assertEqual(shipment.pro_number, '184177525')

    def test_carrier_without_block_gets_nothing(self):
        shipment = self._book(self._shipment(self.tforce))
        self.assertFalse(shipment.pro_number)
        self.assertFalse(shipment.can_assign_pro)
        with self.assertRaises(UserError):
            shipment.action_assign_pro()

    def test_confirm_booking_and_assign_button(self):
        manual = self._shipment()
        manual.action_confirm_booking()  # booked on MyDaylight
        self.assertEqual(manual.pro_number, '184177509')
        early = self._shipment()
        self.assertTrue(early.can_assign_pro)
        early.action_assign_pro()  # to print the BOL and labels before booking
        self.assertEqual(early.pro_number, '184177517')
        self.assertFalse(early.can_assign_pro)
        early.action_confirm_booking()
        self.assertEqual(early.pro_number, '184177517')  # kept, not a second one

    def test_oldest_block_first_then_warning_then_none(self):
        Block = self.env['selamta.ltl.pro.block']
        self.block.active = False
        small = Block.create({'carrier_id': self.daylight.id, 'first_base': '100', 'last_base': '101',
                              'warn_below': 2})
        newer = Block.create({'carrier_id': self.daylight.id, 'first_base': '200', 'last_base': '200',
                              'warn_below': 2})
        pros = [self._book(self._shipment()) for _i in range(3)]
        self.assertEqual([s.pro_number for s in pros], [full_pro('100'), full_pro('101'), full_pro('200')])
        def said(shipment, text):
            return any(text in body for body in shipment.message_ids.mapped('body'))

        self.assertFalse(said(pros[0], 'pre-assigned Daylight PROs left'))  # 2 left, warn below 2
        self.assertTrue(said(pros[1], 'Only 1 pre-assigned Daylight PROs left'))
        self.assertEqual((small.remaining, newer.remaining), (0, 0))
        last = self._book(self._shipment())
        self.assertFalse(last.pro_number)
        self.assertTrue(any('No pre-assigned Daylight PROs left' in body for body in last.message_ids.mapped('body')))
        with self.assertRaises(UserError):
            self._shipment().action_assign_pro()

    def test_changing_carrier_drops_the_pro(self):
        shipment = self._shipment()
        shipment.action_assign_pro()
        shipment.carrier_id = self.daylight  # same carrier: kept
        self.assertEqual(shipment.pro_number, '184177509')
        shipment.carrier_id = self.tforce
        self.assertFalse(shipment.pro_number)
        self.assertFalse(shipment.pro_preassigned)
        self.assertTrue(any('184177509 removed' in body for body in shipment.message_ids.mapped('body')))
        # A PRO typed by hand is the user's business and stays.
        typed = self._shipment(pro='999')
        typed.carrier_id = self.daylight
        self.assertEqual(typed.pro_number, '999')

    def test_typo_warning(self):
        shipment = self._shipment()
        shipment.pro_number = '184177508'
        self.assertIn('warning', shipment._onchange_pro_number_check_digit() or {})
        shipment.pro_number = '184177509'
        self.assertFalse(shipment._onchange_pro_number_check_digit())
        other = self._shipment(self.tforce, pro='12345')
        self.assertFalse(other._onchange_pro_number_check_digit())

    def test_tracking_can_replace_a_preassigned_pro(self):
        shipment = self._shipment()
        shipment.action_assign_pro()
        shipment.state = 'booked'
        Carrier = type(self.env['delivery.carrier'])

        def fake_track(carrier, shipments):
            return {s.id: {'pro_number': '175642396', 'replace_pro': True, 'state': 'in_transit',
                           'note': 'Picked up under 175642396'} for s in shipments}

        with patch.object(Carrier, 'fixed_ltl_track', fake_track, create=True):
            shipment.action_update_tracking()
        self.assertEqual(shipment.pro_number, '175642396')
        self.assertFalse(shipment.pro_preassigned)
        self.assertEqual(shipment.state, 'in_transit')
        self.assertTrue(any('Picked up under 175642396' in body for body in shipment.message_ids.mapped('body')))
