# -*- coding: utf-8 -*-
"""XPO connector tests with XPO's answers simulated (no network). The JSON shapes follow the
samples in XPO's Rating, BOL, Pickup Request, Shipment Tracking and Imaging guides."""
import base64
import json
from datetime import date, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.selamta_ltl_xpo.models import delivery_carrier as xpo_module

MODULE = 'odoo.addons.selamta_ltl_xpo.models.delivery_carrier'
PDF = b'%PDF-1.4 xpo test'
HOST = 'https://api.xpo.com'


class FakeResponse:
    def __init__(self, status, data=None, text=None, content=None):
        self.status_code = status
        self._data = data
        self.text = text if text is not None else (json.dumps(data) if data is not None else '')
        self.content = content if content is not None else self.text.encode()

    def json(self):
        if self._data is None:
            raise ValueError('no json')
        return self._data


def token_answer(token='token-1'):
    return FakeResponse(200, {'access_token': token, 'refresh_token': 'r', 'token_type': 'Bearer',
                              'expires_in': 43200, 'scope': 'default'})


def rate_answer(total=541.01, discount=1423.66, commodity_charge=1840.3, accessorials=None, garnt=True,
                deficit=None):
    accessorials = accessorials if accessorials is not None else [
        {'accessorialCd': 'HMS', 'accessorialDesc': 'HOMELAND SECURITY FEE', 'chargeAmt': {'amt': 22.5}},
        {'accessorialCd': 'FSC', 'accessorialDesc': 'FUEL SURCHARGE', 'chargeAmt': {'amt': 101.87}},
    ]
    quote = {
        'confirmationNbr': '7133312345678893',
        'amcInd': False,
        'totAccessorialAmt': {'amt': 124.37},
        'totCharge': [{'amt': total, 'currencyCd': 'USD'}],
        'totDiscountAmt': {'amt': discount},
        'actlDiscountPct': 77.36,
        'shipmentInfo': {
            'accessorials': accessorials,
            'commodity': [{'pieceCnt': 2, 'grossWeight': {'weight': 1801}, 'nmfcClass': '85.0',
                           'charge': {'chargeAmt': {'amt': commodity_charge},
                                      'calcMethod': {'perUnitRate': 102.18}}}],
            'shipper': {'address': {'postalCd': '30035'}},
            'consignee': {'address': {'postalCd': '28202'}},
            'paymentTermCd': 'P',
            'totCommodityCharge': {'amt': commodity_charge},
        },
        'vspApplied': False,
    }
    if deficit:
        quote['deficitRatingInfo'] = {'nmfcClass': '85', 'deficitWght': {'weight': 199},
                                      'deficitAmt': {'amt': deficit}}
    return FakeResponse(201, {'code': '201', 'transactionTimestamp': 1526000000000, 'data': {
        'rateQuote': quote,
        'msgs': [],
        'transitTime': {'destStateCd': 'NC', 'destPostalCd': '28202', 'destSicCd': 'XCH',
                        'estdDlvrDate': 1794283200000, 'garntInd': garnt, 'origPostalCd': '30035',
                        'origStateCd': 'GA', 'origSicCd': 'XAT', 'transitDays': 2},
    }})


