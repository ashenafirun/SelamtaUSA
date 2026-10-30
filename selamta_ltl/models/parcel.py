# -*- coding: utf-8 -*-
"""Parcel next to LTL: a parcel shipping method (UPS through Odoo's own UPS connector) is
quoted in the LTL rate shop for small loads, and its deliveries are listed under
LTL & Parcel > Parcel deliveries with their tracking status.

Labels are still made the standard Odoo way (validate the delivery). Tracking for UPS uses
the UPS Track API with the same UPS app as Odoo's connector (client ID, secret and shipper
number on the shipping method); the app needs the Tracking API product on developer.ups.com.
"""
import logging
import re
import uuid
from datetime import date, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

UPS_HOSTS = {'production': 'https://onlinetools.ups.com', 'test': 'https://wwwcie.ups.com'}
TIMEOUT = 30
TRACK_DAYS = 21                 # follow parcels shipped in the last three weeks
PARCEL_MAX_WEIGHT_DEFAULT = 300  # lb; heavier loads are not quoted as parcel
PARCEL_BOX_NAME = 'Parcel box 20x12x12'


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    ltl_parcel = fields.Boolean(
        'Parcel carrier',
        help='Quote this shipping method (for example UPS) in the LTL rate shop for small loads, '
             'and list its deliveries under LTL & Parcel > Parcel deliveries.')
    ltl_parcel_token = fields.Char(groups='base.group_system', copy=False, readonly=True)
    ltl_parcel_token_expiry = fields.Datetime(groups='base.group_system', copy=False, readonly=True)

    # ------------------------------------------------------------------ quotes

    def ltl_parcel_rate(self, shipment):
        """Parcel price for the shipment's orders through this shipping method's own rating
        (Odoo's standard rate_shipment on each sale order). Returns (total, message)."""
        self.ensure_one()
        orders = shipment.picking_ids.mapped('sale_id') if 'sale_id' in shipment.picking_ids._fields else []
        if not orders:
            raise UserError(_('Parcel quotes need the shipment\'s delivery orders to come from sales orders.'))
        total, notes = 0.0, []
        for order in orders:
            result = self.rate_shipment(order)
            if not result.get('success'):
                raise UserError(result.get('error_message') or _('%s returned no price.', self.name))
            total += result.get('carrier_price', result.get('price')) or 0.0
            if result.get('warning_message'):
                notes.append(result['warning_message'])
        return total, ' '.join(notes)

    # ------------------------------------------------------------------ tracking

    def ltl_parcel_track(self, pickings):
        """{picking.id: {'status', 'delivered_date'}} from the carrier, when this shipping
        method's provider has a tracking hook (<delivery_type>_ltl_parcel_track)."""
        self.ensure_one()
        method = getattr(self, '%s_ltl_parcel_track' % self.delivery_type, None)
        return method(pickings) if method else {}

    def _ltl_ups_credentials(self):
        """(client ID, client secret, shipper number, environment) of Odoo's UPS connector."""
        self.ensure_one()
        carrier = self.sudo()
        values = [carrier[name] if name in carrier._fields else False
                  for name in ('ups_client_id', 'ups_client_secret', 'ups_shipper_number')]
        if not all(values):
            raise UserError(_('%s has no UPS client ID, secret and account number.', self.name))
        return values[0], values[1], values[2], 'production' if self.prod_environment else 'test'

    def _ltl_ups_token(self, host, client_id, secret, shipper):
        carrier = self.sudo()
        now = fields.Datetime.now()
        if carrier.ltl_parcel_token and carrier.ltl_parcel_token_expiry and carrier.ltl_parcel_token_expiry > now:
            return carrier.ltl_parcel_token
        try:
            response = requests.request(
                'POST', host + '/security/v1/oauth/token', data={'grant_type': 'client_credentials'},
                auth=(client_id, secret), headers={'x-merchant-id': shipper}, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise UserError(_('Could not reach UPS: %s', error)) from error
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code != 200 or not data.get('access_token'):
            raise UserError(_('UPS refused the sign-in for tracking (%(status)s): %(text)s',
                              status=response.status_code, text=(response.text or '')[:200]))
        try:
            lifetime = int(float(data.get('expires_in') or 3600))
        except (TypeError, ValueError):
            lifetime = 3600
        carrier.write({'ltl_parcel_token': data['access_token'],
                       'ltl_parcel_token_expiry': now + timedelta(seconds=max(lifetime - 300, 60))})
        return data['access_token']

    @api.model
    def _ltl_ups_date(self, value):
        value = re.sub(r'\D', '', str(value or ''))[:8]
        try:
            return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        except (ValueError, IndexError):
            return False

    def ups_rest_ltl_parcel_track(self, pickings):
        self.ensure_one()
        client_id, secret, shipper, environment = self._ltl_ups_credentials()
        host = UPS_HOSTS[environment]
        token = self._ltl_ups_token(host, client_id, secret, shipper)
        results = {}
        for picking in pickings:
            numbers = [n for n in re.split(r'[\s,;+]+', picking.carrier_tracking_ref or '') if n]
            packages = []
            for number in numbers:
                try:
                    response = requests.request(
                        'GET', '%s/api/track/v1/details/%s' % (host, number),
                        params={'locale': 'en_US', 'returnSignature': 'false'},
                        headers={'Authorization': 'Bearer %s' % token, 'transId': uuid.uuid4().hex[:32],
                                 'transactionSrc': 'selamta_ltl'},
                        timeout=TIMEOUT)
                except requests.RequestException as error:
                    _logger.warning('UPS tracking %s failed: %s', number, error)
                    continue
                if response.status_code in (401, 403):
                    raise UserError(_('UPS refused tracking (%s). Add the Tracking API to the UPS app on '
                                      'developer.ups.com.', response.status_code))
                try:
                    data = response.json()
                except ValueError:
                    continue
                for shipment in (data.get('trackResponse') or {}).get('shipment') or []:
                    packages.extend(shipment.get('package') or [])
            if packages:
                results[picking.id] = self._ltl_ups_tracking_info(packages)
        return results

    @api.model
    def _ltl_ups_tracking_info(self, packages):
        delivered_dates, texts, all_delivered = [], [], True
        for package in packages:
            current = package.get('currentStatus') or {}
            activities = package.get('activity') or []
            latest = activities[0] if activities else {}
            status = latest.get('status') or {}
            delivered = (status.get('type') == 'D') or (current.get('code') == '011')
            all_delivered = all_delivered and delivered
            text = current.get('description') or status.get('description') or ''
            address = ((latest.get('location') or {}).get('address') or {})
            place = ', '.join(filter(None, [address.get('city'), address.get('stateProvince')]))
            texts.append(' - '.join(filter(None, [text.strip().title() if text.isupper() else text.strip(), place])))
            for entry in package.get('deliveryDate') or []:
                if entry.get('type') == 'DEL':
                    delivered_dates.append(self._ltl_ups_date(entry.get('date')))
            if delivered and not package.get('deliveryDate'):
                delivered_dates.append(self._ltl_ups_date(latest.get('date')))
        info = {'status': '; '.join(dict.fromkeys(t for t in texts if t)) or False}
        dates = [d for d in delivered_dates if d]
        if all_delivered and dates:
            info['delivered_date'] = max(dates)
        return info


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ltl_parcel = fields.Boolean(related='carrier_id.ltl_parcel', string='Parcel')
    parcel_status = fields.Char('Parcel status', copy=False, readonly=True)
    parcel_delivered_date = fields.Date('Parcel delivered on', copy=False, readonly=True)

    def action_parcel_update_tracking(self):
        self._parcel_update_tracking(raise_errors=True)

    def _parcel_update_tracking(self, raise_errors=False):
        by_carrier = {}
        for picking in self.filtered(lambda p: p.carrier_id.ltl_parcel and p.carrier_tracking_ref):
            by_carrier.setdefault(picking.carrier_id, self.browse())
            by_carrier[picking.carrier_id] |= picking
        for carrier, pickings in by_carrier.items():
            try:
                results = carrier.ltl_parcel_track(pickings)
            except Exception as error:  # one carrier failing must not stop the rest
                if raise_errors:
                    raise
                _logger.warning('Parcel tracking failed for %s: %s', carrier.name, error)
                continue
            for picking in pickings:
                info = results.get(picking.id)
                if info:
                    picking.write({'parcel_status': info.get('status') or picking.parcel_status,
                                   'parcel_delivered_date': info.get('delivered_date') or False})

    @api.model
    def _cron_parcel_update_tracking(self):
        since = fields.Datetime.now() - timedelta(days=TRACK_DAYS)
        self.search([
            ('state', '=', 'done'), ('carrier_id.ltl_parcel', '=', True),
            ('carrier_tracking_ref', '!=', False), ('parcel_delivered_date', '=', False),
            ('date_done', '>=', since),
        ])._parcel_update_tracking()


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    @api.model
    def _ltl_ensure_parcel_box(self):
        """Our standard parcel box (20 x 12 x 12 in, up to 50 lb), in this database's length
        and weight units, for UPS. Created once; never changed afterwards."""
        if self.search_count([('name', '=', PARCEL_BOX_NAME)]):
            return
        template = self.env['product.template']
        inch = self.env.ref('uom.product_uom_inch')
        length_uom = template._get_length_uom_id_from_ir_config_parameter()
        weight_uom = template._get_weight_uom_id_from_ir_config_parameter()
        to_length = lambda value: inch._compute_quantity(value, length_uom, round=False)  # noqa: E731
        vals = {
            'name': PARCEL_BOX_NAME,
            'packaging_length': round(to_length(20), 4),
            'width': round(to_length(12), 4),
            'height': round(to_length(12), 4),
            'max_weight': round(self.env.ref('uom.product_uom_lb')._compute_quantity(50, weight_uom, round=False), 2),
        }
        carrier_types = dict(self._fields['package_carrier_type'].selection) \
            if 'package_carrier_type' in self._fields else {}
        if 'ups' in carrier_types:
            vals['package_carrier_type'] = 'ups'
            if 'shipper_package_code' in self._fields:
                vals['shipper_package_code'] = '02'  # customer supplied package
        self.create(vals)
