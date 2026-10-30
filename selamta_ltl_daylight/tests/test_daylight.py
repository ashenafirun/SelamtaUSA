# -*- coding: utf-8 -*-
"""Daylight connector tests with Daylight's answers simulated (no network)."""
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.selamta_ltl_daylight.models.delivery_carrier'
PDF = b'%PDF-1.4 daylight test'


class FakeResponse:
    def __init__(self, status, data=None, content=None):
        self.status_code = status
        self._data = data
        if content is None:
            content = json.dumps(data).encode() if data is not None else b''
        self.content = content
        self.text = content.decode('utf-8', 'replace')

    def json(self):
        if self._data is None:
            raise ValueError('no json')
        return self._data


def rate_answer(**overrides):
    answer = {
        'success': 'YES', 'errorInformation': {'errorMessage': ''},
        'quoteNumber': '12345678', 'quoteDate': '2026-10-30', 'pickupDate': '2026-11-02',
        'earliestDeliveryDate': '2026-11-05', 'totalWeight': 1800, 'origZip': '30035', 'destZip': '28202',
        'itemCharges': {'itemCharge': {'pcs': 2, 'pallets': 2, 'weight': 1800, 'actualClass': '85',
                                       'rateClass': '85', 'rate': 320.29, 'charge': 5765.22, 'discountPct': 94.0}},
        'accessorialCharges': {'accessorialCharge': {'reqAccessorial': 'Lift Gate Delivery', 'accRate': 55, 'accCharge': 55.0}},
        'totalCharges': {'grossCharge': 5765.22, 'fuelSurcharge': 180.22, 'totalAccessorial': 55.0,
                         'discountAmt': 5419.31, 'netCharge': 581.13},
    }
    answer.update(overrides)
    return answer


