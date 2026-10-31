# -*- coding: utf-8 -*-
"""Roadrunner connector tests with Roadrunner's answers simulated (no network)."""
import base64
import hashlib
import hmac
import json
from unittest.mock import patch
from urllib.parse import quote_plus

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.selamta_ltl_roadrunner.models.delivery_carrier'
PDF = b'%PDF-1.4 roadrunner test'
JPG = b'\xff\xd8\xff roadrunner pod'
NS = 'https://webservices.rrts.com/ratequote/'


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


def soap_rate(net='412.50', details=None, transit='3', quote='109724929'):
    details = details if details is not None else [
        ('', '70', '70', '1800', '2744.20'),
        ('DIS', '', '', '', '-2565.83'),
        ('LGD', '', '', '', '65.00'),
        ('FSC', '', '', '', '99.26'),
    ]
    lines = ''.join(
        '<QuoteDetail><ActualClass>%s</ActualClass><RatedClass>%s</RatedClass><Charge>%s</Charge>'
        '<Code>%s</Code><Description>%s</Description><Rate>0</Rate><Weight>%s</Weight>'
        '<ExtraMessages /></QuoteDetail>' % (actual, rated, charge, code, code or 'Base', weight)
        for code, actual, rated, weight, charge in details)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
        '<RateQuoteByAccountV2Response xmlns="%s"><RateQuoteByAccountV2Result>'
        '<QuoteNumber>%s</QuoteNumber><NetCharge>%s</NetCharge>'
        '<Customer><AccountNumber>601698</AccountNumber></Customer>'
        '<RoutingInfo><DestinationZip>28202</DestinationZip><OriginZip>30035</OriginZip>'
        '<EstimatedTransitDays>%s</EstimatedTransitDays><OriginTerminal>ATL</OriginTerminal></RoutingInfo>'
        '<RateDetails>%s</RateDetails><OriginType>O</OriginType><PaymentType>P</PaymentType>'
        '</RateQuoteByAccountV2Result></RateQuoteByAccountV2Response></soap:Body></soap:Envelope>'
        % (NS, quote, net, transit, lines)).encode()


SOAP_FAULT = (
    b'<?xml version="1.0" encoding="utf-8"?>'
    b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><soap:Fault>'
    b'<faultcode>soap:Client</faultcode><faultstring>99998 - Invalid user</faultstring>'
    b'</soap:Fault></soap:Body></soap:Envelope>')

BOL_ANSWER = {
    'HasError': False, 'ErrorMessage': None, 'BOLNumber': None, 'PRONumber': '589084565',
    'PickUpNumber': '55471537', 'TerminalName': 'ATLANTA', 'TerminalPhone': '(404) 555-0123',
    'QuoteNumber': 109724930,
    'QuoteResponse': {'quoteNumberField': 109724930, 'netChargeField': 412.50},
    'Base64PDFData': base64.b64encode(PDF).decode(),
}


