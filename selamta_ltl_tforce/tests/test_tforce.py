# -*- coding: utf-8 -*-
"""TForce connector tests with TForce's answers simulated (no network)."""
import base64
import json
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.selamta_ltl_tforce.models.delivery_carrier'
PDF = b'%PDF-1.4 tforce test'


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.content = json.dumps(data).encode()
        self.text = self.content.decode()

    def json(self):
        return self._data


RATE_ANSWER = {
    'summary': {'responseStatus': {'code': 'OK', 'message': 'success'}, 'quoteNumber': 'Q123456'},
    'detail': [{
        'service': {'code': '308', 'description': 'TForce Freight LTL'},
        'rate': [
            {'code': 'DSCNT', 'description': 'Discount', 'value': '900.00', 'unit': 'USD'},
            {'code': 'DSCNT_RATE', 'description': 'Discount Rate', 'value': '75.00', 'unit': '%'},
            {'code': 'LIFD', 'description': 'LIFT_GATE_DL', 'value': '60.40', 'unit': 'USD'},
            {'code': 'FUEL_SUR', 'description': 'Fuel Surcharge Fee', 'value': '52.10', 'unit': 'USD'},
            {'code': 'LND_GROSS', 'description': 'LND_GROSS', 'value': '1200.00', 'unit': 'USD'},
            {'code': 'AFTR_DSCNT', 'description': 'AFTR_DSCNT', 'value': '300.00', 'unit': 'USD'},
        ],
        'shipmentCharges': {'total': {'value': '412.50', 'currency': 'USD'}},
        'timeInTransit': {'value': '2', 'unit': 'DAY'},
    }],
}

BOL_ANSWER = {
    'summary': {'code': 'OK', 'message': 'success'},
    'detail': {
        'bolId': 8418552, 'pro': 62108025, 'originServiceCenter': 'ATL',
        'rateDetail': [{'shipmentCharges': {'total': {'value': '412.50', 'currency': 'USD'}},
                        'alerts': [{'code': '853', 'message': 'FBR853: DESTINATION IS A RURAL POINT'}]}],
        'pickup': {'responseStatus': {'code': '1', 'description': 'Success'},
                   'transactionReference': {'confirmationNumber': 'WBU3261541'}},
        'documents': {'image': [{'status': 'OK', 'type': '20', 'format': 'PDF',
                                 'data': base64.b64encode(PDF).decode()}]},
    },
}