@tagged('post_install', '-at_install')
class TestDaylight(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        ga = env['res.country.state'].search([('code', '=', 'GA'), ('country_id', '=', us.id)])
        nc = env['res.country.state'].search([('code', '=', 'NC'), ('country_id', '=', us.id)])
        env.company.partner_id.write({
            'street': '5335 Dividend Dr', 'street2': 'Ste C', 'city': 'Decatur', 'zip': '30035',
            'state_id': ga.id, 'country_id': us.id, 'phone': '(404) 555-0100'})
        cls.consignee = env['res.partner'].create({
            'name': 'Sample Market', 'is_company': True, 'street': '100 Example Ave',
            'city': 'Charlotte', 'zip': '28202', 'state_id': nc.id, 'country_id': us.id,
            'phone': '704-555-0199'})
        cls.vendor = env['res.partner'].create({'name': 'Daylight Transport', 'is_company': True})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.liftgate = env.ref('selamta_ltl.accessorial_liftgate_delivery')
        cls.carrier = env['delivery.carrier'].create({
            'name': 'Daylight', 'product_id': product.id, 'delivery_type': 'daylight',
            'ltl_enabled': True, 'ltl_vendor_id': cls.vendor.id,
            'dylt_client_id': 'key', 'dylt_client_secret': 'secret',
            'dylt_account_number': '21365491', 'dylt_username': 'demo', 'dylt_password': 'pw',
            'dylt_contact_name': 'Dock',
        })
        cls.shipment = env['selamta.ltl.shipment'].create({
            'partner_id': cls.consignee.id,
            'carrier_id': cls.carrier.id,
            'ship_date': fields.Date.context_today(env['selamta.ltl.shipment']) + timedelta(days=1),
            'accessorial_ids': [(6, 0, [cls.liftgate.id])],
            'unit_ids': [(0, 0, {'quantity': 2, 'unit_type': 'pallet', 'description': 'Teff flour',
                                 'length': 48, 'width': 40, 'height': 60, 'weight': 1800,
                                 'nmfc_item': '73260'})],
        })
        if cls.shipment.ship_date.weekday() >= 5:
            cls.shipment.ship_date += timedelta(days=7 - cls.shipment.ship_date.weekday())

    def setUp(self):
        super().setUp()
        self.calls = []
        self.answers = {}

        def fake_request(method, url, **kwargs):
            self.calls.append(dict(kwargs, method=method, url=url))
            if url.endswith('/oauth/client_credential/accesstoken'):
                return FakeResponse(200, {'access_token': 'tok-%s' % len(self._calls_to('accesstoken')),
                                          'expires_in': '3599', 'token_type': 'BearerToken'})
            for key, answer in self.answers.items():
                if url.endswith(key):
                    return answer() if callable(answer) else answer
            return FakeResponse(404, {'message': 'not found'})

        patcher = patch(MODULE + '.requests.request', side_effect=fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calls_to(self, part):
        return [c for c in self.calls if part in c['url']]

    def test_rate_request_and_answer(self):
        self.answers['/rateQuote'] = FakeResponse(200, rate_answer())
        rates = self.carrier.ltl_rate(self.shipment)
        token_call = self._calls_to('accesstoken')[0]
        self.assertEqual(token_call['auth'], ('key', 'secret'))
        self.assertEqual(token_call['params'], {'grant_type': 'client_credentials'})
        call = self._calls_to('/rateQuote')[0]
        self.assertEqual(call['url'], 'https://api.dylt.com/rateQuote')
        self.assertEqual(call['headers']['Authorization'], 'Bearer tok-1')
        body = call['json']['dyltRateQuoteReq']
        self.assertEqual((body['accountNumber'], body['userName'], body['password']), ('21365491', 'demo', 'pw'))
        self.assertEqual(body['billTerms'], 'PP')
        self.assertEqual(body['shipperInfo']['customerNumber'], '21365491')
        self.assertEqual(body['shipperInfo']['customerAddress']['zip'], '30035')
        self.assertEqual(body['shipperInfo']['customerAddress']['aptAddress'], 'Ste C')
        self.assertEqual(body['consigneeInfo']['customerAddress']['state'], 'NC')
        self.assertEqual(body['pickupDate'], str(self.shipment.ship_date))
        item = body['items']['item'][0]
        self.assertEqual(item, {'description': 'Teff flour', 'pcs': 2, 'pallets': 2, 'weight': 1800,
                                'actualClass': '85', 'nmfcNumber': '73260'})
        self.assertEqual(body['accessorials'], {'accessorial': [{'accName': 'D', 'accId': 'Lift Gate Delivery'}]})
        rate = rates[0]
        self.assertEqual(rate['total'], 581.13)
        self.assertEqual(rate['quote_number'], '12345678')
        self.assertEqual(rate['transit_days'], 3)  # Mon 11/02 -> Thu 11/05
        self.assertEqual(rate['service'], 'Daylight LTL')
        names = [c['name'] for c in rate['charges']]
        self.assertEqual(names, ['Linehaul before discount', 'Discount (94%)', 'Liftgate at delivery', 'Fuel surcharge'])
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 581.13)

    def test_service_without_daylight_code_is_flagged(self):
        self.liftgate.dylt_code = False
        self.answers['/rateQuote'] = FakeResponse(200, rate_answer(accessorialCharges={}))
        rate = self.carrier.ltl_rate(self.shipment)[0]
        self.assertNotIn('accessorials', self._calls_to('/rateQuote')[0]['json']['dyltRateQuoteReq'])
        self.assertIn('NOT INCLUDED: Liftgate at delivery', rate['service'])
        self.carrier.dylt_book_pickups = True
        with self.assertRaisesRegex(UserError, 'Daylight code of Liftgate at delivery'):
            self.carrier.ltl_book(self.shipment, rate)
        self.assertFalse(self._calls_to('/pickup'))

    def test_rate_errors_and_far_pickup_date(self):
        self.answers['/rateQuote'] = FakeResponse(200, rate_answer(
            success='NO', errorInformation={'errorMessage': 'Invalid consignee zip'}))
        with self.assertRaisesRegex(UserError, 'Invalid consignee zip'):
            self.carrier.ltl_rate(self.shipment)
        self.shipment.ship_date += timedelta(days=14)
        self.answers['/rateQuote'] = FakeResponse(200, rate_answer())
        self.carrier.ltl_rate(self.shipment)
        self.assertNotIn('pickupDate', self._calls_to('/rateQuote')[-1]['json']['dyltRateQuoteReq'])

    def test_token_reused_and_refreshed(self):
        self.answers['/rateQuote'] = FakeResponse(200, rate_answer())
        self.carrier.ltl_rate(self.shipment)
        self.carrier.ltl_rate(self.shipment)
        self.assertEqual(len(self._calls_to('accesstoken')), 1)
        answers = [FakeResponse(401, {'fault': {'faultstring': 'Invalid Access Token'}}),
                   FakeResponse(200, rate_answer())]
        self.answers['/rateQuote'] = lambda: answers.pop(0)
        self.carrier.ltl_rate(self.shipment)
        self.assertEqual(len(self._calls_to('accesstoken')), 2)

    def test_booking_is_off_by_default(self):
        self.answers['/rateQuote'] = FakeResponse(200, rate_answer())
        self.assertFalse(self.carrier.ltl_can('book'))
        action = self.shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        line = wizard.line_ids.filtered(lambda l: l.carrier_id == self.carrier)
        line.action_choose()
        self.assertFalse(self._calls_to('/pickup'))
        self.assertEqual(self.shipment.quoted_amount, 581.13)
        self.assertEqual(self.shipment.state, 'draft')  # staff book on MyDaylight and type the PRO

    def test_book_pickup_through_rate_shop(self):
        self.carrier.dylt_book_pickups = True
        self.shipment.write({'pickup_ready_time': 13.5, 'pickup_close_time': 17.0,
                             'pickup_instructions': 'Dock door 2'})
        self.answers['/rateQuote'] = FakeResponse(200, rate_answer())
        self.answers['/pickup'] = FakeResponse(200, {'dyltPickupResp': {
            'date': '2026-10-30T10:00:00', 'shipmentID': self.shipment.name,
            'reservationStatus': 'A', 'bookingNumber': 4796689, 'reason': ''}})
        self.answers['/image/booking/4796689/bol'] = FakeResponse(200, content=PDF)
        action = self.shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        wizard.line_ids.filtered(lambda l: l.carrier_id == self.carrier).action_choose()
        body = self._calls_to('/pickup')[0]['json']['dyltPickupReqs']['dyltPickupReq']
        self.assertEqual(body['shipmentID'], self.shipment.name)
        self.assertEqual(body['shipperName'], self.env.company.partner_id.name)
        self.assertEqual(body['shipperAddress2'], 'Ste C')
        self.assertEqual(body['shipperContactName'], 'Dock')
        self.assertEqual(body['shipperContactNumber'], '4045550100')
        self.assertEqual(body['consigneeContactName'], 'Receiving')
        self.assertEqual(body['consigneeContactNumber'], '7045550199')
        self.assertEqual((body['pickupStartDate'], body['pickupEndDate']), (str(self.shipment.ship_date),) * 2)
        self.assertEqual((body['pickupStartTime'], body['pickupEndTime']), ('13:30:00', '17:00:00'))
        self.assertEqual(body['items']['item'][0]['pallets'], 2)
        self.assertEqual(body['notes']['note'], 'LIFTGATE AT DELIVERY, NO INSIDE DELIVERY, PICKUP: Dock door 2')
        self.assertEqual(body['accessorials'], {'accessorial': [{'accName': 'D', 'accId': 'Lift Gate Delivery'}]})
        self.assertEqual(body['shipReferences'], {'shipReference': [
            {'referenceType': 'B', 'referenceNumber': self.shipment.name},
            {'referenceType': 'Q', 'referenceNumber': '12345678'}]})
        image_call = self._calls_to('/image/booking/4796689/bol')[0]
        self.assertEqual(image_call['params'], {'userName': 'demo', 'password': 'pw'})
        shipment = self.shipment
        self.assertEqual(shipment.state, 'booked')
        self.assertEqual(shipment.pickup_number, '4796689')
        self.assertFalse(shipment.pro_number)  # Daylight assigns it at pickup
        self.assertEqual(shipment.dylt_reservation, 'Accepted')
        names = self.env['ir.attachment'].search(
            [('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name')
        self.assertIn('Daylight BOL (carrier copy) 4796689.pdf', names)
        self.assertEqual(shipment.message_main_attachment_id.name, 'BOL %s.pdf' % shipment.name)  # ours to print

    def test_declined_pickup(self):
        self.carrier.dylt_book_pickups = True
        self.answers['/pickup'] = FakeResponse(200, {'dyltPickupResp': {
            'reservationStatus': 'D', 'bookingNumber': 0, 'reason': 'No service to destination'}})
        with self.assertRaisesRegex(UserError, 'No service to destination'):
            self.carrier.ltl_book(self.shipment, {'total': 1})

    def test_track_by_booking_then_pro_and_documents(self):
        self.shipment.write({'pickup_number': '4796689', 'state': 'booked'})
        self.answers['/externalTrace/booking/4796689'] = FakeResponse(200, {
            'billNumber': 184177368, 'currentStatus': 'In Transit', 'actualDeliveryDate': None,
            'expectedDeliveryDate': '2026-11-05T00:00:00', 'statHistArr': []})
        self.shipment.action_update_tracking()
        self.assertEqual(self.shipment.pro_number, '184177368')
        self.assertEqual(self.shipment.state, 'in_transit')
        self.assertEqual(self.shipment.tracking_status, 'In Transit, expected 11/05/2026')

        self.answers['/externalTrace/184177368'] = FakeResponse(200, {
            'billNumber': 184177368, 'currentStatus': 'Delivered',
            'actualDeliveryDate': '2026-11-05T10:30:00'})
        self.answers['/image/184177368/dr/pdf'] = FakeResponse(200, content=PDF)
        self.answers['/image/184177368/wic/pdf'] = FakeResponse(404, {'status': 'NOT FOUND', 'message': 'No image'})
        self.shipment.action_update_tracking()
        self.assertEqual(self.shipment.state, 'delivered')
        self.assertEqual(str(self.shipment.delivered_date), '2026-11-05')
        names = self.env['ir.attachment'].search(
            [('res_model', '=', self.shipment._name), ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt 184177368.pdf', names)
        self.assertNotIn('Weight and inspection 184177368.pdf', names)
        self.shipment.action_fetch_documents()  # the delivery receipt is not attached twice
        self.assertEqual(self.env['ir.attachment'].search_count(
            [('res_model', '=', self.shipment._name), ('res_id', '=', self.shipment.id),
             ('name', '=', 'Delivery receipt 184177368.pdf')]), 1)

    def test_missing_settings_and_hooks(self):
        self.carrier.dylt_password = False
        with self.assertRaisesRegex(UserError, 'MyDaylight username and password'):
            self.carrier.ltl_rate(self.shipment)
        self.assertFalse(self.carrier.daylight_rate_shipment(None)['success'])
        picking = self.env['stock.picking'].new({'carrier_tracking_ref': '184177368'})
        self.assertEqual(self.carrier.daylight_get_tracking_link(picking),
                         'https://mydaylight.dylt.com/external/shipment?probill=184177368')

    def test_test_connection_button(self):
        self.answers['/rateQuote'] = FakeResponse(200, rate_answer())
        action = self.carrier.action_dylt_test_connection()
        self.assertIn('21365491', action['params']['message'])
        self.assertIn('581.13', action['params']['message'])

    def test_default_daylight_codes(self):
        Accessorial = self.env['selamta.ltl.accessorial']
        self.assertEqual(self.liftgate.dylt_code, 'Lift Gate Delivery')  # set on install
        self.assertEqual(self.env.ref('selamta_ltl.accessorial_liftgate_pickup').dylt_code, 'Lift Gate Pickup')
        self.liftgate.dylt_code = 'My code'
        Accessorial._dylt_set_default_codes()
        self.assertEqual(self.liftgate.dylt_code, 'My code')  # codes already set are kept
        # "-": Daylight has no such charge; left out of requests without blocking booking.
        notify = self.env.ref('selamta_ltl.accessorial_notify')
        self.assertEqual(notify.dylt_code, '-')
        self.liftgate.dylt_code = 'Lift Gate Delivery'
        self.shipment.accessorial_ids = [(4, notify.id)]
        accessorials, missing = self.carrier._dylt_accessorials(self.shipment)
        self.assertEqual(accessorials, [{'accName': 'D', 'accId': 'Lift Gate Delivery'}])
        self.assertFalse(missing)
