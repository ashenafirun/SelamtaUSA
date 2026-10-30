# -*- coding: utf-8 -*-
"""R+L connector tests with R+L's answers simulated (no network). The JSON answers follow
recorded R+L API exchanges (RateQuote, BillOfLading, PrintBOL, PickupRequest,
DocumentRetrieval) and the field tables of R+L's API documentation (ShipmentTracing)."""
import base64
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.selamta_ltl_rlcarriers.models.delivery_carrier'
PDF = b'%PDF-1.4 r+l test'


class FakeResponse:
    def __init__(self, status, data=None, text=None):
        self.status_code = status
        self._data = data
        self.text = text if text is not None else (json.dumps(data) if data is not None else '')
        self.content = self.text.encode()

    def json(self):
        if self._data is None:
            raise ValueError('no json')
        return self._data


def rate_answer(net='436.71', gross='1,852.92', discount='1,487.83', charges=None, guaranteed=True):
    charges = charges if charges is not None else [
        {'Type': '', 'Title': 'Class: 85', 'Weight': '1800', 'Rate': '$95.21', 'Amount': '$1,713.78'},
    ]
    levels = [{'QuoteNumber': '6898769', 'ServiceDays': 3, 'Charge': '$%s' % gross, 'NetCharge': '$%s' % net,
               'HourlyWindow': None, 'Name': 'Standard Service', 'Code': 'STD'}]
    if guaranteed:
        levels.append({'QuoteNumber': '29098816', 'ServiceDays': 3, 'Charge': '$51.30', 'NetCharge': '$488.01',
                       'HourlyWindow': None, 'Name': 'Guaranteed Service', 'Code': 'GSDS'})
    return {
        'RateQuote': {
            'Origin': {'City': 'DECATUR', 'StateOrProvince': 'GA', 'ZipOrPostalCode': '30035', 'CountryCode': 'USA'},
            'Destination': {'City': 'CHARLOTTE', 'StateOrProvince': 'NC', 'ZipOrPostalCode': '28202',
                            'CountryCode': 'USA'},
            'OriginServiceCenter': {'ZipCode': '30336', 'City': 'ATLANTA', 'State': 'GA', 'Code': 'ATL',
                                    'Location': 'Atlanta, GA', 'Phone': '1-800-555-0101'},
            'CustomerDiscounts': '$%s' % discount,
            'Charges': charges,
            'Ocean': None,
            'CategorizedMessages': {'GeneralMessages': [], 'TransitMessages': [], 'RatesMessages': []},
            'ServiceLevels': levels,
        },
        'Code': 200, 'Errors': [], 'Messages': [],
    }


