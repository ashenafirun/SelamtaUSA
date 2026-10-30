# -*- coding: utf-8 -*-
"""AAA Cooper connector tests with AAA Cooper's answers simulated (no network). The XML
answers follow the samples in AAA Cooper's web service documentation."""
import json
from datetime import timedelta
from unittest.mock import patch

from lxml import etree

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.selamta_ltl_aaacooper.models.delivery_carrier'
PDF = b'%PDF-1.4 aaa cooper test'
RATE_NS = 'http://tempuri.org/wsGenRateEstimate/'
PICKUP_NS = 'http://tempuri.org/wsPickUpRq/'
TRACK_NS = 'http://tempuri.org/WsGetTracking/'


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


def envelope(inner):
    return ('<?xml version="1.0" encoding="ISO-8859-1"?><soap:Envelope '
            'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>%s</soap:Body></soap:Envelope>'
            % inner).encode('iso-8859-1')


def rate_answer(total='581.90', error='', lines=None):
    lines = lines if lines is not None else [
        ('FAK 85', '1,800', '2985.10', ''), ('DISCOUNT 88.0 PCT', '', '-2626.89', 'DSC'),
        ('LIFTGATE DELIVERY', '', '117.88', 'LGD'), ('FUEL SURCHARGE 29.54 PCT', '', '105.81', 'FSC'),
    ]
    body = ''.join('<RateEstimateResponseLine><Description>%s</Description><Weight>%s</Weight>'
                   '<Charges>%s</Charges><Accessorial>%s</Accessorial></RateEstimateResponseLine>' % line
                   for line in lines)
    return envelope(
        '<ns1:RateEstimateResponseVO xmlns:ns1="%s"><ErrorMessage>%s</ErrorMessage>'
        '<EstimateNumber>1234567890</EstimateNumber><OriginTerminal>ATL</OriginTerminal>'
        '<TotalCharges>%s</TotalCharges><InformationCode>RATED</InformationCode><InterlineFlag/>'
        '<TotalTransit>02</TotalTransit>%s</ns1:RateEstimateResponseVO>' % (RATE_NS, error, total, body))


PICKUP_ANSWER = envelope(
    '<ns1:wsPickUpRqResponse xmlns:ns1="%s"><PickupRequestNumber>000000000000012345</PickupRequestNumber>'
    '<ErrorCode/><ErrorMessage/><AlertMessage/><ACTTerminal>SAA</ACTTerminal>'
    '<ACTTerminalPhone>4043631336</ACTTerminalPhone><Severity/></ns1:wsPickUpRqResponse>' % PICKUP_NS)


def tracking_answer(pro, status, delivery='0001-01-01', pickup='2026-11-02', signed='', error=''):
    return envelope(
        '<ns1:GetTrackingResponse xmlns:ns1="%s"><ProLine><ErrorMessage>%s</ErrorMessage>'
        '<DeliveryDate>%s</DeliveryDate><PickupDate>%s</PickupDate><ProNumber>%s</ProNumber>'
        '<Status>%s</Status><SignedFor>%s</SignedFor>'
        '<TracingLine><Description>Shipment Picked Up From Shipper In DECATUR, GA</Description>'
        '<Date>2026-11-02</Date></TracingLine></ProLine></ns1:GetTrackingResponse>'
        % (TRACK_NS, error, delivery, pickup, pro, status, signed))


