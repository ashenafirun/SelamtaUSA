# -*- coding: utf-8 -*-
"""Saia connector tests with Saia's answers simulated (no network). Shapes follow Saia's rate
quote OpenAPI (Rate_Quote_Request / Rate_Quote_Response) and the Customer Imaging API examples."""
import base64
import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MODULE = 'odoo.addons.selamta_ltl_saia.models.delivery_carrier'
PDF = b'%PDF-1.4 saia test'


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


def rate_answer(**overrides):
    answer = {
        'status': 'SUCCESS', 'quoteNumber': 123456789, 'accountCode': '0712345',
        'effectiveDate': '2026-10-30', 'expirationDate': '2026-11-06', 'estimatedDeliveryDate': '2026-11-06',
        'standardServiceDays': 2, 'directPoint': 'Y',
        'discount': {'discountPercent': 90, 'discountAmount': 4500.00},
        'surcharge': {'fuelSurchargePercent': 35.5, 'fuelSurchargeAmount': 177.50,
                      'isFuelSurchargeApplicableOnGss': 'Y', 'fuelSurchargeAmountWithGss5': 190.0,
                      'fuelSurchargeAmountWithGss10': 0, 'fuelSurchargeAmountWithGss12': 200.0},
        'rateDetails': {'rateType': 'Class', 'totalInvoice': 742.50, 'isGssCompliant': True,
                        'totalInvoiceWithGss5': 792.50, 'totalInvoiceWithGss10': 0, 'totalInvoiceWithGss12': 842.50,
                        'gss5AccessorialCharge': 37.50, 'gss10AccessorialCharge': 0, 'gss12AccessorialCharge': 77.50,
                        'tariff': 'CZAR'},
        'deficitDetails': {'deficitWeight': 0, 'deficitRate': 0, 'deficitAmount': 0},
        'weight': {'actualWeight': 1801, 'ratedWeight': 1801, 'weightUnit': 'LBS'},
        'rateDetailItems': [{'class': '85', 'weight': 1801, 'rate': 277.62, 'amount': 5000.00}],
        'rateAccessorials': [{'code': 'LiftgateService', 'internalCode': 'LGDL',
                              'description': 'LIFTGATE SERVICE          1', 'amount': 65.00}],
        'terminals': {'originTerminal': {'id': 'ATL', 'name': 'Atlanta', 'cityDispatchPhone': '(404)555-0123'}},
        'origin': {'city': 'DECATUR', 'state': 'GA', 'zipcode': '30035'},
        'destination': {'city': 'CHARLOTTE', 'state': 'NC', 'zipcode': '28202'},
    }
    answer.update(overrides)
    return answer


