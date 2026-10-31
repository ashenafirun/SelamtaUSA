# -*- coding: utf-8 -*-
"""Southeastern connector tests with SEFL's answers simulated (no network). Shapes follow SEFL's
Web Connect examples (RESTful rate quote, tracing JSON, document retrieval)."""
import base64
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.selamta_ltl_sefl.models.delivery_carrier'
PDF = b'%PDF-1.4 sefl test'


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


def quote_detail(status='RAT', total='667.26', details=None):
    details = details if details is not None else [
        {'ratingClass': '  85', 'description': 'Teff flour', 'charges': '2511.81', 'weight': '1801',
         'typeCharge': '     P', 'rate': '139.47'},
        {'ratingClass': '    ', 'description': 'GROSS FRT CHG', 'charges': '2511.81', 'weight': '',
         'typeCharge': '   GFC', 'rate': '       '},
        {'ratingClass': '    ', 'description': '78.00% DISCOUNT', 'charges': '1959.21', 'weight': '',
         'typeCharge': ' D7800', 'rate': '       '},
        {'ratingClass': '    ', 'description': 'NET FRT CHG', 'charges': '552.60', 'weight': '',
         'typeCharge': '   NFC', 'rate': '       '},
        {'ratingClass': '    ', 'description': 'LTL FUEL SURCHARGE OF  20.75%', 'charges': '114.66', 'weight': '',
         'typeCharge': '    FS', 'rate': '       '},
        {'ratingClass': '    ', 'description': '', 'charges': total, 'weight': '1801',
         'typeCharge': '   TTL', 'rate': '       '},
    ]
    return {'discountAmount': '1959.21', 'custAccount': '001184274', 'transitTime': '2', 'errorMessage': '',
            'quoteNumber': 'CXQKNF157', 'errorOccured': 'false', 'rateQuote': total, 'details': details,
            'status': status, 'quoteType': 'TC', 'quoteDIP': 'D', 'httpStatusCode': '200',
            'discountPercent': '78.00% '}


