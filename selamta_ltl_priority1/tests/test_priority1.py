# -*- coding: utf-8 -*-
"""Priority1 connector tests with Priority1's answers simulated (no network)."""
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.selamta_ltl_priority1.models.delivery_carrier'
PDF = b'%PDF-1.4 priority1 test'


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


def quote(qid, carrier, scac, total, days=3, charges=None):
    return {
        'id': qid, 'carrierName': carrier, 'carrierCode': scac, 'carrierQuoteNumber': 'CQ%s' % qid,
        'serviceLevel': 'Standard', 'serviceLevelDescription': 'Standard', 'transitDays': days,
        'deliveryDate': '2026-11-05T00:00:00', 'expirationDate': '2026-11-06T00:00:00',
        'rateQuoteDetail': {'total': total, 'charges': charges if charges is not None else [
            {'code': '400', 'description': 'Freight Charge', 'amount': total - 80},
            {'code': 'LGDEL', 'description': 'Lift Gate Delivery', 'amount': 50},
            {'code': 'FSC', 'description': 'Fuel Surcharge', 'amount': 30},
        ]},
    }


RATE_ANSWER = {
    'id': 900, 'rateQuotes': [quote(21110, 'XPO Logistics', 'CNWY', 455.0),
                              quote(21108, 'Saia', 'SAIA', 402.5, days=2),
                              quote(21109, 'Estes', 'EXLA', 0)],
    'invalidRateQuotes': [{'carrierName': 'ABF', 'message': 'No service'}],
}

DISPATCH_ANSWER = {
    'id': 5495,
    'shipmentIdentifiers': [
        {'type': 'BILL_OF_LADING', 'value': '60100000123', 'primaryForType': True},
        {'type': 'CUSTOMER_REFERENCE', 'value': 'SEL', 'primaryForType': True},
        {'type': 'PICKUP', 'value': 'PU778899', 'primaryForType': True},
    ],
    'capacityProviderBolUrl': 'https://files.priority1.com/bol/60100000123.pdf',
    'estimatedDeliveryDate': '2026-11-04T00:00:00',
    'infoMessages': [{'severity': 'Info', 'text': 'Pickup requested', 'source': 'Saia', 'id': 1}],
    'totalCost': 402.5,
}