@tagged('post_install', '-at_install')
class TestSaia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        ga = env['res.country.state'].search([('code', '=', 'GA'), ('country_id', '=', us.id)])
        nc = env['res.country.state'].search([('code', '=', 'NC'), ('country_id', '=', us.id)])
        env.company.partner_id.write({
            'street': '5335 Dividend Dr Suite C', 'city': 'Decatur', 'zip': '30035',
            'state_id': ga.id, 'country_id': us.id, 'phone': '404-555-0100'})
        cls.consignee = env['res.partner'].create({
            'name': 'Sample Market', 'is_company': True, 'street': '100 Example Ave',
            'city': 'Charlotte', 'zip': '28202', 'state_id': nc.id, 'country_id': us.id})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.carrier = env['delivery.carrier'].create({
            'name': 'Saia', 'product_id': product.id, 'delivery_type': 'saia', 'ltl_enabled': True,
            'ltl_scac': 'SAIA', 'ltl_match_on': 'manual',
            'saia_username': 'selamtatest', 'saia_password': 'pw-secret-1',
            'saia_rq_key': 'rq-key-1', 'saia_tracking_key': 'tr-key-1', 'saia_imaging_key': 'ca-key-1',
        })
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
                if url.split('?')[0].endswith(key):
                    answer = self.answers[key]
                    return answer() if callable(answer) else answer
            return FakeResponse(404, {'statusCode': 404, 'message': 'Resource not found'})

        patcher = patch(MODULE + '.requests.request', side_effect=fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calls_to(self, part):
        return [c for c in self.calls if c['url'].endswith(part)]

    def test_rate_request_and_answer(self):
        self.answers['/ratequote/customer-api'] = FakeResponse(200, rate_answer())
        rates = self.carrier.ltl_rate(self.shipment)
        call = self._calls_to('/ratequote/customer-api')[0]
        self.assertEqual(call['url'], 'https://api.saia.com/rate-quote/webservice/ratequote/customer-api')
        self.assertEqual(call['headers']['RQ-Key'], 'rq-key-1')
        body = call['json']
        self.assertEqual((body['userID'], body['password'], body['payer']), ('selamtatest', 'pw-secret-1', 'Shipper'))
        self.assertEqual(body['origin'], {'city': 'DECATUR', 'state': 'GA', 'zipcode': '30035'})
        self.assertEqual(body['destination'], {'city': 'CHARLOTTE', 'state': 'NC', 'zipcode': '28202'})
        cls = float(self.shipment.unit_ids.freight_class)
        self.assertEqual(body['details'], [{'weight': 1801, 'class': int(cls) if cls == int(cls) else cls, 'units': 2,
                                            'length': 48, 'width': 40, 'height': 60}])
        self.assertEqual(body['accessorials'], {'code': ['LiftgateService']})
        self.assertEqual(len(rates), 1)
        rate = rates[0]
        self.assertEqual((rate['total'], rate['transit_days'], rate['quote_number'], rate['expires']),
                         (742.5, 2, '123456789', '2026-11-06'))
        self.assertEqual(rate['saia_terminal'], 'Atlanta ((404)555-0123)')
        self.assertEqual([(c['code'], c['amount']) for c in rate['charges']], [
            ('LINEHAUL', 5000.0), ('DISC', -4500.0), ('LGDL', 65.0), ('FUEL', 177.5)])
        self.assertEqual([c['name'] for c in rate['charges']], [
            'Linehaul before discount, class 85, 1801 lb', 'Discount (90%)', 'Liftgate service',
            'Fuel surcharge (35.5%)'])
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 742.5, places=2)

    def test_real_answer_decatur_to_alexandria(self):
        """Saia's answer on 30 Oct 2026 (Decatur GA -> Alexandria VA, 2 pallets, 1,600 lb, class 85,
        liftgate): accessorials come wrapped in {"accessorials": [...]}, with amounts in the text."""
        self.answers['/ratequote/customer-api'] = FakeResponse(200, rate_answer(
            quoteNumber=764491873, accountCode='1055993', expirationDate='2026-11-04', standardServiceDays=2,
            discount={'discountPercent': 95, 'discountAmount': 3945.92},
            surcharge={'fuelSurchargePercent': 58.12, 'fuelSurchargeAmount': 202.65,
                       'isFuelSurchargeApplicableOnGss': 'Y', 'fuelSurchargeAmountWithGss5': 240.43,
                       'fuelSurchargeAmountWithGss10': 324.7, 'fuelSurchargeAmountWithGss12': 312.21},
            rateDetails={'rateType': 'Class', 'totalInvoice': 603.33, 'isGssCompliant': True,
                         'totalInvoiceWithGss5': 706.11, 'totalInvoiceWithGss10': 935.38,
                         'totalInvoiceWithGss12': 901.39, 'gss5AccessorialCharge': 65,
                         'gss10AccessorialCharge': 210, 'gss12AccessorialCharge': 188.5, 'tariff': 'SAIA5700'},
            rateDetailItems=[{'class': '85', 'weight': 1600, 'rate': 259.6, 'amount': 4153.6}],
            rateAccessorials={'accessorials': [
                {'code': 'liftgateservice', 'internalCode': 'LGATE',
                 'description': 'LIFTGATE DELV/HAND UNLOAD   575', 'amount': 52},
                {'description': 'VIRGINIA HIGH COST CHARGE       700', 'internalCode': 'VAARB', 'amount': 141}]}))
        rate = self.carrier.ltl_rate(self.shipment)[0]
        self.assertEqual((rate['total'], rate['quote_number'], rate['transit_days']), (603.33, '764491873', 2))
        self.assertEqual([(c['code'], c['name'], c['amount']) for c in rate['charges']], [
            ('LINEHAUL', 'Linehaul before discount, class 85, 1600 lb', 4153.6),
            ('DISC', 'Discount (95%)', -3945.92),
            ('LGATE', 'Liftgate delv/hand unload', 52.0),
            ('VAARB', 'Virginia high cost charge', 141.0),
            ('FUEL', 'Fuel surcharge (58.12%)', 202.65)])
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 603.33, places=2)
        # Guaranteed by noon: same lines, GSS fuel and the guaranteed charge, adding up to Saia's total.
        self.carrier.saia_show_guaranteed = True
        noon = self.carrier.ltl_rate(self.shipment)[1]
        self.assertEqual((noon['saia_service'], noon['total']), ('GSS12', 901.39))
        self.assertAlmostEqual(sum(c['amount'] for c in noon['charges']), 901.39, places=2)
        self.assertNotIn('OTHER', [c['code'] for c in noon['charges']])

    def test_guaranteed_and_account(self):
        self.carrier.write({'saia_show_guaranteed': True, 'saia_account_code': '0712345'})
        self.answers['/ratequote/customer-api'] = FakeResponse(200, rate_answer())
        rates = self.carrier.ltl_rate(self.shipment)
        self.assertEqual(self._calls_to('/ratequote/customer-api')[0]['json']['origin']['accountCode'], '0712345')
        self.assertEqual([(r['saia_service'], r['total']) for r in rates],
                         [('STD', 742.5), ('GSS12', 842.5), ('GSS5', 792.5)])
        noon = rates[1]
        self.assertIn(('GSS12', 77.5), [(c['code'], c['amount']) for c in noon['charges']])
        self.assertAlmostEqual(sum(c['amount'] for c in noon['charges']), 842.5, places=2)

    def test_errors_hide_secrets(self):
        self.answers['/ratequote/customer-api'] = FakeResponse(400, {
            'status': 'FAIL', 'fault': 'C', 'errors': [{'password': {
                'codes': [400], 'message': 'Invalid Password pw-secret-1', 'value': {'password': '*****'}}}]})
        with self.assertRaisesRegex(UserError, r'Invalid Password \*\*\* \(password\)') as caught:
            self.carrier.ltl_rate(self.shipment)
        self.assertNotIn('pw-secret-1', str(caught.exception))
        self.answers['/ratequote/customer-api'] = FakeResponse(401, {
            'statusCode': 401, 'message': 'Access denied due to missing subscription key.'})
        with self.assertRaisesRegex(UserError, 'Saia refused the key or login'):
            self.carrier.ltl_rate(self.shipment)
        self.carrier.saia_rq_key = False
        with self.assertRaisesRegex(UserError, 'Enter the Saia Rate Quote key'):
            self.carrier.ltl_rate(self.shipment)

    def test_booking_is_on_saia_com(self):
        self.assertFalse(self.carrier.ltl_can('book'))
        self.assertTrue(self.carrier.ltl_can('rate'))
        self.assertTrue(self.carrier.ltl_can('track'))

    def test_tracking_and_documents(self):
        self.shipment.write({'state': 'booked', 'pro_number': '1073050082'})
        self.answers['/track/pro-numbers/01073050082'] = FakeResponse(200, {
            'proNumber': '01073050082', 'shipmentStatus': 'In Transit', 'pickupDate': '2026-11-02',
            'estimatedDeliveryDate': '2026-11-04', 'history': [{'description': 'Picked up', 'date': '2026-11-02'}]})
        self.shipment._ltl_update_tracking()
        call = self._calls_to('/track/pro-numbers/01073050082')[0]
        self.assertEqual(call['headers']['Ocp-Apim-Subscription-Key'], 'tr-key-1')
        self.assertEqual(call['headers']['Api-Version'], 'V1')
        self.assertEqual(call['auth'], ('selamtatest', 'pw-secret-1'))
        self.assertEqual(self.shipment.state, 'in_transit')
        self.assertEqual(self.shipment.tracking_status, 'In Transit, estimated delivery 11/04/2026')

        self.answers['/track/pro-numbers/01073050082'] = FakeResponse(200, {'data': [{
            'proNumber': '01073050082', 'currentStatus': 'Delivered', 'deliveryDate': '2026-11-04T10:50:32Z',
            'signature': 'J SMITH'}]})
        pdf = base64.b64encode(PDF).decode()
        self.answers['/imaging/api/v1/getImages'] = FakeResponse(200, {
            'proNumber': '01073050082', 'documentTypesRequested': 'DR,WC,IV', 'returnCode': 'OK',
            'imageInfo': [
                {'status': 'SUCCESS', 'pageNumber': 1, 'imageFormat': 'pdf', 'docType': 'DR', 'base64': pdf},
                {'status': 'NOT_FOUND', 'pageNumber': 0, 'imageFormat': 'pdf', 'docType': 'WC', 'base64': ''},
                {'status': 'SUCCESS', 'pageNumber': 1, 'imageFormat': 'pdf', 'docType': 'IV', 'base64': pdf}]})
        self.shipment._ltl_update_tracking()
        self.assertEqual(self.shipment.state, 'delivered')
        self.assertEqual(str(self.shipment.delivered_date), '2026-11-04')
        self.assertEqual(self.shipment.tracking_status, 'Delivered, signed by J SMITH')
        images = self._calls_to('/imaging/api/v1/getImages')[0]
        self.assertEqual(images['headers']['CA-Key'], 'ca-key-1')
        self.assertEqual(images['params'], {'pro': '01073050082', 'formatType': 'pdf', 'documentFilter': 'DR,WC,IV'})
        names = self.env['ir.attachment'].search([('res_model', '=', self.shipment._name),
                                                  ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt 01073050082.pdf', names)
        self.assertIn('Saia invoice 01073050082.pdf', names)
        self.assertNotIn('Weight certificate 01073050082.pdf', names)

    def test_raw_answer_and_test_button(self):
        self.answers['/ratequote/customer-api'] = FakeResponse(200, rate_answer())
        raw = json.loads(self.carrier.saia_raw_answer('rate', self.shipment.id))
        self.assertEqual(raw['request']['password'], '***')
        self.assertNotIn('pw-secret-1', json.dumps(raw))
        action = self.carrier.action_saia_test_connection()
        self.assertIn('account 0712345', action['params']['message'])