@tagged('post_install', '-at_install')
class TestXpo(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        ga = env['res.country.state'].search([('code', '=', 'GA'), ('country_id', '=', us.id)])
        nc = env['res.country.state'].search([('code', '=', 'NC'), ('country_id', '=', us.id)])
        env.company.partner_id.write({
            'street': '5335 Dividend Dr Suite C', 'city': 'Decatur', 'zip': '30035',
            'state_id': ga.id, 'country_id': us.id, 'phone': '+1 (404) 555-0100', 'email': 'ship@example.com',
            'tz': 'America/New_York'})
        cls.consignee = env['res.partner'].create({
            'name': 'Sample Market', 'is_company': True, 'street': '100 Example Ave',
            'city': 'Charlotte', 'zip': '28202', 'state_id': nc.id, 'country_id': us.id,
            'phone': '704-555-0199'})
        cls.vendor = env['res.partner'].create({'name': 'XPO', 'is_company': True})
        product = env['product.product'].create({'name': 'Freight', 'type': 'service'})
        cls.carrier = env['delivery.carrier'].create({
            'name': 'XPO', 'product_id': product.id, 'delivery_type': 'xpo',
            'ltl_enabled': True, 'ltl_vendor_id': cls.vendor.id, 'ltl_scac': 'CNWY', 'ltl_match_on': 'manual',
            'xpo_api_key': 'Basic a2V5OnNlY3JldA==', 'xpo_username': 'selamtatest', 'xpo_password': 'pw-1',
            'xpo_shipper_account': '700000001', 'xpo_billto_account': '800000002',
            'xpo_billto_code': 'TESTX991000', 'xpo_contact_name': 'Dock',
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
        xpo_module._TOKENS.clear()
        self.calls = []
        self.answers = {'/token': token_answer()}

        def fake_request(method, url, **kwargs):
            self.calls.append(dict(kwargs, method=method, url=url))
            for key in sorted(self.answers, key=len, reverse=True):  # most specific path first
                if url.endswith(key):
                    answer = self.answers[key]
                    return answer() if callable(answer) else answer
            return FakeResponse(404, {'code': '404', 'error': {'errorCode': 'NOTFOUND', 'message': 'Not found'}})

        patcher = patch(MODULE + '.requests.request', side_effect=fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calls_to(self, part):
        return [c for c in self.calls if c['url'].endswith(part)]

    def test_login_and_rate(self):
        self.answers['/rating/1.0/ratequotes'] = rate_answer()
        rates = self.carrier.ltl_rate(self.shipment)
        login = self._calls_to('/token')[0]
        self.assertEqual((login['method'], login['url']), ('POST', HOST + '/token'))
        self.assertEqual(login['headers']['Authorization'], 'Basic a2V5OnNlY3JldA==')  # "Basic " not doubled
        self.assertEqual(login['data'], {'grant_type': 'password', 'username': 'selamtatest', 'password': 'pw-1'})
        call = self._calls_to('/rating/1.0/ratequotes')[0]
        self.assertEqual((call['method'], call['url']), ('POST', HOST + '/rating/1.0/ratequotes'))
        self.assertEqual(call['headers']['Authorization'], 'Bearer token-1')
        info = call['json']['shipmentInfo']
        self.assertEqual(info['paymentTermCd'], 'P')
        self.assertEqual(info['shipper'], {'address': {'postalCd': '30035'}, 'acctInstId': '700000001'})
        self.assertEqual(info['consignee'], {'address': {'postalCd': '28202'}})
        self.assertEqual(info['bill2Party'], {'acctInstId': '800000002', 'acctMadCd': 'TESTX991000',
                                              'address': {'postalCd': '30035'}})
        self.assertEqual(info['commodity'], [{
            'pieceCnt': 2, 'packageCode': 'PLT', 'grossWeight': {'weight': 1801, 'weightUom': 'LBS'},
            'nmfcClass': '%g' % float(self.shipment.unit_ids.freight_class), 'hazmatInd': False,
            'dimensions': {'length': 48.0, 'width': 40.0, 'height': 60.0, 'dimensionsUom': 'INCH'}}])
        self.assertEqual(info['accessorials'], [{'accessorialCd': 'DLG'}])
        self.assertEqual(info['palletCnt'], 2)
        self.assertTrue(info['shipmentDate'].startswith(self.shipment.ship_date.isoformat() + 'T10:00:00.000-0'))
        # Standard service only by default.
        self.assertEqual(len(rates), 1)
        rate = rates[0]
        self.assertEqual((rate['total'], rate['transit_days'], rate['quote_number']), (541.01, 2, '7133312345678893'))
        self.assertEqual(rate['service'], 'XPO Standard')
        self.assertEqual(rate['xpo_terminal'], 'XAT')
        self.assertEqual([(c['code'], c['amount']) for c in rate['charges']], [
            ('LINEHAUL', 1840.3), ('DISC', -1423.66), ('HMS', 22.5), ('FSC', 101.87)])
        self.assertEqual([c['name'] for c in rate['charges']], [
            'Linehaul before discount, class 85, 1801 lb', 'Discount (77.36%)', 'Homeland security fee',
            'Fuel surcharge'])
        self.assertAlmostEqual(sum(c['amount'] for c in rate['charges']), 541.01, places=2)

    def test_token_reused_and_renewed(self):
        self.answers['/rating/1.0/ratequotes'] = rate_answer()
        self.carrier.ltl_rate(self.shipment)
        self.carrier.ltl_rate(self.shipment)
        self.assertEqual(len(self._calls_to('/token')), 1)  # one login for both quotes
        # XPO says the token expired: log in again once and repeat the call.
        answers = iter([FakeResponse(401, {'code': '401', 'error': {'message': 'Invalid token'}}), rate_answer()])
        self.answers['/rating/1.0/ratequotes'] = lambda: next(answers)
        self.answers['/token'] = token_answer('token-2')
        self.assertEqual(self.carrier.ltl_rate(self.shipment)[0]['total'], 541.01)
        self.assertEqual(len(self._calls_to('/token')), 2)
        self.assertEqual(self._calls_to('/rating/1.0/ratequotes')[-1]['headers']['Authorization'], 'Bearer token-2')

    def test_login_refused_and_missing_credentials(self):
        self.answers['/token'] = FakeResponse(400, {'error': 'invalid_grant',
                                                    'error_description': 'Authentication failed'})
        with self.assertRaisesRegex(UserError, 'XPO refused the login \\(Authentication failed\\)'):
            self.carrier.ltl_rate(self.shipment)
        self.carrier.xpo_password = False
        with self.assertRaisesRegex(UserError, 'Enter the XPO key, user ID and password'):
            self.carrier.ltl_rate(self.shipment)

    def test_rate_errors(self):
        self.answers['/rating/1.0/ratequotes'] = FakeResponse(400, {'code': '400', 'error': {
            'errorCode': 'VALEXCEPTION', 'message': 'Validation Errors found',
            'moreInfo': [{'message': 'Postal code is invalid', 'location': 'consignee.address.postalCd'}]}})
        with self.assertRaisesRegex(UserError, 'Postal code is invalid \\(consignee.address.postalCd\\)'):
            self.carrier.ltl_rate(self.shipment)

    def test_deficit_and_guaranteed(self):
        self.carrier.xpo_show_guaranteed = True
        standard = rate_answer(total=600.0, discount=1500.0, commodity_charge=1840.3, deficit=100.0,
                               accessorials=[{'accessorialCd': 'FSC', 'accessorialDesc': 'Fuel Surcharge',
                                              'chargeAmt': {'amt': 159.7}}])
        guaranteed = rate_answer(total=690.0, discount=1500.0, commodity_charge=1840.3, deficit=100.0,
                                 accessorials=[{'accessorialCd': 'FSC', 'accessorialDesc': 'Fuel Surcharge',
                                                'chargeAmt': {'amt': 159.7}},
                                               {'accessorialCd': 'GUR', 'accessorialDesc': 'Guaranteed',
                                                'chargeAmt': {'amt': 90.0}}])
        answers = iter([standard, guaranteed])
        self.answers['/rating/1.0/ratequotes'] = lambda: next(answers)
        rates = self.carrier.ltl_rate(self.shipment)
        self.assertEqual([r['xpo_service'] for r in rates], ['STD', 'GUR'])
        self.assertEqual([(c['code'], c['amount']) for c in rates[0]['charges']], [
            ('LINEHAUL', 1840.3), ('DEFICIT', 100.0), ('DISC', -1500.0), ('FSC', 159.7)])
        self.assertEqual((rates[1]['total'], rates[1]['service']), (690.0, 'XPO Guaranteed (G!)'))
        self.assertIn({'accessorialCd': 'GUR'},
                      self._calls_to('/rating/1.0/ratequotes')[1]['json']['shipmentInfo']['accessorials'])
        self.assertAlmostEqual(sum(c['amount'] for c in rates[1]['charges']), 690.0, places=2)

    def test_booking_off_by_default(self):
        self.assertFalse(self.carrier.ltl_can('book'))
        self.assertTrue(self.carrier.ltl_can('rate'))
        self.assertTrue(self.carrier.ltl_can('cancel'))
        self.assertTrue(self.carrier.ltl_can('track'))

    def _book(self, **carrier_vals):
        self.carrier.write(dict({'xpo_book_shipments': True}, **carrier_vals))
        self.answers['/rating/1.0/ratequotes'] = rate_answer()
        self.answers['/billoflading/1.0/billsoflading'] = FakeResponse(201, {
            'code': '201', 'transactionTimestamp': 1507669461137, 'data': {'bolInfo': {
                'bolInstId': '4659194715665', 'pkupTrmnlSic': 'XAT', 'pkupCallDate': 1794024000000,
                'pkupCallSeq': 7}}})
        self.answers['/billsoflading/4659194715665/requester'] = FakeResponse(200, {
            'code': '200', 'data': {'bol': {'bolInstId': '4659194715665', 'proNbr': '123456782'}}})
        self.answers['/billsoflading/4659194715665/pdf'] = FakeResponse(200, None, text='', content=PDF)
        rate = self.carrier.ltl_rate(self.shipment)[0]
        self.shipment.write({'pickup_ready_time': 10.5, 'pickup_close_time': 16.0})
        self.shipment._apply_quote(rate, self.carrier, 'api')
        result = self.carrier.ltl_book(self.shipment, rate)
        self.shipment._apply_booking(result)
        return result

    def test_book_creates_bol_with_pickup(self):
        result = self._book()
        self.assertEqual(result['pro_number'], '123456782')
        self.assertTrue(result['pickup_number'].startswith('XAT-7'))
        call = self._calls_to('/billoflading/1.0/billsoflading')[0]
        self.assertEqual(call['url'], HOST + '/billoflading/1.0/billsoflading')
        self.assertIn(('testMode', 'N'), call['params'])
        request = call['json']
        self.assertTrue(request['autoAssignPro'])
        bol = request['bol']
        self.assertEqual(bol['requester'], {'role': 'S'})
        self.assertEqual(bol['chargeToCd'], 'P')
        self.assertEqual(bol['shipper']['acctInstId'], '700000001')
        self.assertEqual(bol['shipper']['address'], {
            'addressLine1': '5335 Dividend Dr Suite C', 'cityName': 'Decatur', 'stateCd': 'GA',
            'countryCd': 'US', 'postalCd': '30035'})
        self.assertEqual(bol['shipper']['contactInfo']['phone'], {'phoneNbr': '404-5550100'})
        self.assertEqual(bol['shipper']['contactInfo']['fullName'], 'Dock')
        self.assertEqual(bol['consignee']['address']['cityName'], 'Charlotte')
        self.assertEqual(bol['consignee']['contactInfo']['phone'], {'phoneNbr': '704-5550199'})
        self.assertEqual(bol['billToCust']['acctInstId'], '800000002')
        self.assertEqual(bol['commodityLine'], [{
            'pieceCnt': 2, 'packaging': {'packageCd': 'PLT'}, 'grossWeight': {'weight': 1801},
            'desc': 'Teff flour', 'nmfcClass': '%g' % float(self.shipment.unit_ids.freight_class),
            'hazmatInd': False}])
        self.assertEqual(bol['additionalService'], [{'accsrlCode': 'DLG', 'prepaidOrCollect': 'P'}])
        self.assertEqual(bol['suppRef'], {'shippersRefNbr': self.shipment.bol_reference})
        self.assertIn('XPO quote 7133312345678893', bol['remarks'])
        pickup = bol['pickupInfo']
        day = self.shipment.ship_date.isoformat()
        self.assertTrue(pickup['pkupTime'].startswith(day + 'T10:30:00-0'))
        self.assertTrue(pickup['dockCloseTime'].startswith(day + 'T16:00:00-0'))
        self.assertEqual(pickup['contact']['phone'], {'phoneNbr': '404-5550100'})
        self.assertEqual(self.shipment.state, 'booked')
        self.assertEqual(self.shipment.pro_number, '123456782')
        self.assertEqual((self.shipment.xpo_bol_inst_id, self.shipment.xpo_terminal), ('4659194715665', 'XAT'))
        self.assertFalse(self.shipment.xpo_test_booking)
        names = self.env['ir.attachment'].search([('res_model', '=', self.shipment._name),
                                                  ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('XPO BOL (carrier copy) 123456782.pdf', names)

    def test_book_in_test_mode_without_pickup(self):
        self._book(xpo_environment='test', xpo_schedule_pickup=False)
        call = self._calls_to('/billoflading/1.0/billsoflading')[0]
        self.assertIn(('testMode', 'Y'), call['params'])
        self.assertNotIn('pickupInfo', call['json']['bol'])
        self.assertTrue(self.shipment.xpo_test_booking)
        self.assertIn('TEST MODE', ' '.join(self.shipment.message_ids.mapped('body')))

    def test_book_error(self):
        self.carrier.xpo_book_shipments = True
        self.answers['/billoflading/1.0/billsoflading'] = FakeResponse(400, {'code': '400', 'error': {
            'errorCode': 'VALEXCEPTION', 'message': 'Validation Errors found',
            'moreInfo': [{'message': 'Consignee phone is required', 'location': 'bol.consignee'}]}})
        with self.assertRaisesRegex(UserError, 'Consignee phone is required'):
            self.carrier.ltl_book(self.shipment, {'total': 1.0})

    def test_cancel(self):
        self._book()
        self.answers['/billsoflading/4659194715665/cancel'] = FakeResponse(200, {'code': '200', 'data': {}})
        self.assertTrue(self.shipment.action_cancel())
        call = self._calls_to('/billsoflading/4659194715665/cancel')[0]
        self.assertEqual(call['method'], 'PUT')
        self.assertIn(('testMode', 'N'), call['params'])
        self.assertEqual(self.shipment.state, 'cancel')

    def test_cancel_pickup_typed_by_hand_and_without_number(self):
        self.shipment.write({'state': 'booked', 'pro_number': '123456790', 'pickup_number': 'XAT-8-35'})
        self.answers['/pickuprequests/XAT-8-35/cancel'] = FakeResponse(200, {'code': '200'})
        self.assertTrue(self.shipment.action_cancel())
        self.assertEqual(self._calls_to('/pickuprequests/XAT-8-35/cancel')[0]['json']['confirmationNbr'], 'XAT-8-35')
        shipment = self.shipment.copy({'state': 'booked', 'pro_number': '123456791', 'pickup_number': False})
        with self.assertRaises(RedirectWarning):
            shipment.action_cancel()
        self.assertEqual(shipment.state, 'booked')

    def test_tracking_and_documents(self):
        self.shipment.write({'state': 'booked', 'pro_number': '123-456782'})
        self.answers['/tracking/1.0/shipments/shipment-status-details'] = FakeResponse(200, {
            'code': '200', 'data': {'shipmentStatusDtls': [{
                'proNbr': '0123456782', 'pkupDate': 1794024000000,
                'shipmentStatus': {'statusCd': '5', 'reason': 'En route to destination',
                                   'description': 'En route to Charlotte, NC'},
                'estdDlvrDate': 1794283200000}],
                'matchedSearchReferences': ['123456782'], 'unmatchedSearchReferences': []}})
        self.shipment._ltl_update_tracking()
        call = self._calls_to('/shipment-status-details')[0]
        self.assertEqual(call['params'], [('referenceNumbers', '123456782')])
        self.assertEqual(self.shipment.state, 'in_transit')
        self.assertTrue(self.shipment.tracking_status.startswith('En route to Charlotte, NC, estimated delivery'))

        self.answers['/tracking/1.0/shipments/shipment-status-details'] = FakeResponse(200, {
            'code': '200', 'data': {'shipmentStatusDtls': [{
                'proNbr': '123456782', 'pkupDate': 1794024000000, 'finalDlvrDate': 1794330000000,
                'dlvrSigNameTxt': 'J SMITH',
                'shipmentStatus': {'statusCd': '23', 'reason': 'Delivered', 'description': 'Delivered'}}]}})
        self.answers['/imaged-docs'] = lambda: FakeResponse(200, {'code': '200', 'data': {'imagedDocument': [{
            'proNumber': '123456782', 'imageType': 'DR', 'imageFormat': 'PDF',
            'imageFiles': [{'fileName': '123456782_DR1.pdf', 'contentType': 'application/pdf',
                            'base64Data': base64.b64encode(PDF).decode()}]}]}})
        self.shipment._ltl_update_tracking()
        self.assertEqual(self.shipment.state, 'delivered')
        self.assertEqual(self.shipment.tracking_status, 'Delivered, signed by J SMITH')
        delivered = self.carrier._xpo_date(1794330000000)
        self.assertEqual(self.shipment.delivered_date, delivered)
        requested = [dict(c['params'])['imageType'] for c in self._calls_to('/imaged-docs')]
        self.assertEqual(requested, ['DR', 'WI'])
        names = self.env['ir.attachment'].search([('res_model', '=', self.shipment._name),
                                                  ('res_id', '=', self.shipment.id)]).mapped('name')
        self.assertIn('Delivery receipt 123456782.pdf', names)

    def test_helpers(self):
        carrier = self.carrier
        winter = carrier._xpo_moment(date(2026, 11, 2), 10.5, self.env.company.partner_id)
        summer = carrier._xpo_moment(date(2026, 10, 30), 16.0, self.env.company.partner_id)
        self.assertEqual(carrier._xpo_iso(winter), '2026-11-02T10:30:00-05:00')
        self.assertEqual(carrier._xpo_iso(summer), '2026-10-30T16:00:00-04:00')
        self.assertEqual(carrier._xpo_iso(winter, millis=True), '2026-11-02T10:30:00.000-0500')
        self.assertEqual(carrier._xpo_date(1526367600000), date(2018, 5, 15))
        self.assertFalse(carrier._xpo_date(None))
        self.assertEqual(carrier._xpo_amount([{'amt': 541.01, 'currencyCd': 'USD'}]), 541.01)
        self.assertEqual(carrier._xpo_amount({'amt': '22.5'}), 22.5)
        self.assertEqual(carrier._xpo_phone('+1 (404) 555-0100'), '404-5550100')
