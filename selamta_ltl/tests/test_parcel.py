# -*- coding: utf-8 -*-
"""Parcel next to LTL: parcel quotes in the rate shop, choosing parcel, UPS tracking."""
import base64
import io
import json
import re
from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError

from odoo.tests import TransactionCase, tagged

PARCEL = 'odoo.addons.selamta_ltl.models.parcel'


class FakeResponse:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


@tagged('post_install', '-at_install')
class TestParcel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        cls.customer = env['res.partner'].create({
            'name': 'Parcel Market', 'is_company': True, 'street': '1 Main St', 'city': 'Urbana',
            'zip': '61801', 'country_id': us.id})
        freight = env['product.product'].create({'name': 'Shipping', 'type': 'service'})
        cls.ups = env['delivery.carrier'].create({
            'name': 'UPS US', 'product_id': freight.id, 'delivery_type': 'fixed', 'fixed_price': 27.90,
            'ltl_parcel': True})
        cls.ltl = env['delivery.carrier'].create({
            'name': 'LTL Co', 'product_id': freight.id, 'ltl_enabled': True,
            'ltl_vendor_id': env['res.partner'].create({'name': 'LTL Co', 'is_company': True}).id})
        cls.product = env['product.product'].create({
            'name': 'Teff flour 25 lb', 'is_storable': True, 'weight': 11.34, 'list_price': 40})

    def _delivery(self, qty):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': qty})],
        })
        order.action_confirm()
        picking = order.picking_ids
        picking.carrier_id = self.ltl
        picking.action_ltl_shipment()
        return order, picking, picking.ltl_shipment_id

    def test_parcel_box_created_in_database_units(self):
        box = self.env['stock.package.type'].search([('name', '=', 'Parcel box 20x12x12')])
        self.assertEqual(len(box), 1)
        self.assertEqual(box._ltl_dimensions(), (20.0, 12.0, 12.0))  # no UPS connector here: database units
        self.assertEqual(box.ltl_unit_type, 'box')
        self.env['stock.package.type']._ltl_ensure_parcel_box()  # runs again on update: no duplicate
        self.assertEqual(self.env['stock.package.type'].search_count([('name', '=', 'Parcel box 20x12x12')]), 1)

    def test_parcel_quote_and_choosing_parcel(self):
        _order, picking, shipment = self._delivery(qty=2)  # about 50 lb, boxes not measured
        action = shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        self.assertIn('Only parcel quotes', wizard.message)  # LTL quotes need measured units
        self.assertFalse(wizard.line_ids.filtered(lambda l: not l.parcel))
        parcel = wizard.line_ids.filtered('parcel')
        self.assertEqual(len(parcel), 1)
        self.assertEqual((parcel.carrier_id, parcel.total, parcel.service), (self.ups, 27.90, 'UPS US (parcel)'))
        result = parcel.action_choose()
        self.assertEqual(picking.carrier_id, self.ups)  # validate the delivery to print the UPS label
        self.assertEqual(shipment.state, 'cancel')
        self.assertEqual(result['res_id'], picking.id)
        self.assertIn('Going by parcel with UPS US', ' '.join(shipment.message_ids.mapped('body')))

    def test_heavy_loads_get_no_parcel_quote(self):
        _order, _picking, shipment = self._delivery(qty=20)  # about 500 lb
        with self.assertRaisesRegex(Exception, 'Measure every pallet'):
            shipment.action_open_rate_shop()  # too heavy for parcel, and not measured
        shipment.unit_ids.write({'length': 48, 'width': 40, 'height': 40})
        action = shipment.action_open_rate_shop()
        wizard = self.env['selamta.ltl.rate.wizard'].browse(action['res_id'])
        self.assertFalse(wizard.line_ids.filtered('parcel'))
        self.env['ir.config_parameter'].sudo().set_param('selamta_ltl.parcel_max_weight', 1000)
        wizard.action_refresh()
        self.assertTrue(wizard.line_ids.filtered('parcel'))

    def test_ups_tracking(self):
        order, picking, _shipment = self._delivery(qty=2)
        picking.write({'carrier_id': self.ups.id, 'carrier_tracking_ref': '1Z0X74Y80316287858,1Z0X74Y80318377631'})
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            if url.endswith('/security/v1/oauth/token'):
                return FakeResponse(200, {'access_token': 'tok', 'expires_in': '14399'})
            delivered = url.endswith('1Z0X74Y80316287858')
            package = {
                'trackingNumber': url.rsplit('/', 1)[1],
                'currentStatus': {'description': 'DELIVERED' if delivered else 'On the Way', 'code': '011' if delivered else '005'},
                'activity': [{'status': {'type': 'D' if delivered else 'I', 'description': 'DELIVERED'},
                              'date': '20261104', 'location': {'address': {'city': 'URBANA', 'stateProvince': 'IL'}}}],
            }
            if delivered:
                package['deliveryDate'] = [{'type': 'DEL', 'date': '20261104'}]
            return FakeResponse(200, {'trackResponse': {'shipment': [{'package': [package]}]}})

        with patch(PARCEL + '.requests.request', side_effect=fake_request), \
                patch.object(type(self.ups), '_ltl_ups_credentials', lambda self: ('id', 'secret', '0X74Y8', 'production')):
            info = self.ups.ups_rest_ltl_parcel_track(picking)[picking.id]
            self.assertFalse(info.get('delivered_date'))  # one of the two boxes is still on the way
            self.assertIn('Delivered - URBANA, IL', info['status'])
            token_call = calls[0]
            self.assertEqual(token_call[2]['auth'], ('id', 'secret'))
            self.assertEqual(token_call[2]['headers'], {'x-merchant-id': '0X74Y8'})
            track_call = calls[1]
            self.assertEqual(track_call[1], 'https://onlinetools.ups.com/api/track/v1/details/1Z0X74Y80316287858')
            self.assertEqual(track_call[2]['headers']['Authorization'], 'Bearer tok')
            # Both boxes delivered: the delivery is marked delivered.
            picking.carrier_tracking_ref = '1Z0X74Y80316287858'
            picking.state = 'done'
            picking.date_done = '2026-11-03 10:00:00'
            with patch.object(type(self.ups), 'ltl_parcel_track',
                              lambda carrier, pickings: carrier.ups_rest_ltl_parcel_track(pickings)):
                picking._parcel_update_tracking(raise_errors=True)
            self.assertEqual(str(picking.parcel_delivered_date), '2026-11-04')
            self.assertEqual(len([c for c in calls if c[1].endswith('/oauth/token')]), 1)  # token reused