@tagged('post_install', '-at_install')
class TestPriority1(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        ga = env['res.country.state'].search([('code', '=', 'GA'), ('country_id', '=', us.id)])
        nc = env['res.country.state'].search([('code', '=', 'NC'), ('country_id', '=', us.id)])
        env.company.partner_id.write({
            'street': '5335 Dividend Dr', 'street2': 'Ste C', 'city': 'Decatur', 'zip': '30035',
            'state_id': ga.id, 'country_id': us.id, 'phone': '(404) 555-0100', 'email': 'ship@example.com'})
        cls.consignee = env['res.partner'].create({
            'name': 'Sample Market', 'is_company': True, 'street': '100 Example Ave',
            'city': 'Charlotte', 'zip': '28202', 'state_id': nc.id, 'country_id': us.id,
            'phone': '704-555-0199'})
        cls.vendor = env['res.partner'].create({'name': 'Priority1', 'is_company': True})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.carrier = env['delivery.carrier'].create({
            'name': 'Priority1', 'product_id': product.id, 'delivery_type': 'priority1',
            'ltl_enabled': True, 'ltl_vendor_id': cls.vendor.id, 'ltl_match_on': 'manual',
            'ltl_scac': 'POIP', 'p1_api_key': 'test-key', 'p1_contact_name': 'Dock',
        })
        cls.shipment = env['selamta.ltl.shipment'].create({
            'partner_id': cls.consignee.id,
            'carrier_id': cls.carrier.id,
            'ship_date': fields.Date.context_today(env['selamta.ltl.shipment']) + timedelta(days=1),
            'accessorial_ids': [(6, 0, [env.ref('selamta_ltl.accessorial_liftgate_delivery').id])],
            'unit_ids': [(0, 0, {'quantity': 2, 'unit_type': 'pallet', 'description': 'Teff flour',
                                 'length': 48, 'width': 40, 'height': 60, 'weight': 1800,
                                 'nmfc_item': '73260'})],
        })

    def setUp(self):
        super().setUp()
        self.calls = []
        self.answers = {}

        def fake_request(method, url, **kwargs):
            self.calls.append(dict(kwargs, method=method, url=url))
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
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(200, RATE_ANSWER)
        rates = self.carrier.ltl_rate(self.shipment)
        call = self._calls_to('/quotes/rates')[0]
        self.assertEqual(call['url'], 'https://api.priority1.com/v2/ltl/quotes/rates')
        self.assertEqual(call['headers']['X-API-KEY'], 'test-key')
        body = call['json']
        self.assertEqual((body['originZipCode'], body['originStateAbbreviation'], body['originCity']),
                         ('30035', 'GA', 'Decatur'))
        self.assertEqual(body['destinationZipCode'], '28202')
        self.assertEqual(body['pickupDate'], '%sT00:00:00' % self.shipment.ship_date)
        self.assertEqual(body['accessorialServices'], [{'code': 'LGDEL'}])
        item = body['items'][0]
        self.assertEqual((item['freightClass'], item['packagingType'], item['units'], item['totalWeight']),
                         ('85', 'Pallet', 2, 1800))
        self.assertEqual((item['length'], item['width'], item['height']), (48, 40, 60))
        self.assertEqual(item['nmfcItemCode'], '73260')
        self.assertEqual([r['p1_carrier_name'] for r in rates], ['Saia', 'XPO Logistics'])  # cheapest first, no $0
        saia = rates[0]
        self.assertEqual(saia['service'], 'Saia via Priority1')
        self.assertEqual((saia['total'], saia['transit_days'], saia['p1_quote_id']), (402.5, 2, 21108))
        self.assertEqual(saia['quote_number'], 'CQ21108')
        self.assertEqual(saia['expires'], '2026-11-06')
        self.assertEqual(saia['p1_carrier_scac'], 'SAIA')
        self.assertAlmostEqual(sum(c['amount'] for c in saia['charges']), 402.5)

    def test_quote_limit_and_errors(self):
        self.carrier.p1_max_quotes = 1
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(200, RATE_ANSWER)
        self.assertEqual(len(self.carrier.ltl_rate(self.shipment)), 1)
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(200, {'rateQuotes': [], 'invalidRateQuotes': [
            {'carrierName': 'Saia', 'message': 'Destination not serviced'}]})
        with self.assertRaisesRegex(UserError, 'Destination not serviced'):
            self.carrier.ltl_rate(self.shipment)
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(401, {'message': 'Unauthorized'})
        with self.assertRaisesRegex(UserError, 'refused the API key'):
            self.carrier.ltl_rate(self.shipment)
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(400, {
            'title': 'One or more validation errors occurred.',
            'errors': {'OriginZipCode': ['The OriginZipCode field is required.']}})
        with self.assertRaisesRegex(UserError, 'OriginZipCode field is required'):
            self.carrier.ltl_rate(self.shipment)

    def test_dispatch_is_off_by_default(self):
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(200, RATE_ANSWER)
        self.assertFalse(self.carrier.ltl_can('book'))
        action = self.shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        lines = wizard.line_ids.filtered(lambda l: l.carrier_id == self.carrier)
        self.assertEqual(len(lines), 2)  # one line per Priority1 carrier
        lines.sorted('total')[0].action_choose()
        self.assertFalse(self._calls_to('/dispatch'))
        self.assertEqual((self.shipment.state, self.shipment.quoted_amount), ('draft', 402.5))

    def test_dispatch_through_rate_shop(self):
        self.carrier.p1_book_shipments = True
        self.shipment.write({'pickup_ready_time': 13.5, 'pickup_close_time': 17.0,
                             'pickup_instructions': 'Dock door 2'})
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(200, RATE_ANSWER)
        self.answers['/v2/ltl/shipments/dispatch'] = FakeResponse(200, DISPATCH_ANSWER)
        self.answers['/bol/60100000123.pdf'] = FakeResponse(200, content=PDF)
        action = self.shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        wizard.line_ids.filtered(lambda l: l.carrier_id == self.carrier).sorted('total')[0].action_choose()
        body = self._calls_to('/dispatch')[0]['json']
        self.assertEqual(body['quoteId'], 21108)
        self.assertEqual(body['pickupWindow'], {'date': self.shipment.ship_date.strftime('%m/%d/%Y'),
                                                'startTime': '13:30', 'endTime': '17:00'})
        earliest = self.carrier._p1_add_business_days(self.shipment.ship_date, 2)
        expected = max(earliest, fields.Date.to_date('2026-11-05'))
        self.assertEqual(body['deliveryWindow']['date'], expected.strftime('%m/%d/%Y'))  # never before pickup + transit
        origin = body['originLocation']
        self.assertEqual(origin['address']['addressLine2'], 'Ste C')
        self.assertEqual(origin['contact'], {'companyName': self.env.company.partner_id.name,
                                             'contactName': 'Dock', 'phoneNumber': '4045550100',
                                             'email': 'ship@example.com'})
        self.assertEqual(body['destinationLocation']['contact']['contactName'], 'Receiving')
        self.assertEqual(body['destinationLocation']['contact']['phoneNumber'], '7045550199')
        self.assertEqual(body['shipmentIdentifiers'][0],
                         {'type': 'CUSTOMER_REFERENCE', 'value': self.shipment.name, 'primaryForType': True})
        self.assertEqual(body['deliveryNote'], 'LIFTGATE AT DELIVERY, NO INSIDE DELIVERY')
        self.assertEqual(body['pickupNote'], 'Dock door 2')
        shipment = self.shipment
        self.assertEqual(shipment.state, 'booked')
        self.assertEqual(shipment.bol_number, '60100000123')
        self.assertEqual(shipment.pickup_number, 'PU778899')
        self.assertFalse(shipment.pro_number)
        self.assertEqual((shipment.p1_carrier_name, shipment.p1_carrier_scac, shipment.p1_shipment_id),
                         ('Saia', 'SAIA', '5495'))
        self.assertEqual(shipment.print_carrier_name, 'Saia (via Priority1)')  # on our BOL and labels
        self.assertEqual(shipment.print_carrier_scac, 'SAIA')
        names = self.env['ir.attachment'].search(
            [('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name')
        self.assertIn('Saia BOL (carrier copy) 60100000123.pdf', names)
        self.assertIn('BOL 60100000123.pdf', names)  # ours to print
        messages = ' '.join(shipment.message_ids.mapped('body'))
        self.assertIn('Pickup requested', messages)
        self.assertNotIn('&lt;br', messages)

    def test_track_and_documents(self):
        self.shipment.write({'bol_number': '60100000123', 'state': 'booked'})
        self.answers['/v2/ltl/shipments/status'] = FakeResponse(200, {'shipments': [{
            'id': 5495, 'carrierCode': 'SAIA', 'status': 'Delivered',
            'actualPickupDate': '2026-11-02T14:00:00', 'actualDeliveryDate': '2026-11-04T10:30:00',
            'shipmentIdentifiers': [{'type': 'PRO', 'value': '10123456789', 'primaryForType': True}],
            'trackingStatuses': [
                {'timeStamp': '2026-11-02T14:00:00', 'city': 'Atlanta', 'state': 'GA', 'status': 'In Transit'},
                {'timeStamp': '2026-11-04T10:30:00', 'city': 'Charlotte', 'state': 'NC', 'status': 'Delivered',
                 'statusReason': 'Delivered clear.'}],
        }]})
        self.answers['/v2/ltl/shipments/images'] = FakeResponse(200, {
            'imageUrl': 'https://files.priority1.com/img/dr.pdf', 'shipmentImageTypeId': 'DeliveryReceipt'})
        self.answers['/img/dr.pdf'] = FakeResponse(200, content=PDF)
        self.shipment.action_update_tracking()
        status_call = self._calls_to('/shipments/status')[0]['json']
        self.assertEqual(status_call, {'identifierType': 'BILL_OF_LADING', 'identifierValue': '60100000123'})
        shipment = self.shipment
        self.assertEqual(shipment.pro_number, '10123456789')
        self.assertEqual(shipment.state, 'delivered')
        self.assertEqual(str(shipment.delivered_date), '2026-11-04')
        self.assertEqual(shipment.tracking_status, 'Delivered - Delivered clear. - Charlotte, NC')
        names = self.env['ir.attachment'].search(
            [('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt 10123456789.pdf', names)

    def test_missing_key_and_hooks(self):
        self.carrier.p1_api_key = False
        with self.assertRaisesRegex(UserError, 'API key'):
            self.carrier.ltl_rate(self.shipment)
        self.assertFalse(self.calls)
        self.assertFalse(self.carrier.priority1_rate_shipment(None)['success'])

    def test_test_key_button(self):
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(200, RATE_ANSWER)
        action = self.carrier.action_p1_test_connection()
        self.assertIn('2 quotes', action['params']['message'])
        self.assertIn('Saia via Priority1', action['params']['message'])

    def test_service_label_and_delivery_window_after_pickup(self):
        answer = dict(RATE_ANSWER, rateQuotes=[dict(quote(1, 'Roadrunner', 'RDFS', 400.0, days=4),
                                                    serviceLevelDescription='Standard Rate',
                                                    deliveryDate='2020-01-01T00:00:00')])
        self.answers['/v2/ltl/quotes/rates'] = FakeResponse(200, answer)
        rate = self.carrier.ltl_rate(self.shipment)[0]
        self.assertEqual(rate['service'], 'Roadrunner via Priority1')  # "Standard Rate" not repeated
        request = self.carrier._p1_dispatch_request(self.shipment, rate)
        expected = self.carrier._p1_add_business_days(self.shipment.ship_date, 4)
        self.assertEqual(request['deliveryWindow']['date'], expected.strftime('%m/%d/%Y'))

    def test_cancel_with_priority1(self):
        self.shipment.write({'state': 'booked', 'bol_number': '60116495862', 'p1_shipment_id': '15260611'})
        self.answers['/v2/ltl/shipments/cancel'] = FakeResponse(200, {'id': 15260611, 'success': True})
        self.assertTrue(self.carrier.ltl_can('cancel'))  # even with dispatch off
        action = self.shipment.action_cancel()
        self.assertEqual(self._calls_to('/shipments/cancel')[0]['json'], {'id': 15260611})
        self.assertEqual(self.shipment.state, 'cancel')
        bodies = ' '.join(self.shipment.message_ids.mapped('body'))
        self.assertIn('Pickup cancelled with Priority1', bodies)
        self.assertIn('call or email Priority1', bodies)
        # The API cancel does not reach the trucking carrier: staff get a sticky reminder.
        self.assertEqual(action['tag'], 'display_notification')
        self.assertTrue(action['params']['sticky'])
        self.assertIn('call or email Priority1', action['params']['message'])
        self.assertIn('60116495862', action['params']['message'])

    def test_cancel_refused_keeps_shipment_booked(self):
        self.shipment.write({'state': 'booked', 'p1_shipment_id': '15260611'})
        self.answers['/v2/ltl/shipments/cancel'] = FakeResponse(403, {'message': 'Forbidden'})
        with self.assertRaises(RedirectWarning) as caught:
            self.shipment.action_cancel()
        message, action_id, button, context = caught.exception.args
        self.assertIn('does not allow our API key', message)
        self.assertIn('still booked', message)
        self.assertEqual(button, 'Cancel in Odoo only')
        self.assertEqual(context['active_ids'], self.shipment.ids)
        self.assertEqual(self.shipment.state, 'booked')
        # After cancelling by phone: the offered action cancels in Odoo only, without calling Priority1.
        calls = len(self.calls)
        self.env['ir.actions.server'].browse(action_id).with_context(
            active_model=self.shipment._name, active_ids=self.shipment.ids, active_id=self.shipment.id).run()
        self.assertEqual(self.shipment.state, 'cancel')
        self.assertEqual(len(self.calls), calls)
        self.assertIn('cancelled with Priority1 outside Odoo', ' '.join(self.shipment.message_ids.mapped('body')))