@tagged('post_install', '-at_install')
class TestRlCarriers(TransactionCase):

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
        cls.vendor = env['res.partner'].create({'name': 'R+L Carriers', 'is_company': True})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.carrier = env['delivery.carrier'].create({
            'name': 'R+L Carriers', 'product_id': product.id, 'delivery_type': 'rlcarriers',
            'ltl_enabled': True, 'ltl_vendor_id': cls.vendor.id, 'ltl_scac': 'RLCA', 'ltl_match_on': 'manual',
            'rlc_api_key': 'key-123', 'rlc_contact_name': 'Dock',
        })
        cls.shipment = env['selamta.ltl.shipment'].create({
            'partner_id': cls.consignee.id,
            'carrier_id': cls.carrier.id,
            'ship_date': fields.Date.context_today(env['selamta.ltl.shipment']) + timedelta(days=2),
            'accessorial_ids': [(6, 0, [env.ref('selamta_ltl.accessorial_liftgate_delivery').id])],
            'unit_ids': [(0, 0, {'quantity': 2, 'unit_type': 'pallet', 'description': 'Teff flour',
                                 'length': 48, 'width': 40, 'height': 60, 'weight': 1801})],
        })

    def setUp(self):
        super().setUp()
        self.calls = []
        self.answers = {}

        def fake_request(method, url, **kwargs):
            self.calls.append(dict(kwargs, method=method, url=url))
            for key in sorted(self.answers, key=len, reverse=True):  # most specific path first
                if url.endswith(key):
                    answer = self.answers[key]
                    return answer() if callable(answer) else answer
            return FakeResponse(404, {'Code': 404, 'Errors': [{'ErrorMessage': 'Not found'}], 'Messages': []})

        patcher = patch(MODULE + '.requests.request', side_effect=fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calls_to(self, part):
        return [c for c in self.calls if c['url'].endswith(part)]

    def test_rate_request_and_answer(self):
        self.answers['/RateQuote'] = FakeResponse(200, rate_answer())
        rates = self.carrier.ltl_rate(self.shipment)
        call = self._calls_to('/RateQuote')[0]
        self.assertEqual((call['method'], call['url']), ('POST', 'https://api.rlc.com/RateQuote'))
        self.assertEqual(call['headers']['apiKey'], 'key-123')
        quote = call['json']['RateQuote']
        self.assertEqual(quote['PickupDate'], self.shipment.ship_date.strftime('%m/%d/%Y'))
        self.assertEqual(quote['Origin'], {'City': 'Decatur', 'StateOrProvince': 'GA',
                                           'ZipOrPostalCode': '30035', 'CountryCode': 'USA'})
        self.assertEqual(quote['Destination']['ZipOrPostalCode'], '28202')
        # Two pallets on one line become two items with their own weight and dimensions.
        self.assertEqual(quote['Items'], [
            {'Class': '85', 'Weight': 900, 'Length': 48.0, 'Width': 40.0, 'Height': 60.0},
            {'Class': '85', 'Weight': 901, 'Length': 48.0, 'Width': 40.0, 'Height': 60.0}])
        self.assertEqual(quote['AdditionalServices'], ['DestinationLiftgate'])
        # Standard service only by default.
        self.assertEqual(len(rates), 1)
        rate = rates[0]
        self.assertEqual((rate['total'], rate['transit_days'], rate['quote_number']), (436.71, 3, '6898769'))
        self.assertEqual(rate['service'], 'R+L Standard Service')
        self.assertEqual(rate['rlc_service_level'], 'Standard')
        self.assertEqual(rate['rlc_service_center'], 'Atlanta, GA (1-800-555-0101)')
        # Linehaul, gross adjustment to R+L's gross charge, discount, and fuel/other: adds up to the total.
        self.assertEqual([c['code'] for c in rate['charges']], ['LINEHAUL', 'MIN', 'DISC', 'OTHER'])
        self.assertEqual(rate['charges'][0]['amount'], 1713.78)
        self.assertEqual(rate['charges'][1]['amount'], 139.14)
        self.assertEqual(rate['charges'][2]['amount'], -1487.83)
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 436.71, places=2)

    def test_guaranteed_and_complete_charge_lines(self):
        self.carrier.rlc_show_guaranteed = True
        self.answers['/RateQuote'] = FakeResponse(200, rate_answer(net='300.00', charges=[
            {'Type': '', 'Title': 'Class: 85', 'Weight': '1800', 'Amount': '$1,000.00'},
            {'Type': 'DISC', 'Title': 'Discount', 'Amount': '-$800.00'},
            {'Type': 'FUEL', 'Title': 'Fuel Surcharge', 'Amount': '$35.00'},
            {'Type': 'LGATE', 'Title': 'Destination Liftgate', 'Amount': '$65.00'},
        ]))
        rates = self.carrier.ltl_rate(self.shipment)
        self.assertEqual([r['rlc_service_code'] for r in rates], ['STD', 'GSDS'])
        standard, guaranteed = rates
        self.assertEqual([c['name'] for c in standard['charges']],
                         ['Linehaul before discount, class: 85, 1800 lb', 'Discount', 'Fuel Surcharge',
                          'Destination Liftgate'])
        self.assertEqual((guaranteed['total'], guaranteed['rlc_service_level'], guaranteed['quote_number']),
                         (488.01, 'Guaranteed', '29098816'))
        self.assertAlmostEqual(sum(c['amount'] for c in guaranteed['charges']), 488.01, places=2)
        self.assertIn('Guaranteed Service', [c['name'] for c in guaranteed['charges']])

    def test_many_pallets_and_errors(self):
        self.shipment.unit_ids.quantity = 10  # more than 8 pieces: one item per line, no dimensions
        self.answers['/RateQuote'] = FakeResponse(200, rate_answer())
        self.carrier.ltl_rate(self.shipment)
        self.assertEqual(self._calls_to('/RateQuote')[0]['json']['RateQuote']['Items'],
                         [{'Class': '%g' % float(self.shipment.unit_ids.freight_class), 'Weight': 1801}])
        self.answers['/RateQuote'] = FakeResponse(400, {'RateQuote': None, 'Code': 400, 'Errors': [
            {'Property': 'request.RateQuote.Items', 'ErrorMessage': 'At least one Item is required',
             'ExceptionMessage': ''}], 'Messages': []})
        with self.assertRaisesRegex(UserError, r'At least one Item is required \(RateQuote.Items\)'):
            self.carrier.ltl_rate(self.shipment)
        self.answers['/RateQuote'] = FakeResponse(400, None, text='"Invalid API Key"')
        with self.assertRaisesRegex(UserError, 'refused the API key'):
            self.carrier.ltl_rate(self.shipment)
        self.carrier.rlc_api_key = False
        with self.assertRaisesRegex(UserError, 'Enter the R\\+L API key'):
            self.carrier.ltl_rate(self.shipment)

    def test_booking_off_by_default(self):
        self.assertFalse(self.carrier.ltl_can('book'))
        self.assertTrue(self.carrier.ltl_can('rate'))
        self.assertTrue(self.carrier.ltl_can('cancel'))

    def _book(self, **carrier_vals):
        self.carrier.write(dict({'rlc_book_shipments': True}, **carrier_vals))
        self.answers['/RateQuote'] = FakeResponse(200, rate_answer())
        self.answers['/BillOfLading'] = FakeResponse(200, {
            'ProNumber': '41388591', 'PickupRequestNumber': '74201384', 'Code': 0, 'Errors': [], 'Messages': []})
        self.answers['/BillOfLading/PrintBOL'] = FakeResponse(200, {
            'BolDocument': base64.b64encode(PDF).decode(), 'Code': 200, 'Errors': [], 'Messages': []})
        rate = self.carrier.ltl_rate(self.shipment)[0]
        self.shipment.write({'pickup_ready_time': 10.5, 'pickup_close_time': 16.0})
        self.shipment._apply_quote(rate, self.carrier, 'api')
        result = self.carrier.ltl_book(self.shipment, rate)
        self.shipment._apply_booking(result)
        return result

    def test_book_creates_bol_with_pickup(self):
        result = self._book()
        self.assertEqual((result['pro_number'], result['pickup_number']), ('41388591', '74201384'))
        call = self._calls_to('/BillOfLading')[0]
        self.assertEqual(call['url'], 'https://api.rlc.com/BillOfLading')
        request = call['json']
        bill = request['BillOfLading']
        self.assertTrue(request['GenerateUniversalPro'])
        self.assertEqual(bill['FreightChargePaymentMethod'], 'Prepaid')
        self.assertEqual(bill['ServiceLevel'], 'Standard')
        self.assertEqual(bill['Shipper']['CompanyName'], self.env.company.partner_id.name)
        self.assertEqual(bill['Shipper']['PhoneNumber'], '404-555-0100')
        self.assertEqual(bill['Consignee']['City'], 'Charlotte')
        self.assertEqual(bill['Consignee']['PhoneNumber'], '704-555-0199')
        self.assertEqual(bill['Items'], [{'Class': '85', 'Pieces': 2, 'Weight': 1801, 'PackageType': 'PLT',
                                          'Description': 'Teff flour', 'IsHazmat': False}])
        self.assertEqual(bill['AdditionalServices'], ['DestinationLiftgate'])
        self.assertEqual(bill['ReferenceNumbers'], {'ShipperNumber': self.shipment.bol_reference,
                                                    'RateQuoteNumber': '6898769'})
        self.assertIn('LIFT GATE', bill['SpecialInstructions'].upper().replace('LIFTGATE', 'LIFT GATE'))
        pickup = request['PickupRequest']['PickupInformation']
        self.assertEqual((pickup['ReadyTime'], pickup['CloseTime']), ('10:30 AM', '04:00 PM'))
        self.assertEqual(pickup['PickupDate'], self.shipment.ship_date.strftime('%m/%d/%Y'))
        self.assertEqual(pickup['LoadAttributes'], ['Food'])
        self.assertEqual(self.shipment.state, 'booked')
        self.assertEqual(self.shipment.pro_number, '41388591')
        self.assertEqual(self.shipment.rlc_service_center, 'Atlanta, GA (1-800-555-0101)')
        names = self.env['ir.attachment'].search([('res_model', '=', self.shipment._name),
                                                  ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('R+L BOL (carrier copy) 41388591.pdf', names)

    def test_book_without_pickup_in_sandbox(self):
        self._book(rlc_schedule_pickup=False, rlc_environment='sandbox', rlc_universal_pro=False)
        request = self._calls_to('/BillOfLading')[0]
        self.assertEqual(request['url'], 'https://apisandbox.rlc.com/BillOfLading')
        self.assertNotIn('PickupRequest', request['json'])
        self.assertFalse(request['json']['GenerateUniversalPro'])
        # Rates still come from production.
        self.assertEqual(self._calls_to('/RateQuote')[0]['url'], 'https://api.rlc.com/RateQuote')
        self.assertIn('SANDBOX', ' '.join(self.shipment.message_ids.mapped('body')))

    def test_book_error(self):
        self.carrier.rlc_book_shipments = True
        self.answers['/BillOfLading'] = FakeResponse(400, {
            'ProNumber': None, 'PickupRequestNumber': None, 'Code': 400,
            'Errors': [{'Property': 'request.BillOfLading.Items', 'ErrorMessage': 'There must be at least one item'}],
            'Messages': []})
        with self.assertRaisesRegex(UserError, 'There must be at least one item'):
            self.carrier.ltl_book(self.shipment, {'total': 1.0})

    def test_cancel_pickup(self):
        self._book()
        self.answers['/PickupRequest'] = FakeResponse(200, {'Code': 200, 'Errors': None, 'Messages': []})
        self.assertTrue(self.shipment.action_cancel())
        call = self._calls_to('/PickupRequest')[0]
        self.assertEqual(call['method'], 'DELETE')
        self.assertEqual(call['json']['PickupRequestId'], 74201384)
        self.assertEqual(self.shipment.state, 'cancel')

    def test_cancel_without_pickup_number_offers_odoo_only(self):
        self.shipment.write({'state': 'booked', 'pro_number': '41388599', 'pickup_number': False})
        with self.assertRaises(RedirectWarning):
            self.shipment.action_cancel()
        self.assertEqual(self.shipment.state, 'booked')

    def test_tracking_and_documents(self):
        self.shipment.write({'state': 'booked', 'pro_number': '41388591'})
        self.answers['/ShipmentTracing'] = FakeResponse(200, {
            'Shipments': [{'Shipment': {
                'ShipmentNumber': '41388591', 'ShortStatus': 'In Transit',
                'LongStatus': 'Departed ATLANTA, GA', 'EstimatedDelivery': '11/04/2026',
                'PickupDate': {'Date': '11/02/2026', 'Time': '14:05'}, 'DeliveryDate': {'Date': '', 'Time': ''},
                'StatusHistory': [{'Date': '11/02/2026', 'Description': 'Picked up'}]}}],
            'Code': 200, 'Errors': [], 'Messages': []})
        self.shipment._ltl_update_tracking()
        call = self._calls_to('/ShipmentTracing')[0]
        self.assertEqual(call['url'], 'https://api.rlc.com/ShipmentTracing')
        self.assertIn(('TraceNumbers', '41388591'), call['params'])
        self.assertIn(('TraceType', 'PRO'), call['params'])
        self.assertEqual(self.shipment.state, 'in_transit')
        self.assertEqual(self.shipment.tracking_status, 'Departed ATLANTA, GA, estimated delivery 11/04/2026')

        self.answers['/ShipmentTracing'] = FakeResponse(200, {
            'Shipments': [{'ShipmentNumber': '41388591', 'ShortStatus': 'Delivered',
                           'LongStatus': 'Delivered to consignee',
                           'DeliveryDate': {'Date': '11/04/2026', 'Time': '10:12'}}],
            'Code': 200, 'Errors': [], 'Messages': []})
        self.answers['/DocumentRetrieval/GetDocumentTypes'] = FakeResponse(200, {
            'DocumentTypes': ['BillOfLading', 'DeliveryReceipt', 'Invoice'], 'Code': 200, 'Errors': [], 'Messages': []})
        self.answers['/DocumentRetrieval'] = lambda: FakeResponse(200, {
            'Documents': [{'Name': '41388591-x.pdf', 'Data': base64.b64encode(PDF).decode(), 'Type': 'x'}],
            'Code': 200, 'Errors': [], 'Messages': []})
        self.shipment._ltl_update_tracking()
        self.assertEqual(self.shipment.state, 'delivered')
        self.assertEqual(str(self.shipment.delivered_date), '2026-11-04')
        requested = [c['params']['DocumentTypes'] for c in self._calls_to('/DocumentRetrieval')]
        self.assertEqual(requested, ['DeliveryReceipt', 'Invoice'])  # only the available ones we want
        names = self.env['ir.attachment'].search([('res_model', '=', self.shipment._name),
                                                  ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt 41388591.pdf', names)
        self.assertIn('R+L invoice 41388591.pdf', names)

    def test_money_and_time_helpers(self):
        carrier = self.carrier
        self.assertEqual(carrier._rlc_money('$1,852.92'), 1852.92)
        self.assertEqual(carrier._rlc_money('-$12.50'), -12.5)
        self.assertEqual(carrier._rlc_money('($12.50)'), -12.5)
        self.assertEqual(carrier._rlc_money(None), 0.0)
        self.assertEqual(carrier._rlc_time(8.0), '08:00 AM')
        self.assertEqual(carrier._rlc_time(12.25), '12:15 PM')
        self.assertEqual(carrier._rlc_time(16.0), '04:00 PM')
