# -*- coding: utf-8 -*-
"""Parcel next to LTL: parcel quotes in the rate shop, choosing parcel, UPS tracking."""
import json
from unittest.mock import patch

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
        inch = self.env.ref('uom.product_uom_inch')
        length_uom = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()
        self.assertAlmostEqual(length_uom._compute_quantity(box.packaging_length, inch, round=False), 20, places=2)
        self.assertAlmostEqual(length_uom._compute_quantity(box.height, inch, round=False), 12, places=2)
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