@tagged('post_install', '-at_install')
class TestSefl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        ga = env['res.country.state'].search([('code', '=', 'GA'), ('country_id', '=', us.id)])
        nc = env['res.country.state'].search([('code', '=', 'NC'), ('country_id', '=', us.id)])
        env.company.partner_id.write({
            'name': 'Selamta Test LLC', 'street': '5335 Dividend Dr Suite C', 'city': 'Decatur', 'zip': '30035',
            'state_id': ga.id, 'country_id': us.id})
        cls.consignee = env['res.partner'].create({
            'name': 'Sample Market', 'is_company': True, 'street': '100 Example Ave',
            'city': 'Charlotte', 'zip': '28202', 'state_id': nc.id, 'country_id': us.id})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.carrier = env['delivery.carrier'].create({
            'name': 'Southeastern Freight Lines', 'product_id': product.id, 'delivery_type': 'sefl',
            'ltl_enabled': True, 'ltl_scac': 'SEFL', 'ltl_match_on': 'manual',
            'sefl_username': 'selamtatest', 'sefl_password': 'pw-secret-1', 'sefl_account': '001184274'})
        cls.shipment = env['selamta.ltl.shipment'].create({
            'partner_id': cls.consignee.id, 'carrier_id': cls.carrier.id,
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
            for key in sorted(self.answers, key=len, reverse=True):
                if url.endswith(key):
                    answer = self.answers[key]
                    return answer() if callable(answer) else answer
            return FakeResponse(404, None, text='Not found')

        for target, side_effect in (('.requests.request', fake_request), ('.time.sleep', lambda s: None)):
            patcher = patch(MODULE + target, side_effect=side_effect)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _calls_to(self, part):
        return [c for c in self.calls if c['url'].endswith(part)]

    def _answer_quote(self, *details):
        self.answers['/rest/submitQuote'] = FakeResponse(200, {
            'errorMessage': '', 'quoteNumber': 'CXQKNF157', 'errorOccured': 'false',
            'location': 'https://www.sefl.com/webconnect/ratequotes/rest/CXQKNF157'})
        answers = iter(details or [quote_detail()])
        self.answers['/rest/CXQKNF157'] = lambda: FakeResponse(200, next(answers))

    def test_rate_form_and_answer(self):
        self._answer_quote()
        rates = self.carrier.ltl_rate(self.shipment)
        submit = self._calls_to('/rest/submitQuote')[0]
        self.assertEqual((submit['method'], submit['auth']), ('POST', ('selamtatest', 'pw-secret-1')))
        form = submit['data']
        day = max(self.shipment.ship_date, fields.Date.context_today(self.carrier))
        self.assertEqual({k: form[k] for k in ('CustomerAccount', 'CustomerName', 'CustomerZip', 'Option', 'Terms',
                                               'OriginCity', 'OriginZip', 'DestinationCity', 'DestinationZip',
                                               'OrigCountry', 'PickupDateMM', 'PickupDateYYYY')},
                         {'CustomerAccount': '001184274', 'CustomerName': 'Selamta Test LLC', 'CustomerZip': '30035',
                          'Option': 'S', 'Terms': 'P', 'OriginCity': 'DECATUR', 'OriginZip': '30035',
                          'DestinationCity': 'CHARLOTTE', 'DestinationZip': '28202', 'OrigCountry': 'U',
                          'PickupDateMM': day.strftime('%m'), 'PickupDateYYYY': day.strftime('%Y')})
        self.assertEqual((form['Class1'], form['Weight1'], form['Pieces1']),
                         (self.carrier._sefl_class(self.shipment.unit_ids.freight_class), '1801', '2'))
        self.assertEqual(form['chkLGD'], 'on')
        self.assertNotIn('DimsOption', form)
        detail = self._calls_to('/rest/CXQKNF157')[0]
        self.assertEqual(detail['params'], {'ReturnDetail': 'Y'})
        rate = rates[0]
        self.assertEqual((rate['total'], rate['transit_days'], rate['quote_number']), (667.26, 2, 'CXQKNF157'))
        self.assertEqual([(c['code'], c['amount']) for c in rate['charges']], [
            ('LINEHAUL', 2511.81), ('DISC', -1959.21), ('FUEL', 114.66)])
        self.assertEqual(rate['charges'][1]['name'], '78.00% discount')
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 667.26, places=2)

    def test_queued_quote_hand_rating_and_errors(self):
        self._answer_quote(quote_detail(status='ENT', total='0'), quote_detail())
        self.assertEqual(self.carrier.ltl_rate(self.shipment)[0]['total'], 667.26)
        self.assertEqual(len(self._calls_to('/rest/CXQKNF157')), 2)
        self._answer_quote(quote_detail(status='UTR', total='0'))
        with self.assertRaisesRegex(UserError, 'rate quote CXQKNF157 by hand'):
            self.carrier.ltl_rate(self.shipment)
        self.answers['/rest/submitQuote'] = FakeResponse(200, {
            'errorOccured': 'true', 'errorMessage': 'Invalid destination zip code'})
        with self.assertRaisesRegex(UserError, 'Invalid destination zip code'):
            self.carrier.ltl_rate(self.shipment)
        self.answers['/rest/submitQuote'] = FakeResponse(401, None, text='')
        with self.assertRaisesRegex(UserError, 'refused the MySEFL login'):
            self.carrier.ltl_rate(self.shipment)
        self.carrier.sefl_password = False
        with self.assertRaisesRegex(UserError, 'Enter the MySEFL username and password'):
            self.carrier.ltl_rate(self.shipment)

    def test_minimum_charge_and_dimensions(self):
        self.carrier.sefl_send_dimensions = True
        self._answer_quote(quote_detail(total='487.10', details=[
            {'typeCharge': '     P', 'description': 'Teff flour', 'charges': '410.00', 'ratingClass': ' 85',
             'weight': '300'},
            {'typeCharge': '   GFC', 'description': 'GROSS FRT CHG', 'charges': '410.00'},
            {'typeCharge': ' D7800', 'description': '78.00% DISCOUNT', 'charges': '319.80'},
            {'typeCharge': '   MFC', 'description': 'MIN FRT CHG', 'charges': '374.00'},
            {'typeCharge': '   LGD', 'description': 'LIFTGATE DELIVERY', 'charges': '56.82'},
            {'typeCharge': '    FS', 'description': 'LTL FUEL SURCHARGE OF  15.18%', 'charges': '56.28'},
            {'typeCharge': '   TTL', 'description': '', 'charges': '487.10'}]))
        rate = self.carrier.ltl_rate(self.shipment)[0]
        self.assertEqual([c['code'] for c in rate['charges']], ['MFC', 'LGD', 'FUEL'])
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 487.10, places=2)
        form = self._calls_to('/rest/submitQuote')[0]['data']
        self.assertEqual((form['DimsOption'], form['PieceLength1'], form['UnitOfMeasure1'], form['NumberOfUnits1']),
                         ('I', '48', 'I', '2'))

    def test_class_codes_and_booking_off(self):
        self.assertEqual(self.carrier._sefl_class('77.5'), '775')
        self.assertEqual(self.carrier._sefl_class('92.5'), '925')
        self.assertEqual(self.carrier._sefl_class('85'), '85')
        self.assertFalse(self.carrier.ltl_can('book'))
        self.assertTrue(self.carrier.ltl_can('rate'))

    def test_tracking_and_documents(self):
        self.shipment.write({'state': 'booked', 'pro_number': 'RIC-0123456789'})
        self.answers['/webconnect/tracing'] = FakeResponse(200, {'pro': [{
            'proNumber': '123456789', 'pickupDate': '11/02/2026', 'location': 'At RALEIGH service center',
            'currentStatusCode': 'LOD', 'currentStatusDescription': 'Loaded on trailer'}]})
        self.shipment._ltl_update_tracking()
        call = self._calls_to('/webconnect/tracing')[0]
        self.assertEqual(call['params'], [('Type', 'PN'), ('RefNum1', '123456789'), ('output', 'JSON')])
        self.assertNotIn('auth', call)  # the password never goes into the tracing address
        self.assertEqual(self.shipment.state, 'in_transit')
        self.assertEqual(self.shipment.tracking_status, 'Loaded on trailer, At RALEIGH service center')

        self.answers['/webconnect/tracing'] = FakeResponse(200, {'pro': [{
            'proNumber': '123456789', 'pickupDate': '11/02/2026', 'currentStatusCode': 'DLV',
            'currentStatusDescription': 'Delivered', 'currentStatusDateOnly': '11/04/2026'}]})
        pdf = base64.b64encode(PDF).decode()
        self.answers['/document-retrieval/'] = FakeResponse(200, [
            {'pro': '123456789', 'type': 'Delivery Receipt', 'fileExt': 'pdf', 'base64Image': pdf, 'error': ''},
            {'pro': '123456789', 'type': '', 'fileExt': '', 'base64Image': '', 'error': 'No W&I found'}])
        self.shipment._ltl_update_tracking()
        self.assertEqual(self.shipment.state, 'delivered')
        self.assertEqual(str(self.shipment.delivered_date), '2026-11-04')
        docs = self._calls_to('/document-retrieval/')[0]
        self.assertEqual(docs['json'], {'pros': ['123456789'], 'associated': False,
                                        'imageTypes': ['DR', 'WI', 'FB'], 'format': 'pdf'})
        self.assertEqual(docs['auth'], ('selamtatest', 'pw-secret-1'))
        names = self.env['ir.attachment'].search([('res_model', '=', self.shipment._name),
                                                  ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt 123456789.pdf', names)