def _gif(width=1400, height=800):
    """A label-like GIF lying on its side, as UPS sends them."""
    from PIL import Image, ImageDraw
    image = Image.new('L', (width, height), 255)
    ImageDraw.Draw(image).rectangle((20, 20, 1200, 780), outline=0, width=8)
    buffer = io.BytesIO()
    image.save(buffer, 'GIF')
    return buffer.getvalue()


@tagged('post_install', '-at_install')
class TestUpsFromShipment(TransactionCase):
    """UPS priced and shipped from the boxes typed on the shipment."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        us = env.ref('base.us')
        georgia = env['res.country.state'].search([('country_id', '=', us.id), ('code', '=', 'GA')], limit=1)
        env.company.partner_id.write({
            'street': '5335 Dividend Dr', 'street2': 'Suite C', 'city': 'Decatur', 'zip': '30035',
            'state_id': georgia.id, 'country_id': us.id, 'phone': '+1 (404) 555-0100'})
        cls.customer = env['res.partner'].create({
            'name': 'Parcel Market', 'is_company': True, 'street': '1 Main St', 'city': 'Urbana',
            'zip': '61801-2233', 'country_id': us.id, 'phone': '217-555-0199'})
        freight = env['product.product'].create({'name': 'Shipping', 'type': 'service'})
        cls.ups = env['delivery.carrier'].create({
            'name': 'UPS US', 'product_id': freight.id, 'delivery_type': 'fixed', 'fixed_price': 1.0,
            'ltl_parcel': True})
        cls.ltl = env['delivery.carrier'].create({
            'name': 'LTL Co', 'product_id': freight.id, 'ltl_enabled': True,
            'ltl_vendor_id': env['res.partner'].create({'name': 'LTL Co', 'is_company': True}).id})
        cls.product = env['product.product'].create({
            'name': 'Teff flour 25 lb', 'is_storable': True, 'weight': 11.34, 'list_price': 40})

    def setUp(self):
        super().setUp()
        self.calls = []
        self.answers = {}
        ups = self.ups
        original = type(ups)._ltl_method

        def ltl_method(carrier, operation):
            if carrier == ups:  # in production this is Odoo's UPS provider (ups_rest)
                return getattr(carrier, 'ups_rest_ltl_%s' % operation, None)
            return original(carrier, operation)

        def fake_request(method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            if url.endswith('/security/v1/oauth/token'):
                return FakeResponse(200, {'access_token': 'tok', 'expires_in': '14399'})
            for key, answer in self.answers.items():
                if key in url:
                    return answer
            return FakeResponse(500, {'response': {'errors': [{'code': '1', 'message': 'unexpected %s' % url}]}})

        for patcher in (
                patch.object(type(ups), '_ltl_method', ltl_method),
                patch.object(type(ups), '_ltl_ups_credentials', lambda self: ('id', 'secret', '0X74Y8', 'production')),
                patch(PARCEL + '.requests.request', side_effect=fake_request)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _shipment(self, lines, pickings=None):
        shipment = self.env['selamta.ltl.shipment'].create({
            'partner_id': self.customer.id,
            'unit_ids': [(0, 0, dict({'unit_type': 'box', 'description': 'Foodstuff'}, **line)) for line in lines],
        })
        if pickings:
            pickings.ltl_shipment_id = shipment
        return shipment

    def _rate_answer(self):
        return FakeResponse(200, {'RateResponse': {'Response': {'ResponseStatus': {'Code': '1'}}, 'RatedShipment': [
            {'Service': {'Code': '02'}, 'TotalCharges': {'MonetaryValue': '120.10'},
             'NegotiatedRateCharges': {'TotalCharge': {'MonetaryValue': '88.00'}},
             'GuaranteedDelivery': {'BusinessDaysInTransit': '2'}},
            {'Service': {'Code': '03'}, 'TotalCharges': {'MonetaryValue': '52.40'},
             'NegotiatedRateCharges': {'TotalCharge': {'MonetaryValue': '35.20'}},
             'TimeInTransit': {'ServiceSummary': {'EstimatedArrival': {'BusinessDaysInTransit': '3'}}}},
        ]}})

    def _ship_answer(self, numbers):
        label = base64.b64encode(_gif()).decode()
        return FakeResponse(200, {'ShipmentResponse': {'ShipmentResults': {
            'ShipmentIdentificationNumber': numbers[0],
            'ShipmentCharges': {'TotalCharges': {'MonetaryValue': '52.40'}},
            'NegotiatedRateCharges': {'TotalCharge': {'MonetaryValue': '35.20'}},
            'PackageResults': [{'TrackingNumber': n, 'ShippingLabel': {'ImageFormat': {'Code': 'GIF'},
                                                                        'GraphicImage': label}} for n in numbers],
        }}})

    def _wizard(self, shipment):
        return self.env['selamta.ltl.rate.wizard'].browse(shipment.action_open_rate_shop()['res_id'])

    def test_ups_rates_from_typed_boxes_without_a_delivery(self):
        shipment = self._shipment([
            {'quantity': 3, 'length': 20, 'width': 12, 'height': 12, 'weight': 90},
            {'quantity': 1, 'length': 24, 'width': 18, 'height': 12, 'weight': 41},
        ])
        self.answers['/api/rating/v2409/Shoptimeintransit'] = self._rate_answer()
        wizard = self._wizard(shipment)
        lines = wizard.line_ids.filtered('parcel')
        self.assertEqual([(l.service, l.total, l.transit_days) for l in lines.sorted('total')],
                         [('UPS Ground', 35.20, 3), ('UPS 2nd Day Air', 88.00, 2)])
        request = [c for c in self.calls if '/rating/' in c[1]][0][2]
        self.assertEqual(request['headers']['Authorization'], 'Bearer tok')
        self.assertEqual(request['json']['RateRequest']['PickupType'], {'Code': '06'})  # UPS picks up
        sent = request['json']['RateRequest']['Shipment']
        self.assertEqual([p['PackageWeight']['Weight'] for p in sent['Package']], ['30.0', '30.0', '30.0', '41.0'])
        self.assertEqual(sent['Package'][3]['Dimensions'],
                         {'UnitOfMeasurement': {'Code': 'IN'}, 'Length': '24.0', 'Width': '18.0', 'Height': '12.0'})
        self.assertEqual(sent['Package'][0]['PackagingType'], {'Code': '02'})
        self.assertEqual(sent['Shipper']['ShipperNumber'], '0X74Y8')
        self.assertEqual(sent['PaymentDetails']['ShipmentCharge'][0]['BillShipper']['AccountNumber'], '0X74Y8')
        self.assertEqual(sent['ShipTo']['Address']['PostalCode'], '618012233')
        self.assertEqual(sent['ShipTo']['Phone'], {'Number': '2175550199'})
        self.assertEqual(sent['ShipFrom']['Address']['AddressLine'], ['5335 Dividend Dr', 'Suite C'])
        self.assertEqual(sent['ShipmentTotalWeight']['Weight'], '131.0')
        self.assertEqual(sent['DeliveryTimeInformation']['PackageBillType'], '03')
        self.assertNotIn('ResidentialAddressIndicator', sent['ShipTo']['Address'])

    def test_ups_says_what_is_missing(self):
        shipment = self._shipment([{'unit_type': 'pallet', 'length': 48, 'width': 40, 'height': 40, 'weight': 200}])
        error = self._wizard(shipment).line_ids.filtered('parcel').error
        self.assertIn('boxes only', error)
        shipment.unit_ids.write({'unit_type': 'box', 'height': 0})
        self.assertIn('Measure every box', self._wizard(shipment).line_ids.filtered('parcel').error)
        shipment.unit_ids.write({'length': 20, 'width': 12, 'height': 12, 'weight': 160})
        self.assertIn('up to 150 lb', self._wizard(shipment).line_ids.filtered('parcel').error)
        self.assertFalse([c for c in self.calls if '/api/' in c[1]])  # nothing was sent to UPS

    def test_falls_back_to_rates_without_transit_days(self):
        shipment = self._shipment([{'quantity': 1, 'length': 20, 'width': 12, 'height': 12, 'weight': 30}])
        self.answers['/Shoptimeintransit'] = FakeResponse(400, {'response': {'errors': [
            {'code': '111500', 'message': 'Time in transit not available'}]}})
        self.answers['/api/rating/v2409/Shop'] = self._rate_answer()
        lines = self._wizard(shipment).line_ids.filtered('parcel')
        self.assertEqual(len(lines), 2)
        self.assertFalse(lines.filtered('error'))

    def test_choosing_ups_makes_labels_on_the_shipment(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 10})],
        })
        order.action_confirm()
        picking = order.picking_ids  # the whole order: we only send part of it today
        shipment = self._shipment([{'quantity': 2, 'length': 20, 'width': 12, 'height': 12, 'weight': 50}], picking)
        shipment.accessorial_ids = self.env['selamta.ltl.accessorial'].search([('code', '=', 'RESIDENTIAL_DEL')])
        self.answers['/api/rating/v2409/Shoptimeintransit'] = self._rate_answer()
        ground = self._wizard(shipment).line_ids.filtered(lambda l: l.service == 'UPS Ground')
        self.answers['/api/shipments/v2409/ship'] = self._ship_answer(['1Z0X74Y80300000011', '1Z0X74Y80300000022'])
        self.answers['/api/pickupcreation/v2409/pickup'] = FakeResponse(200, {'PickupCreationResponse': {
            'Response': {'ResponseStatus': {'Code': '1'}}, 'PRN': '2929602E9CP', 'RateStatus': {'Code': '01'},
            'RateResult': {'RateType': 'FD', 'CurrencyCode': 'USD', 'GrandTotalOfAllCharge': '8.30'}}})
        shipment.write({'pickup_ready_time': 13.0, 'pickup_close_time': 17.5,
                        'pickup_instructions': 'Ring the bell at door C'})
        ground.action_choose()

        pickup = [c for c in self.calls if '/pickupcreation/' in c[1]][0][2]['json']['PickupCreationRequest']
        self.assertEqual(pickup['Shipper']['Account'], {'AccountNumber': '0X74Y8', 'AccountCountryCode': 'US'})
        self.assertEqual(pickup['PickupDateInfo']['ReadyTime'], '1300')
        self.assertEqual(pickup['PickupDateInfo']['CloseTime'], '1730')
        self.assertEqual(pickup['PickupDateInfo']['PickupDate'], max(shipment.ship_date, date.today()).strftime('%Y%m%d'))
        self.assertEqual(pickup['PickupAddress']['AddressLine'], ['5335 Dividend Dr'])
        self.assertEqual(pickup['PickupAddress']['Room'], 'Suite C')
        self.assertEqual(pickup['PickupAddress']['PostalCode'], '30035')
        self.assertEqual(pickup['PickupAddress']['Phone'], {'Number': '4045550100'})
        self.assertEqual(pickup['AlternateAddressIndicator'], 'N')
        self.assertEqual(pickup['PickupPiece'], [{'ServiceCode': '003', 'Quantity': '2', 'DestinationCountryCode': 'US',
                                                  'ContainerCode': '01'}])
        self.assertEqual(pickup['TotalWeight'], {'Weight': '50.0', 'UnitOfMeasurement': 'LBS'})
        self.assertEqual(pickup['OverweightIndicator'], 'N')
        self.assertEqual((pickup['PaymentMethod'], pickup['ShippingLabelsAvailable']), ('01', 'Y'))
        self.assertEqual(pickup['TrackingData'], [{'TrackingNumber': '1Z0X74Y80300000011'},
                                                  {'TrackingNumber': '1Z0X74Y80300000022'}])
        self.assertEqual(pickup['SpecialInstruction'], 'Ring the bell at door C')
        self.assertEqual(shipment.pickup_number, '2929602E9CP')
        self.assertIn('UPS pickup charge 8.30 USD', ' '.join(shipment.message_ids.mapped('body')))

        sent = [c for c in self.calls if c[1].endswith('/ship')][0][2]['json']['ShipmentRequest']
        self.assertEqual(sent['Shipment']['Service']['Code'], '03')
        self.assertEqual(len(sent['Shipment']['Package']), 2)
        self.assertEqual(sent['Shipment']['Package'][0]['Packaging'], {'Code': '02'})
        self.assertEqual(sent['Shipment']['Package'][0]['ReferenceNumber'][0], {'Value': shipment.name})
        self.assertEqual(sent['Shipment']['PaymentInformation']['ShipmentCharge'][0]['Type'], '01')
        self.assertEqual(sent['Shipment']['ShipTo']['Address']['ResidentialAddressIndicator'], 'Y')
        self.assertEqual(sent['LabelSpecification']['LabelStockSize'], {'Height': '6', 'Width': '4'})

        self.assertEqual(shipment.state, 'booked')
        self.assertEqual(shipment.carrier_id, self.ups)
        self.assertTrue(shipment.ltl_parcel)
        self.assertEqual(shipment.parcel_tracking_ref, '1Z0X74Y80300000011 1Z0X74Y80300000022')
        self.assertEqual(shipment.parcel_shipment_number, '1Z0X74Y80300000011')
        self.assertEqual(shipment.quoted_amount, 35.20)
        label = shipment.parcel_label_id
        self.assertTrue(label.raw.startswith(b'%PDF'))
        self.assertEqual(len(re.findall(rb'/Type\s*/Page\b', label.raw)), 2)  # one 4x6 page per box
        self.assertEqual(shipment.action_parcel_labels()['url'], '/web/content/%s' % label.id)
        self.assertEqual((picking.carrier_id, picking.carrier_tracking_ref),
                         (self.ups, '1Z0X74Y80300000011,1Z0X74Y80300000022'))

        # Validating the delivery buys no second label: it already has the tracking numbers.
        with patch.object(type(self.ups), 'send_shipping', side_effect=AssertionError('second label')):
            picking.move_ids.write({'quantity': 10, 'picked': True})
            picking.button_validate()
        self.assertEqual(picking.state, 'done')

        # Re-shopping a shipment that has labels asks to cancel (void) first.
        wizard = self._wizard(shipment)
        with self.assertRaisesRegex(UserError, 'already has UPS labels'):
            wizard.line_ids.filtered(lambda l: l.service == 'UPS Ground').action_choose()

    def test_ups_refusal_changes_nothing(self):
        shipment = self._shipment([{'quantity': 1, 'length': 20, 'width': 12, 'height': 12, 'weight': 30}])
        self.answers['/api/rating/v2409/Shoptimeintransit'] = self._rate_answer()
        ground = self._wizard(shipment).line_ids.filtered(lambda l: l.service == 'UPS Ground')
        self.answers['/api/shipments/v2409/ship'] = FakeResponse(400, {'response': {'errors': [
            {'code': '120802', 'message': 'Address Validation Error on ShipTo address'}]}})
        with self.assertRaisesRegex(UserError, 'Address Validation Error'):
            ground.action_choose()
        self.assertEqual((shipment.state, shipment.carrier_id.id, shipment.parcel_tracking_ref), ('draft', False, False))

    def test_cancel_voids_with_ups_and_tracking_follows(self):
        shipment = self._shipment([{'quantity': 1, 'length': 20, 'width': 12, 'height': 12, 'weight': 30}])
        shipment.write({'carrier_id': self.ups.id, 'state': 'booked', 'pickup_number': '2929602E9CP',
                        'parcel_tracking_ref': '1Z0X74Y80300000033', 'parcel_shipment_number': '1Z0X74Y80300000033'})

        self.answers['/api/track/v1/details/1Z0X74Y80300000033'] = FakeResponse(200, {'trackResponse': {'shipment': [{
            'package': [{'currentStatus': {'description': 'On the Way', 'code': '005'},
                         'activity': [{'status': {'type': 'I'}, 'date': '20261104',
                                       'location': {'address': {'city': 'URBANA', 'stateProvince': 'IL'}}}]}]}]}})
        shipment._ltl_update_tracking()
        self.assertEqual((shipment.state, shipment.tracking_status), ('in_transit', 'On the Way - URBANA, IL'))
        shipment.state = 'booked'

        self.answers['/void/cancel/1Z0X74Y80300000033'] = FakeResponse(200, {'VoidShipmentResponse': {
            'Response': {'ResponseStatus': {'Code': '1'}}, 'SummaryResult': {'Status': {'Code': '1', 'Description': 'Voided'}}}})
        self.answers['/api/shipments/v2409/pickup/02'] = FakeResponse(200, {'PickupCancelResponse': {
            'Response': {'ResponseStatus': {'Code': '1'}}, 'PickupType': '01'}})
        result = shipment.action_cancel()
        cancel = [c for c in self.calls if c[1].endswith('/pickup/02')][0]
        self.assertEqual((cancel[0], cancel[2]['headers']['Prn']), ('DELETE', '2929602E9CP'))
        self.assertIn('UPS pickup 2929602E9CP cancelled', result['params']['message'])
        void = [c for c in self.calls if '/void/cancel/' in c[1]][0]
        self.assertEqual(void[0], 'DELETE')
        self.assertEqual(void[2]['headers']['shipperNumber'], '0X74Y8')
        self.assertEqual(shipment.state, 'cancel')
        self.assertFalse(shipment.parcel_tracking_ref)
        self.assertIn('throw away its labels', result['params']['message'])

    def test_drop_off_makes_labels_only(self):
        shipment = self._shipment([{'quantity': 1, 'length': 20, 'width': 12, 'height': 12, 'weight': 30}])
        shipment.request_pickup = False
        answer = self._rate_answer()
        answer._data['RateResponse']['RatedShipment'].append(  # UPS answering a service twice
            {'Service': {'Code': '03'}, 'TotalCharges': {'MonetaryValue': '64.00'},
             'NegotiatedRateCharges': {'TotalCharge': {'MonetaryValue': '41.90'}}})
        self.answers['/api/rating/v2409/Shoptimeintransit'] = answer
        lines = self._wizard(shipment).line_ids.filtered('parcel')
        self.assertEqual(sorted(lines.mapped('total')), [35.20, 88.00])  # one line per service, the lower price
        rating = [c for c in self.calls if '/rating/' in c[1]][0][2]['json']['RateRequest']
        self.assertEqual(rating['PickupType'], {'Code': '03'})  # we take it to UPS
        self.answers['/api/shipments/v2409/ship'] = self._ship_answer(['1Z0X74Y80300000044'])
        lines.filtered(lambda l: l.service == 'UPS Ground').action_choose()
        self.assertFalse([c for c in self.calls if '/pickup' in c[1]])
        self.assertEqual((shipment.state, shipment.pickup_number), ('booked', False))
        self.assertIn('take the boxes to a UPS Store', ' '.join(shipment.message_ids.mapped('body')))

    def test_refused_pickup_keeps_the_labels(self):
        shipment = self._shipment([{'quantity': 1, 'length': 20, 'width': 12, 'height': 12, 'weight': 80}])
        self.answers['/api/rating/v2409/Shoptimeintransit'] = self._rate_answer()
        ground = self._wizard(shipment).line_ids.filtered(lambda l: l.service == 'UPS Ground')
        self.answers['/api/shipments/v2409/ship'] = self._ship_answer(['1Z0X74Y80300000055'])
        self.answers['/api/pickupcreation/v2409/pickup'] = FakeResponse(400, {'response': {'errors': [
            {'code': '9510131', 'message': 'Order has successfully been submitted, but the Pickup is past cutoff'}]}})
        ground.action_choose()
        sent = [c for c in self.calls if '/pickupcreation/' in c[1]][0][2]['json']['PickupCreationRequest']
        self.assertEqual(sent['OverweightIndicator'], 'Y')  # over 70 lb
        self.assertEqual((shipment.state, shipment.parcel_tracking_ref, shipment.pickup_number),
                         ('booked', '1Z0X74Y80300000055', False))
        self.assertIn('Schedule the pickup on ups.com', ' '.join(shipment.message_ids.mapped('body')))

    def test_label_pdf_is_upright_4x6(self):
        pdf = self.ups._ltl_ups_labels_pdf([_gif(), _gif()])
        self.assertTrue(pdf.startswith(b'%PDF'))
        boxes = re.findall(rb'/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]', pdf)
        self.assertEqual([(float(w), float(h)) for w, h in boxes], [(288.0, 432.0)] * 2)  # 4 x 6 in, portrait