@tagged('post_install', '-at_install')
class TestTForce(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        ga = env['res.country.state'].search([('code', '=', 'GA'), ('country_id', '=', us.id)])
        nc = env['res.country.state'].search([('code', '=', 'NC'), ('country_id', '=', us.id)])
        env.company.partner_id.write({
            'street': '5335 Dividend Dr #C', 'city': 'Decatur', 'zip': '30035',
            'state_id': ga.id, 'country_id': us.id, 'phone': '(404) 555-0100',
            'email': 'shipping@example.com'})
        cls.consignee = env['res.partner'].create({
            'name': 'Sample Market', 'is_company': True, 'street': '100 Example Ave',
            'city': 'Charlotte', 'zip': '28202', 'state_id': nc.id, 'country_id': us.id,
            'phone': '704-555-0199'})
        cls.vendor = env['res.partner'].create({'name': 'TForce Freight', 'is_company': True})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.carrier = env['delivery.carrier'].create({
            'name': 'TForce Freight', 'product_id': product.id, 'delivery_type': 'tforce',
            'ltl_enabled': True, 'ltl_vendor_id': cls.vendor.id,
            'tforce_client_id': 'client-id', 'tforce_client_secret': 'client-secret',
            'tforce_contact_name': 'Dock', 'tforce_contact_email': 'dock@example.com',
            'tforce_contact_phone': '404-555-0100',
        })
        cls.shipment = env['selamta.ltl.shipment'].create({
            'partner_id': cls.consignee.id,
            'carrier_id': cls.carrier.id,
            'accessorial_ids': [(6, 0, [env.ref('selamta_ltl.accessorial_liftgate_delivery').id])],
            'unit_ids': [(0, 0, {'quantity': 2, 'unit_type': 'pallet', 'description': 'Teff flour',
                                 'length': 48, 'width': 40, 'height': 60, 'weight': 1800,
                                 'nmfc_item': '73260'})],
        })

    def setUp(self):
        super().setUp()
        self.calls = []
        self.token_calls = []
        self.answers = {}

        def fake_post(url, data=None, timeout=None):
            self.token_calls.append(data)
            return FakeResponse(200, {'access_token': 'tok-%s' % len(self.token_calls), 'expires_in': 3599})

        def fake_request(method, url, params=None, json=None, headers=None, timeout=None):
            self.calls.append({'method': method, 'url': url, 'params': params, 'json': json, 'headers': headers})
            for path, answer in self.answers.items():
                if url.endswith(path):
                    return answer() if callable(answer) else answer
            return FakeResponse(404, {'message': 'not found'})

        patcher_post = patch(MODULE + '.requests.post', side_effect=fake_post)
        patcher_req = patch(MODULE + '.requests.request', side_effect=fake_request)
        patcher_post.start()
        patcher_req.start()
        self.addCleanup(patcher_post.stop)
        self.addCleanup(patcher_req.stop)

    def test_rate_request_and_answer(self):
        self.answers['/rating/getRate'] = FakeResponse(200, RATE_ANSWER)
        rates = self.carrier.ltl_rate(self.shipment)
        call = self.calls[0]
        self.assertEqual(call['params'], {'api-version': 'cie-v1'})  # test environment by default
        self.assertEqual(call['headers']['Authorization'], 'Bearer tok-1')
        body = call['json']
        self.assertEqual(body['payment']['billingCode'], '10')
        self.assertEqual(body['shipTo']['address']['postalCode'], '28202')
        self.assertEqual(body['serviceOptions'], {'delivery': ['LIFD']})
        commodity = body['commodities'][0]
        self.assertEqual(commodity['class'], '85')  # from the pallets' density (13.5 lb/ft3)
        self.assertEqual(commodity['pieces'], 2)
        self.assertEqual(commodity['packagingType'], 'PLT')
        self.assertEqual(commodity['nmfc'], {'prime': '73260'})
        self.assertEqual(commodity['dimensions'], {'length': 48, 'width': 40, 'height': 60, 'unit': 'IN'})
        self.assertEqual(len(rates), 1)
        self.assertEqual(rates[0]['total'], 412.5)
        self.assertEqual(rates[0]['transit_days'], 2)
        self.assertEqual(rates[0]['quote_number'], 'Q123456')
        charges = rates[0]['charges']
        self.assertEqual([c['code'] for c in charges], ['DSCNT', 'LIFD', 'FUEL_SUR', 'LND_GROSS'])
        self.assertEqual(charges[0]['amount'], -900.0)  # discount shown negative
        self.assertAlmostEqual(sum(c['amount'] for c in charges), 412.5)  # lines add up to the total
        self.assertEqual(charges[1]['name'], 'Liftgate at delivery')

    def test_token_reused_and_refreshed_after_401(self):
        self.answers['/rating/getRate'] = FakeResponse(200, RATE_ANSWER)
        self.carrier.ltl_rate(self.shipment)
        self.carrier.ltl_rate(self.shipment)
        self.assertEqual(len(self.token_calls), 1)
        self.assertEqual(self.token_calls[0]['grant_type'], 'client_credentials')
        answers = [FakeResponse(401, {'message': 'expired'}), FakeResponse(200, RATE_ANSWER)]
        self.answers['/rating/getRate'] = lambda: answers.pop(0)
        self.carrier.ltl_rate(self.shipment)
        self.assertEqual(len(self.token_calls), 2)

    def test_book_through_rate_shop(self):
        self.answers['/rating/getRate'] = FakeResponse(200, RATE_ANSWER)
        self.answers['/shipping/bol/create'] = FakeResponse(200, BOL_ANSWER)
        action = self.shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        line = wizard.line_ids.filtered(lambda l: l.carrier_id == self.carrier)
        self.assertEqual(line.total, 412.5)
        line.action_choose()
        bol = [c for c in self.calls if c['url'].endswith('/shipping/bol/create')][0]['json']
        self.assertEqual(bol['handlingUnitOne'], {'quantity': 2, 'typeCode': 'PLT'})
        self.assertEqual(bol['references'][0], {'number': self.shipment.name, 'type': 'BL'})
        self.assertEqual(bol['instructions']['delivery'], 'LIFTGATE AT DELIVERY, NO INSIDE DELIVERY')
        self.assertEqual(bol['pickupRequest']['requester']['email'], 'dock@example.com')
        self.assertEqual(bol['pickupRequest']['pickup']['time'], '10:00:00')
        self.assertEqual(bol['pickupRequest']['pickup']['openTime'], '08:00:00')
        self.assertEqual(bol['pickupRequest']['pickup']['closeTime'], '16:00:00')
        self.assertEqual(bol['pickupRequest']['pickup']['date'], str(self.shipment.ship_date))
        self.assertEqual(bol['shipTo']['phone'], {'number': '7045550199'})
        self.assertEqual(bol['documents']['image'], [{'type': '20', 'format': '01'}])
        shipment = self.shipment
        self.assertEqual(shipment.state, 'booked')
        self.assertEqual(shipment.pro_number, '062108025')  # zero-padded to 9 digits
        self.assertEqual(shipment.pickup_number, 'WBU3261541')
        self.assertEqual(shipment.quote_number, 'Q123456')
        self.assertEqual(shipment.quoted_amount, 412.5)
        self.assertEqual(shipment.tforce_bol_id, '8418552')
        attachments = self.env['ir.attachment'].search(
            [('res_model', '=', shipment._name), ('res_id', '=', shipment.id)])
        self.assertIn('TForce eBOL (carrier copy) 062108025.pdf', attachments.mapped('name'))
        self.assertIn('BOL 062108025.pdf', attachments.mapped('name'))  # our BOL, to print
        self.assertEqual(shipment.message_main_attachment_id.name, 'BOL 062108025.pdf')
        messages = ' '.join(shipment.message_ids.mapped('body'))
        self.assertIn('RURAL POINT', messages)
        self.assertIn('TEST environment', messages)

    def test_track_and_documents_on_delivery(self):
        self.shipment.write({'pro_number': '062108025', 'state': 'in_transit'})
        self.answers['/track/pro/multiple'] = FakeResponse(200, {'detail': [{
            'pro': '62108025',
            'currentStatus': {'code': '011', 'description': 'Delivered'},
            'delivery': {'actual': {'date': '2026-11-03'}, 'signedBy': 'ABEL'},
        }]})
        self.answers['/documents/pro'] = FakeResponse(200, {'detail': [
            {'category': 'DR', 'id': '538833', 'data': base64.b64encode(PDF).decode()},
            {'category': 'WGHT', 'id': '538834', 'data': base64.b64encode(PDF).decode()},
        ]})
        self.shipment.action_update_tracking()
        self.assertEqual(self.shipment.state, 'delivered')
        self.assertEqual(str(self.shipment.delivered_date), '2026-11-03')
        self.assertIn('ABEL', self.shipment.tracking_status)
        names = self.env['ir.attachment'].search(
            [('res_model', '=', self.shipment._name), ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt 062108025 538833.pdf', names)
        self.assertIn('Weight and inspection 062108025 538834.pdf', names)
        docs_call = [c for c in self.calls if c['url'].endswith('/documents/pro')][0]['json']
        self.assertEqual(docs_call['pro'], '062108025')
        # Asking again does not attach the same documents twice.
        self.shipment.action_fetch_documents()
        self.assertEqual(self.env['ir.attachment'].search_count(
            [('res_model', '=', self.shipment._name), ('res_id', '=', self.shipment.id)]), 2)

    def test_errors_are_shown(self):
        self.answers['/rating/getRate'] = FakeResponse(400, {
            'summary': {'responseStatus': {'code': 'ERR', 'message': 'Invalid destination postal code'}}})
        with self.assertRaisesRegex(UserError, 'Invalid destination postal code'):
            self.carrier.ltl_rate(self.shipment)

    def test_consignee_phone_required_before_booking(self):
        self.consignee.phone = False
        with self.assertRaisesRegex(UserError, 'phone number'):
            self.carrier.ltl_book(self.shipment, {'total': 1})
        self.assertFalse([c for c in self.calls if c['url'].endswith('/shipping/bol/create')])

    def test_pickup_window_from_shipment(self):
        self.shipment.write({'pickup_ready_time': 13.5, 'pickup_close_time': 17.0})
        request = self.carrier._tforce_bol_request(self.shipment)
        pickup = request['pickupRequest']['pickup']
        self.assertEqual((pickup['time'], pickup['openTime'], pickup['closeTime']),
                         ('13:30:00', '08:00:00', '17:00:00'))

    def test_production_version(self):
        self.carrier.tforce_environment = 'production'
        self.answers['/rating/getRate'] = FakeResponse(200, RATE_ANSWER)
        self.carrier.ltl_rate(self.shipment)
        self.assertEqual(self.calls[0]['params'], {'api-version': 'v1'})

    def test_odoo_delivery_hooks_do_not_book(self):
        self.assertFalse(self.carrier.tforce_rate_shipment(None)['success'])
        self.assertFalse(self.calls)