@tagged('post_install', '-at_install')
class TestRoadrunner(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        ga = env['res.country.state'].search([('code', '=', 'GA'), ('country_id', '=', us.id)])
        nc = env['res.country.state'].search([('code', '=', 'NC'), ('country_id', '=', us.id)])
        env.company.partner_id.write({
            'street': '5335 Dividend Dr #C', 'city': 'Decatur', 'zip': '30035-1234',
            'state_id': ga.id, 'country_id': us.id, 'phone': '+1 (404) 555-0100',
            'email': 'shipping@example.com'})
        cls.consignee = env['res.partner'].create({
            'name': 'Sample Market', 'is_company': True, 'street': '100 Example Ave',
            'city': 'Charlotte', 'zip': '28202', 'state_id': nc.id, 'country_id': us.id,
            'phone': '704-555-0199'})
        cls.vendor = env['res.partner'].create({'name': 'Roadrunner', 'is_company': True})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.carrier = env['delivery.carrier'].create({
            'name': 'Roadrunner', 'product_id': product.id, 'delivery_type': 'roadrunner',
            'ltl_enabled': True, 'ltl_vendor_id': cls.vendor.id,
            'rrts_account_number': '601698', 'rrts_username': 'demo', 'rrts_password': 'p&ss<1>',
            'rrts_contact_name': 'Dock', 'rrts_contact_email': 'dock@example.com',
            'rrts_contact_phone': '404-555-0100',
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
        self.answers = {}

        def fake_request(method, url, **kwargs):
            self.calls.append(dict(kwargs, method=method, url=url))
            for key, answer in self.answers.items():
                if key in url:
                    return answer() if callable(answer) else answer
            return FakeResponse(404, {'Message': 'not found'})

        patcher = patch(MODULE + '.requests.request', side_effect=fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calls_to(self, part):
        return [c for c in self.calls if part in c['url']]

    def test_rate_request_and_answer(self):
        self.answers['ratequote.asmx'] = FakeResponse(200, content=soap_rate())
        rates = self.carrier.ltl_rate(self.shipment)
        call = self.calls[0]
        self.assertEqual(call['method'], 'POST')
        self.assertEqual(call['headers']['SOAPAction'], '"https://webservices.rrts.com/ratequote/RateQuoteByAccountV2"')
        root = etree.fromstring(call['data'])

        def text(path):
            return root.findtext(path, namespaces={'r': NS, 's': 'http://schemas.xmlsoap.org/soap/envelope/'})

        self.assertEqual(text('s:Header/r:AuthenticationHeader/r:UserName'), 'demo')
        self.assertEqual(text('s:Header/r:AuthenticationHeader/r:Password'), 'p&ss<1>')  # escaped, not broken
        request = 's:Body/r:RateQuoteByAccountV2/r:request/'
        self.assertEqual(text(request + 'r:OriginZip'), '30035')  # ZIP+4 cut to 5
        self.assertEqual(text(request + 'r:DestinationZip'), '28202')
        self.assertEqual(text(request + 'r:ShipmentDetails/r:ShipmentDetail/r:ActualClass'), '85')
        self.assertEqual(text(request + 'r:ShipmentDetails/r:ShipmentDetail/r:Weight'), '1800')
        self.assertEqual(text(request + 'r:OriginType'), 'O')
        self.assertEqual(text(request + 'r:PaymentType'), 'P')
        self.assertEqual(text(request + 'r:PalletCount'), '2')
        self.assertEqual(text(request + 'r:Pieces'), '2')
        self.assertEqual(text(request + 'r:ServiceDeliveryOptions/r:ServiceOptions/r:ServiceCode'), 'LGD')
        self.assertEqual(text(request + 'r:ShipDate'), '%sT00:00:00' % self.shipment.ship_date)
        self.assertEqual(text(request + 'r:Account'), '601698')
        names = [etree.QName(n).localname for n in root.find(request[:-1], namespaces={
            'r': NS, 's': 'http://schemas.xmlsoap.org/soap/envelope/'})]
        self.assertEqual(names[-1], 'Account')  # derived field after the QuoteRequest fields
        self.assertLess(names.index('ShipDate'), names.index('Account'))
        self.assertEqual(len(rates), 1)
        rate = rates[0]
        self.assertEqual(rate['total'], 412.5)
        self.assertEqual(rate['transit_days'], 3)
        self.assertEqual(rate['quote_number'], '109724929')
        codes = [c['code'] for c in rate['charges']]
        self.assertEqual(codes[:4], ['LINEHAUL', 'DIS', 'LGD', 'FSC'])
        self.assertEqual(rate['charges'][1]['amount'], -2565.83)
        self.assertEqual(rate['charges'][2]['name'], 'Liftgate at delivery')
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 412.5)  # adds up to the total

    def test_discount_sent_positive_is_shown_negative(self):
        self.answers['ratequote.asmx'] = FakeResponse(200, content=soap_rate(
            net='243.37', details=[('', '70', '70', '1800', '2744.20'), ('DIS', '', '', '', '2565.83'),
                                   ('FSC', '', '', '', '65.00')]))
        rate = self.carrier.ltl_rate(self.shipment)[0]
        self.assertEqual(rate['charges'][1]['amount'], -2565.83)
        self.assertEqual([c['code'] for c in rate['charges']], ['LINEHAUL', 'DIS', 'FSC'])

    def test_rate_errors_are_shown(self):
        self.answers['ratequote.asmx'] = FakeResponse(500, content=SOAP_FAULT)
        with self.assertRaisesRegex(UserError, 'Invalid user'):
            self.carrier.ltl_rate(self.shipment)
        self.answers['ratequote.asmx'] = FakeResponse(200, content=soap_rate(net='-1', details=[]))
        with self.assertRaisesRegex(UserError, 'cannot rate'):
            self.carrier.ltl_rate(self.shipment)

    def test_book_through_rate_shop(self):
        self.answers['ratequote.asmx'] = FakeResponse(200, content=soap_rate())
        self.answers['bolrequest'] = FakeResponse(200, BOL_ANSWER)
        action = self.shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        line = wizard.line_ids.filtered(lambda l: l.carrier_id == self.carrier)
        self.assertEqual(line.total, 412.5)
        line.action_choose()
        call = self._calls_to('bolrequest')[0]
        self.assertEqual(call['url'], 'https://webservices-test.rrts.com/bol/api/bolrequest')  # test by default
        self.assertEqual(call['auth'], ('demo', 'p&ss<1>'))
        bol = call['json']
        self.assertEqual(bol['MainAccountNumber'], '601698')
        self.assertEqual(bol['PayTerms'], 'P')
        self.assertEqual(bol['ShipDt'], str(self.shipment.ship_date))
        self.assertEqual(bol['BOLNumber'], self.shipment.name)
        self.assertTrue(bol['GenerateBOL'])
        self.assertEqual(bol['ShipperAddr']['Phone'], '(404) 555-0100')
        self.assertEqual(bol['ShipperAddr']['Zip'], '30035')
        self.assertEqual(bol['ShipperAddr']['Contact'], 'Dock')
        self.assertEqual(bol['ConsigneeAddr']['Company'], 'Sample Market')
        self.assertEqual(bol['ConsigneeAddr']['Contact'], 'Receiving')
        self.assertEqual(bol['ConsigneeAddr']['Country'], 'United States')
        self.assertEqual(bol['ConsigneeAddr']['Phone'], '(704) 555-0199')
        commodity = bol['Commodities'][0]
        self.assertEqual((commodity['UnitDesc'], commodity['UnitQnty']), ('Pallet', 2))
        self.assertEqual(commodity['ClassCode'], 85.0)
        self.assertEqual(commodity['Weight'], 1800)
        self.assertEqual((commodity['Length'], commodity['Width'], commodity['Height']), (48, 40, 60))
        self.assertEqual(commodity['NMFC'], '73260')
        self.assertEqual(bol['Accessorials'], [{'AccessorialCode': 'LGD'}])
        self.assertEqual(bol['Instructions'], 'LIFTGATE AT DELIVERY, NO INSIDE DELIVERY')
        self.assertTrue(bol['QuickPickup'])
        self.assertEqual((bol['FreightReady'], bol['FreightClosed']), ('10:00', '16:00'))
        self.assertEqual(bol['ReqEmail'], 'dock@example.com')
        self.assertFalse(bol['PrintLabel'])
        shipment = self.shipment
        self.assertEqual(shipment.state, 'booked')
        self.assertEqual(shipment.pro_number, '589084565')
        self.assertEqual(shipment.pickup_number, '55471537')
        self.assertEqual(shipment.quote_number, '109724929')
        self.assertEqual(shipment.quoted_amount, 412.5)
        self.assertEqual(shipment.rrts_terminal, 'ATLANTA ((404) 555-0123)')
        names = self.env['ir.attachment'].search(
            [('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name')
        self.assertIn('Roadrunner BOL (carrier copy) 589084565.pdf', names)
        self.assertIn('BOL 589084565.pdf', names)  # our BOL, to print
        self.assertEqual(shipment.message_main_attachment_id.name, 'BOL 589084565.pdf')
        messages = ' '.join(shipment.message_ids.mapped('body'))
        self.assertIn('TEST system', messages)
        self.assertNotIn('&lt;br', messages)  # line breaks, not escaped tags

    def test_booking_errors_and_production(self):
        self.answers['bolrequest'] = FakeResponse(200, {'HasError': True, 'ErrorMessage': 'Ship date is in the past'})
        with self.assertRaisesRegex(UserError, 'Ship date is in the past'):
            self.carrier.ltl_book(self.shipment, {'total': 1})
        self.answers['bolrequest'] = FakeResponse(401, content=b'Unauthorized')
        with self.assertRaisesRegex(UserError, 'refused the sign-in'):
            self.carrier.ltl_book(self.shipment, {'total': 1})
        self.carrier.rrts_environment = 'production'
        self.answers['bolrequest'] = FakeResponse(200, dict(BOL_ANSWER, PRONumber=None))
        result = self.carrier.ltl_book(self.shipment, {'total': 1})
        self.assertEqual(self._calls_to('bolrequest')[-1]['url'], 'https://webservices.rrts.com/BOL/api/bolrequest')
        self.assertFalse(result['pro_number'])
        self.assertIn('did not send the PRO', ' '.join(self.shipment.message_ids.mapped('body')))

    def test_consignee_phone_required_before_booking(self):
        self.consignee.phone = False
        with self.assertRaisesRegex(UserError, 'phone number'):
            self.carrier.ltl_book(self.shipment, {'total': 1})
        self.assertFalse(self._calls_to('bolrequest'))

    def test_pickup_window_labels_and_references(self):
        self.shipment.write({'pickup_ready_time': 13.5, 'pickup_close_time': 17.25,
                             'pickup_instructions': 'Use dock door 2'})
        self.carrier.rrts_label_style = '4'
        request = self.carrier._rrts_bol_request(self.shipment)
        self.assertEqual((request['FreightReady'], request['FreightClosed']), ('13:30', '17:15'))
        self.assertEqual(request['Instructions'],
                         'LIFTGATE AT DELIVERY, NO INSIDE DELIVERY; PICKUP: Use dock door 2')
        self.assertEqual((request['PrintLabel'], request['LabelStyle'], request['NumberOfLabels']), (True, '4', 2))
        self.carrier.rrts_schedule_pickup = False
        self.assertNotIn('QuickPickup', self.carrier._rrts_bol_request(self.shipment))

    def test_too_many_lines(self):
        self.shipment.write({'unit_ids': [(0, 0, {'quantity': 1, 'unit_type': 'box', 'length': 20 + i,
                                                  'width': 20, 'height': 20, 'weight': 50})
                                          for i in range(9)]})
        with self.assertRaisesRegex(UserError, 'at most 9'):
            self.carrier._rrts_bol_request(self.shipment)

    def test_track_by_pickup_then_pro_and_delivery_receipt(self):
        self.shipment.write({'pickup_number': '55471537', 'state': 'booked'})
        self.answers['api/values/'] = FakeResponse(200, {'SearchResults': [{
            'SearchItem': '55471537',
            'Shipment': {'ProNumber': '589084565', 'PickedUp': True, 'Location': 'ATLANTA',
                         'DeliveredDateTime': '0001-01-01T00:00:00',
                         'Comments': [{'ActivityCode': 'PU', 'StatusComment': 'Picked up',
                                       'StatusDateTime': '2026-11-02T15:10:00'}]},
        }]})
        self.shipment.action_update_tracking()
        self.assertEqual(self._calls_to('api/values/')[0]['url'],
                         'https://webservices.rrts.com/TrackWebApi/api/values/55471537')
        self.assertNotIn('Authorization', self._calls_to('api/values/')[0]['headers'])
        self.assertEqual(self.shipment.pro_number, '589084565')  # PRO learned from tracking
        self.assertEqual(self.shipment.state, 'in_transit')
        self.assertEqual(self.shipment.tracking_status, 'Picked up (ATLANTA)')

        self.answers['api/values/'] = FakeResponse(200, {'SearchResults': [{
            'SearchItem': '589084565',
            'Shipment': {'ProNumber': '589084565', 'PickedUp': True,
                         'DeliveredDateTime': '2026-11-05T13:57:00',
                         'Comments': [{'ActivityCode': 'PU', 'StatusComment': 'Picked up',
                                       'StatusDateTime': '2026-11-02T15:10:00'},
                                      {'ActivityCode': 'DEL', 'StatusComment': 'Delivered',
                                       'StatusDateTime': '2026-11-05T13:57:00'}]},
        }]})
        self.answers['api/images'] = FakeResponse(200, [{
            'ProNumber': 589084565, 'HasError': False, 'ErrorMessage': None,
            'Images': [{'FileName': 'POD_589084565_1.jpg', 'Base64Image': base64.b64encode(JPG).decode()}],
        }])
        self.shipment.action_update_tracking()
        self.assertTrue(self._calls_to('api/values/589084565'))
        self.assertEqual(self.shipment.state, 'delivered')
        self.assertEqual(str(self.shipment.delivered_date), '2026-11-05')
        self.assertEqual(self.shipment.tracking_status, 'Delivered')
        images_call = self._calls_to('api/images')[0]
        self.assertEqual(images_call['json'], [{'ImageType': 'POD', 'ProNumber': 589084565}])
        self.assertNotIn('Authorization', images_call['headers'])  # no app ID: delivery receipt only
        names = self.env['ir.attachment'].search(
            [('res_model', '=', self.shipment._name), ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt POD_589084565_1.jpg', names)
        # Asking again does not attach the same image twice.
        self.shipment.action_fetch_documents()
        self.assertEqual(names.count('Delivery receipt POD_589084565_1.jpg'), 1)
        self.assertEqual(self.env['ir.attachment'].search_count(
            [('res_model', '=', self.shipment._name), ('res_id', '=', self.shipment.id),
             ('name', '=', 'Delivery receipt POD_589084565_1.jpg')]), 1)

    def test_signed_images_with_app_id(self):
        self.carrier.write({'rrts_app_id': '7e437b64-81fd-4ea9-b354-66f10749e5d1', 'rrts_api_key': 'secretkey'})
        self.shipment.pro_number = '589084565'
        self.answers['api/images'] = FakeResponse(200, [{'ProNumber': 589084565, 'HasError': False, 'Images': [
            {'FileName': 'BOL_589084565_1.jpg', 'Base64Image': base64.b64encode(JPG).decode()}]}])
        with patch(MODULE + '.time.time', return_value=1793400000.4), \
                patch(MODULE + '.uuid.uuid4') as fake_uuid:
            fake_uuid.return_value.hex = 'a' * 32
            documents = self.carrier.ltl_documents(self.shipment)
        signed = [c for c in self._calls_to('api/images') if 'Authorization' in c['headers']]
        self.assertEqual(len(signed), 1)
        self.assertEqual([i['ImageType'] for i in signed[0]['json']], ['BOL', 'WI', 'INVOICE'])
        url = 'https://webservices.rrts.com/TrackWebApi/api/images'
        raw = '7E437B64-81FD-4EA9-B354-66F10749E5D1POST%s1793400000%s' % (quote_plus(url, safe=''), 'a' * 32)
        self.assertIn('https%3A%2F%2Fwebservices.rrts.com%2FTrackWebApi%2Fapi%2Fimages', raw)  # upper-case %XX
        expected = base64.b64encode(hmac.new(b'secretkey', raw.encode(), hashlib.sha256).digest()).decode()
        self.assertEqual(signed[0]['headers']['Authorization'],
                         'amx 7E437B64-81FD-4EA9-B354-66F10749E5D1:%s:%s:1793400000' % (expected, 'a' * 32))
        self.assertIn('Roadrunner signed BOL BOL_589084565_1.jpg', [d[0] for d in documents])

    def test_test_connection_button(self):
        self.answers['ratequote.asmx'] = FakeResponse(200, content=soap_rate(net='150.00', details=[]))
        action = self.carrier.action_rrts_test_connection()
        self.assertIn('601698', action['params']['message'])
        self.assertIn('150.00', action['params']['message'])
        self.assertFalse(self.env['selamta.ltl.shipment'].search([('partner_id', '=', self.env.company.partner_id.id)]))

    def test_missing_settings(self):
        self.carrier.rrts_password = False
        with self.assertRaisesRegex(UserError, 'username and password'):
            self.carrier.ltl_rate(self.shipment)
        self.carrier.write({'rrts_password': 'x', 'rrts_account_number': False})
        with self.assertRaisesRegex(UserError, 'account number'):
            self.carrier.ltl_rate(self.shipment)
        self.assertFalse(self.calls)

    def test_odoo_delivery_hooks_do_not_book(self):
        self.assertFalse(self.carrier.roadrunner_rate_shipment(None)['success'])
        self.assertFalse(self.calls)