@tagged('post_install', '-at_install')
class TestAaaCooper(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        ga = env['res.country.state'].search([('code', '=', 'GA'), ('country_id', '=', us.id)])
        nc = env['res.country.state'].search([('code', '=', 'NC'), ('country_id', '=', us.id)])
        env.company.partner_id.write({
            'street': '5335 Dividend Dr Suite C', 'city': 'Decatur', 'zip': '30035',
            'state_id': ga.id, 'country_id': us.id, 'phone': '+1 (404) 555-0100', 'email': 'ship@example.com'})
        cls.consignee = env['res.partner'].create({
            'name': 'Sample Market', 'is_company': True, 'street': '100 Example Ave',
            'city': 'Charlotte', 'zip': '28202', 'state_id': nc.id, 'country_id': us.id,
            'phone': '704-555-0199'})
        cls.vendor = env['res.partner'].create({'name': 'AAA Cooper', 'is_company': True})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.carrier = env['delivery.carrier'].create({
            'name': 'AAA Cooper', 'product_id': product.id, 'delivery_type': 'aaacooper',
            'ltl_enabled': True, 'ltl_vendor_id': cls.vendor.id, 'ltl_scac': 'AACT',
            'aact_token': 'tok-123', 'aact_customer_number': '2219427', 'aact_contact_name': 'Dock',
        })
        cls.shipment = env['selamta.ltl.shipment'].create({
            'partner_id': cls.consignee.id,
            'carrier_id': cls.carrier.id,
            'ship_date': fields.Date.context_today(env['selamta.ltl.shipment']) + timedelta(days=2),
            'accessorial_ids': [(6, 0, [env.ref('selamta_ltl.accessorial_liftgate_delivery').id])],
            'unit_ids': [(0, 0, {'quantity': 2, 'unit_type': 'pallet', 'description': 'Teff flour',
                                 'length': 48, 'width': 40, 'height': 60, 'weight': 1800})],
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
            return FakeResponse(404, {'message': 'not found'})

        patcher = patch(MODULE + '.requests.request', side_effect=fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calls_to(self, part):
        return [c for c in self.calls if part in c['url']]

    @staticmethod
    def _xml(call):
        return etree.fromstring(call['data'])

    def test_rate_request_and_answer(self):
        self.answers['/sapi30/wsGenEst'] = FakeResponse(200, content=rate_answer())
        rate = self.carrier.ltl_rate(self.shipment)[0]
        call = self._calls_to('wsGenEst')[0]
        self.assertEqual(call['url'], 'https://api2.aaacooper.com:8200/sapi30/wsGenEst')
        root = self._xml(call)
        ns = {'r': RATE_NS}
        req = root.find('.//r:RateEstimateRequestVO', ns)
        self.assertEqual(req.findtext('r:Token', namespaces=ns), 'tok-123')
        self.assertEqual(req.findtext('r:CustomerNumber', namespaces=ns), '2219427')
        self.assertEqual((req.findtext('r:OriginZip', namespaces=ns), req.findtext('r:OriginCountryCode', namespaces=ns)),
                         ('30035', 'USA'))
        self.assertEqual(req.findtext('r:DestinationCity', namespaces=ns), 'Charlotte')
        self.assertEqual(req.findtext('r:WhoAmI', namespaces=ns), 'S')
        self.assertEqual(req.findtext('r:BillDate', namespaces=ns), self.shipment.ship_date.strftime('%m%d%Y'))
        self.assertEqual(req.findtext('r:PrePaidCollect', namespaces=ns), 'P')
        self.assertEqual(req.findtext('r:TotalPalletCount', namespaces=ns), '2')
        self.assertEqual([a.text for a in req.findall('r:AccLine/r:AccCode', ns)], ['LGD'])
        line = req.find('r:RateEstimateRequestLine', ns)
        self.assertEqual((line.findtext('r:Weight', namespaces=ns), line.findtext('r:Class', namespaces=ns),
                          line.findtext('r:HandlingUnits', namespaces=ns), line.findtext('r:HandlingUnitType', namespaces=ns)),
                         ('1800', '85', '2', 'Pallets'))
        self.assertEqual((line.findtext('r:Length', namespaces=ns), line.findtext('r:Width', namespaces=ns),
                          line.findtext('r:Height', namespaces=ns)), ('48', '40', '60'))
        self.assertEqual(rate['total'], 581.90)
        self.assertEqual(rate['transit_days'], 2)
        self.assertEqual(rate['quote_number'], '1234567890')
        self.assertEqual([c['code'] for c in rate['charges']], ['LINE', 'DSC', 'LGD', 'FSC'])
        self.assertEqual(rate['charges'][1]['amount'], -2626.89)
        self.assertEqual(rate['charges'][2]['name'], 'Liftgate delivery')
        self.answers['/sapi30/wsGenEst'] = FakeResponse(200, content=rate_answer(total='100.00', lines=[
            ('', '1,800', '100.00', '')]).replace(b'<Weight>', b'<Class>85</Class><Weight>'))
        self.assertEqual(self.carrier.ltl_rate(self.shipment)[0]['charges'][0]['name'],
                         'Linehaul before discount, class 85')
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 581.90)

    def test_pallet_pricing_and_errors(self):
        self.carrier.aact_pallet_pricing = True
        self.answers['/sapi30/wsGenEst'] = FakeResponse(200, content=rate_answer())
        self.carrier.ltl_rate(self.shipment)
        req = self._xml(self._calls_to('wsGenEst')[0])
        self.assertEqual([a.text for a in req.iter('{%s}AccCode' % RATE_NS)], ['LGD', 'PALET'])
        self.answers['/sapi30/wsGenEst'] = FakeResponse(200, content=rate_answer(error='Token ID Invalid'))
        with self.assertRaisesRegex(UserError, 'Token ID Invalid'):
            self.carrier.ltl_rate(self.shipment)
        self.answers['/sapi30/wsGenEst'] = FakeResponse(500, content=envelope(
            '<soap:Fault><faultcode>soap:Server</faultcode><faultstring>Server down</faultstring></soap:Fault>'))
        with self.assertRaisesRegex(UserError, 'Server down'):
            self.carrier.ltl_rate(self.shipment)

    def test_booking_is_off_by_default(self):
        self.answers['/sapi30/wsGenEst'] = FakeResponse(200, content=rate_answer())
        self.assertFalse(self.carrier.ltl_can('book'))
        action = self.shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        wizard.line_ids.filtered(lambda l: l.carrier_id == self.carrier).action_choose()
        self.assertFalse(self._calls_to('wsPickUpRq'))
        self.assertEqual((self.shipment.state, self.shipment.quote_number), ('draft', '1234567890'))

    def test_pickup_request_through_rate_shop(self):
        self.carrier.aact_book_pickups = True
        self.shipment.write({'pickup_ready_time': 13.5, 'pickup_close_time': 17.0,
                             'pickup_instructions': 'Dock door 2'})
        self.answers['/sapi30/wsGenEst'] = FakeResponse(200, content=rate_answer())
        self.answers['/sapi30/wsPickUpRq'] = FakeResponse(200, content=PICKUP_ANSWER)
        action = self.shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        wizard.line_ids.filtered(lambda l: l.carrier_id == self.carrier).action_choose()
        ns = {'p': PICKUP_NS}
        req = self._xml(self._calls_to('wsPickUpRq')[0]).find('.//p:wsPickUpRqRequest', ns)
        text = lambda path: req.findtext(path, namespaces=ns)  # noqa: E731
        self.assertEqual(text('p:TokenID'), 'tok-123')
        self.assertEqual(text('p:PkupCompanyAddress'), '5335 Dividend Dr Suite C')
        self.assertEqual((text('p:PkupCompanyContact'), text('p:PkupCompanyPhone'), text('p:PkupCompanyEmail')),
                         ('Dock', '4045550100', 'ship@example.com'))
        self.assertEqual(text('p:PickupDate'), self.shipment.ship_date.strftime('%m/%d/%Y'))
        self.assertEqual((text('p:ReadyTime'), text('p:CloseTime')), ('13:30', '17:00'))
        self.assertEqual(text('p:PickupComments'),
                         'BOL %s. Dock door 2. LIFTGATE AT DELIVERY. NO INSIDE DELIVERY' % self.shipment.name)
        line = 'p:LineItems/p:LineItem/'
        self.assertEqual(text(line + 'p:EstimateNumber'), '1234567890')
        self.assertEqual(text(line + 'p:BOLID'), self.shipment.name)
        self.assertEqual((text(line + 'p:Pieces'), text(line + 'p:HandlingUnitType'), text(line + 'p:TotalWeight')),
                         ('2', 'Pallets', '1800'))
        self.assertEqual((text(line + 'p:DestinationCompanyContact'), text(line + 'p:DestinationCompanyPhone')),
                         ('Receiving', '7045550199'))
        self.assertEqual(text(line + 'p:DestinationCountry'), 'USA')
        shipment = self.shipment
        self.assertEqual(shipment.state, 'booked')
        self.assertEqual(shipment.pickup_number, '12345')
        self.assertEqual(shipment.aact_terminal, 'SAA (4043631336)')
        self.assertEqual(shipment.message_main_attachment_id.name, 'BOL %s.pdf' % shipment.name)  # our BOL

    def test_pickup_error(self):
        self.carrier.aact_book_pickups = True
        self.answers['/sapi30/wsPickUpRq'] = FakeResponse(200, content=envelope(
            '<ns1:wsPickUpRqResponse xmlns:ns1="%s"><PickupRequestNumber/><ErrorCode>ERR0000334</ErrorCode>'
            '<ErrorMessage>PICKUP DATE MUST BE CURRENT OR FUTURE</ErrorMessage></ns1:wsPickUpRqResponse>' % PICKUP_NS))
        with self.assertRaisesRegex(UserError, 'ERR0000334.*CURRENT OR FUTURE'):
            self.carrier.ltl_book(self.shipment, {'total': 1})

    def test_track_by_bol_then_pro_and_documents(self):
        self.shipment.write({'state': 'booked', 'pickup_number': '12345'})
        self.answers['/sapi30/wsTracking'] = FakeResponse(200, content=tracking_answer('87654321', 'Picked Up'))
        self.shipment.action_update_tracking()
        req = self._xml(self._calls_to('wsTracking')[0])
        self.assertEqual(req.findtext('.//{%s}BOLNumber' % TRACK_NS), self.shipment.name)
        self.assertFalse(req.findtext('.//{%s}ProNumber' % TRACK_NS))
        self.assertEqual(self.shipment.pro_number, '87654321')
        self.assertEqual(self.shipment.state, 'in_transit')
        self.assertEqual(self.shipment.tracking_status,
                         'Picked Up - Shipment Picked Up From Shipper In DECATUR, GA')

        self.answers['/sapi30/wsTracking'] = FakeResponse(200, content=tracking_answer(
            '87654321', 'Delivered', delivery='2026-11-04', signed='ABEL'))
        self.answers['/sapi30/documents'] = lambda: FakeResponse(200, {'proNumber': '87654321', 'images': [
            {'url': 'https://img.aaacooper.com/doc.pdf', 'type': 'Delivery Receipt', 'format': 'PDF'}]})
        self.answers['img.aaacooper.com'] = FakeResponse(200, content=PDF)
        self.shipment.action_update_tracking()
        req = self._xml(self._calls_to('wsTracking')[-1])
        self.assertEqual(req.findtext('.//{%s}ProNumber' % TRACK_NS), '87654321')
        self.assertEqual(self.shipment.state, 'delivered')
        self.assertEqual(str(self.shipment.delivered_date), '2026-11-04')
        self.assertIn('signed by ABEL', self.shipment.tracking_status)
        doc_calls = self._calls_to('/sapi30/documents')
        self.assertEqual([c['params']['type'] for c in doc_calls], ['POD', 'INSPT'])
        self.assertEqual(doc_calls[0]['params']['proNumber'], '87654321')
        names = self.env['ir.attachment'].search(
            [('res_model', '=', self.shipment._name), ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt 87654321.pdf', names)
        self.assertIn('Inspection certificate 87654321.pdf', names)

    def test_cancel_says_to_call_aaa_cooper(self):
        self.shipment.write({'state': 'booked', 'pickup_number': '12345'})
        self.assertFalse(self.carrier.ltl_can('cancel'))
        action = self.shipment.action_cancel()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertEqual(self.shipment.state, 'cancel')
        self.assertFalse(self.calls)

    def test_missing_token_and_test_button(self):
        self.answers['/sapi30/wsGenEst'] = FakeResponse(200, content=rate_answer())
        action = self.carrier.action_aact_test_connection()
        self.assertIn('1234567890', action['params']['message'])
        self.carrier.aact_token = False
        with self.assertRaisesRegex(UserError, 'API token'):
            self.carrier.ltl_rate(self.shipment)
        self.carrier.aact_environment = 'test'
        self.carrier.aact_token = 'tok'
        self.carrier.ltl_rate(self.shipment)
        self.assertTrue(self._calls_to('https://testapi2.aaacooper.com:8200/sapi30/wsGenEst'))
