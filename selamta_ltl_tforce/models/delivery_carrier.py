# -*- coding: utf-8 -*-
"""TForce Freight API connection (https://developer.tforcefreight.com).

Authentication: OAuth2 client credentials against Microsoft identity platform; the token
lasts about 60 minutes and is reused until shortly before it expires.
Versions: ``?api-version=v1`` is production, ``?api-version=cie-v1`` is TForce's test
environment (nothing is really booked or picked up).
"""
import base64
import logging
from datetime import timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

API_HOST = 'https://api.tforcefreight.com'
DEFAULT_TOKEN_URL = 'https://login.microsoftonline.com/ca4f5969-c10f-40d4-8127-e74b691f95de/oauth2/v2.0/token'
DEFAULT_SCOPE = 'https://tffproduction.onmicrosoft.com/04cc9749-dbe5-4914-b262-d866b907756b/.default'
TIMEOUT = 45

# Our accessorial codes -> TForce service options.
DELIVERY_OPTIONS = {
    'LIFTGATE_DEL': 'LIFD',
    'RESIDENTIAL_DEL': 'RESD',
    'LIMITED_ACCESS_DEL': 'LADL',
    'INSIDE_DEL': 'INDE',
    'NOTIFY_DEL': 'NTFN',
    'APPOINTMENT_DEL': 'NTFN',  # TForce has no separate appointment option: notify/call ahead
}
PICKUP_OPTIONS = {
    'LIFTGATE_PU': 'LIFO',
}
# Our pallet/box -> TForce packaging codes.
COMMODITY_PACKAGING = {'pallet': 'PLT', 'box': 'BOX'}
# Rate lines: subtotals left out, discounts shown negative, friendlier names.
SKIP_CHARGES = {'AFTR_DSCNT', 'DSCNT_RATE'}
NEGATIVE_CHARGES = {'DSCNT'}
CHARGE_NAMES = {
    'LND_GROSS': 'Linehaul before discount',
    'DSCNT': 'Discount',
    'FUEL_SUR': 'Fuel surcharge',
    'LIFD': 'Liftgate at delivery',
    'LIFO': 'Liftgate at pickup',
    'INDE': 'Inside delivery',
    'INPU': 'Inside pickup',
    'RESD': 'Residential delivery',
    'RESP': 'Residential pickup',
    'LADL': 'Limited access delivery',
    'LAPU': 'Limited access pickup',
    'NTFN': 'Notify before delivery',
    'HICST': 'High cost service area',
    'EXLI': 'Extreme length',
}
TRACKING_STATE = {'005': 'in_transit', '006': 'in_transit', '011': 'delivered'}
DOCUMENT_CATEGORIES = ['DR', 'WGHT', 'BOL', 'INVC']
DOCUMENT_NAMES = {
    'DR': 'Delivery receipt', 'WGHT': 'Weight and inspection', 'BOL': 'TForce BOL',
    'INVC': 'TForce invoice', 'CLM': 'Claim',
}


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('tforce', 'TForce Freight')],
        ondelete={'tforce': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    tforce_environment = fields.Selection(
        [('test', 'Test (CIE) - nothing is really booked'), ('production', 'Production')],
        'TForce environment', default='test', required=True)
    tforce_client_id = fields.Char('Client ID', groups='base.group_system', copy=False)
    tforce_client_secret = fields.Char('Client secret', groups='base.group_system', copy=False)
    tforce_token_url = fields.Char('Token address', default=DEFAULT_TOKEN_URL, groups='base.group_system')
    tforce_scope = fields.Char('Scope', default=DEFAULT_SCOPE, groups='base.group_system')
    tforce_access_token = fields.Char(groups='base.group_system', copy=False, readonly=True)
    tforce_token_expiry = fields.Datetime(groups='base.group_system', copy=False, readonly=True)
    tforce_service_code = fields.Selection(
        [('308', 'TForce Freight LTL'), ('309', 'TForce Freight LTL - Guaranteed'),
         ('349', 'TForce Standard LTL')],
        'TForce service', default='308', required=True)
    tforce_bol_format = fields.Selection(
        [('VICS', 'VICS (standard BOL)'), ('TFF', 'TForce format')],
        'TForce BOL format', default='VICS', required=True)
    tforce_label_type = fields.Selection(
        [('01', 'Address labels with PRO'), ('03', 'PRO stickers'),
         ('07', 'Thermal labels 4x6'), ('08', 'Thermal labels 4x8')],
        'Labels to get with the BOL', help='Leave empty for no labels.')
    tforce_schedule_pickup = fields.Boolean(
        'Schedule pickup when booking', default=True,
        help='Ask TForce for a pickup in the same call that creates the BOL.')
    tforce_contact_name = fields.Char('Pickup contact name')
    tforce_contact_email = fields.Char('Pickup contact email')
    tforce_contact_phone = fields.Char('Pickup contact phone')

    # ------------------------------------------------------------------ connection

    def _tforce_version(self):
        return 'v1' if self.tforce_environment == 'production' else 'cie-v1'

    def _tforce_token(self):
        self.ensure_one()
        carrier = self.sudo()
        now = fields.Datetime.now()
        if carrier.tforce_access_token and carrier.tforce_token_expiry and carrier.tforce_token_expiry > now:
            return carrier.tforce_access_token
        if not carrier.tforce_client_id or not carrier.tforce_client_secret:
            raise UserError(_(
                'Enter the TForce client ID and client secret on the %s shipping method first.',
                carrier.name))
        try:
            response = requests.post(
                carrier.tforce_token_url or DEFAULT_TOKEN_URL,
                data={
                    'client_id': carrier.tforce_client_id,
                    'client_secret': carrier.tforce_client_secret,
                    'grant_type': 'client_credentials',
                    'scope': carrier.tforce_scope or DEFAULT_SCOPE,
                },
                timeout=TIMEOUT)
        except requests.RequestException as error:
            raise UserError(_('Could not reach TForce to sign in: %s', error)) from error
        data = self._tforce_json(response)
        if response.status_code != 200 or not data.get('access_token'):
            raise UserError(_(
                'TForce refused the sign-in (%(status)s): %(message)s. Check the client ID and '
                'client secret.', status=response.status_code,
                message=data.get('error_description') or data.get('error') or response.text[:300]))
        lifetime = int(data.get('expires_in') or 3600)
        carrier.write({
            'tforce_access_token': data['access_token'],
            'tforce_token_expiry': now + timedelta(seconds=max(lifetime - 300, 60)),
        })
        return data['access_token']

    @api.model
    def _tforce_json(self, response):
        try:
            return response.json() if response.content else {}
        except ValueError:
            return {}

    def _tforce_call(self, method, path, payload=None, retry=True):
        """Call a TForce API, e.g. ('POST', '/rating/getRate', {...}). Returns the JSON."""
        self.ensure_one()
        url = '%s%s' % (API_HOST, path)
        headers = {
            'Authorization': 'Bearer %s' % self._tforce_token(),
            'Content-Type': 'application/json',
        }
        params = {'api-version': self._tforce_version()}
        _logger.info('TForce %s %s (%s)', method, path, params['api-version'])
        try:
            response = requests.request(
                method, url, params=params, json=payload, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise UserError(_('Could not reach TForce: %s', error)) from error
        if response.status_code == 401 and retry:
            self.sudo().write({'tforce_access_token': False, 'tforce_token_expiry': False})
            return self._tforce_call(method, path, payload, retry=False)
        data = self._tforce_json(response)
        if response.status_code >= 400:
            raise UserError(_('TForce answered %(status)s: %(message)s',
                              status=response.status_code, message=self._tforce_error(data, response)))
        return data

    @api.model
    def _tforce_error(self, data, response=None):
        messages = []
        summary = data.get('summary') or {}
        status = summary.get('responseStatus') or data.get('responseStatus') or {}
        if status.get('message') or status.get('description'):
            messages.append(status.get('message') or status.get('description'))
        details = data.get('detail')
        for detail in (details if isinstance(details, list) else [details] if details else []):
            ds = (detail or {}).get('detailStatus') or {}
            if ds.get('message'):
                messages.append(ds['message'])
        for key in ('message', 'title', 'error'):
            if isinstance(data.get(key), str):
                messages.append(data[key])
        if data.get('errors'):
            messages.append(str(data['errors'])[:300])
        if not messages and response is not None:
            messages.append(response.text[:300])
        return '; '.join(m for m in messages if m) or _('no details')

    # ------------------------------------------------------------------ request parts

    @api.model
    def _tforce_address(self, partner, full=False):
        if not partner.zip or not partner.country_id:
            raise UserError(_('%s needs a ZIP code and country for TForce.', partner.display_name))
        address = {
            'city': partner.city or '',
            'stateProvinceCode': partner.state_id.code or '',
            'postalCode': (partner.zip or '').strip()[:10],
            'country': partner.country_id.code or 'US',
        }
        if full:
            if not partner.street or not partner.city or not partner.state_id:
                raise UserError(_('%s needs a street, city and state for a TForce BOL.', partner.display_name))
            address['addressLine'] = ', '.join(filter(None, [partner.street, partner.street2]))[:100]
        return address

    @api.model
    def _tforce_party(self, partner, label):
        phone = digits_only(partner.phone or partner.mobile or partner.commercial_partner_id.phone)
        if not phone:
            raise UserError(_('TForce needs a phone number for the %(label)s (%(name)s).',
                              label=label, name=partner.display_name))
        name = partner.commercial_partner_id.name if partner.parent_id else partner.name
        party = {
            'name': (name or '')[:100],
            'phone': {'number': phone[:15]},
            'address': self._tforce_address(partner, full=True),
        }
        if partner.email:
            party['email'] = partner.email[:100]
        if partner.parent_id and partner.name:
            party['contact'] = partner.name[:100]
        return party

    def _tforce_service_options(self, shipment):
        codes = shipment.accessorial_ids.mapped('code')
        delivery = sorted({DELIVERY_OPTIONS[c] for c in codes if c in DELIVERY_OPTIONS})
        pickup = sorted({PICKUP_OPTIONS[c] for c in codes if c in PICKUP_OPTIONS})
        options = {}
        if delivery:
            options['delivery'] = delivery
        if pickup:
            options['pickup'] = pickup
        return options

    @api.model
    def _tforce_commodities(self, shipment, with_description=False):
        commodities = []
        for unit in shipment.unit_ids.sorted('sequence'):
            if not unit.freight_class:
                raise UserError(_('Measure every pallet or box on %s first.', shipment.name))
            item = {
                'class': unit.freight_class,
                'pieces': unit.quantity,
                'weight': {'weight': round(unit.weight, 1), 'weightUnit': 'LBS'},
                'packagingType': COMMODITY_PACKAGING.get(unit.unit_type, 'PLT'),
                'dangerousGoods': False,
                'dimensions': {
                    'length': round(unit.length, 1), 'width': round(unit.width, 1),
                    'height': round(unit.height, 1), 'unit': 'IN',
                },
            }
            if unit.nmfc_item:
                item['nmfc'] = {'prime': unit.nmfc_item}
                if unit.nmfc_sub:
                    item['nmfc']['sub'] = unit.nmfc_sub
            if with_description:
                text = unit.description or _('Freight')
                if shipment.consolidated and unit.for_text:
                    text = '%s - for %s' % (text, unit.for_text)
                item['description'] = text[:754]
            commodities.append(item)
        return commodities

    def _tforce_rate_request(self, shipment):
        payer = shipment.company_id.partner_id
        request = {
            'requestOptions': {
                'serviceCode': self.tforce_service_code,
                'pickupDate': fields.Date.to_string(shipment.ship_date or fields.Date.context_today(self)),
                'type': 'L',
                'densityEligible': False,
                'timeInTransit': True,
                'quoteNumber': True,
                'customerContext': shipment.name,
            },
            'shipFrom': {'address': self._tforce_address(shipment.shipper_id)},
            'shipTo': {'address': self._tforce_address(shipment.partner_id)},
            'payment': {'payer': {'address': self._tforce_address(payer)}, 'billingCode': '10'},
            'commodities': self._tforce_commodities(shipment),
        }
        options = self._tforce_service_options(shipment)
        if options:
            request['serviceOptions'] = options
        return request

    def _tforce_bol_request(self, shipment):
        units = shipment.unit_ids
        pallets = sum(units.filtered(lambda u: u.unit_type == 'pallet').mapped('quantity'))
        boxes = sum(units.filtered(lambda u: u.unit_type != 'pallet').mapped('quantity'))
        request = {
            'requestOptions': {
                'serviceCode': self.tforce_service_code,
                'pickupDate': fields.Date.to_string(shipment.ship_date or fields.Date.context_today(self)),
                'previewRate': True,
                'timeInTransit': True,
                'customerContext': shipment.name,
                'bolPrintFormat': self.tforce_bol_format,
            },
            'shipFrom': self._tforce_party(shipment.shipper_id, _('shipper')),
            'shipTo': self._tforce_party(shipment.partner_id, _('consignee')),
            'payment': {
                'payer': self._tforce_party(shipment.company_id.partner_id, _('bill-to')),
                'billingCode': '10',
            },
            'commodities': self._tforce_commodities(shipment, with_description=True),
            'references': [{'number': shipment.bol_reference, 'type': 'BL'}],
            'documents': {'image': [{'type': '20', 'format': '01'}]},
        }
        if pallets:
            request['handlingUnitOne'] = {'quantity': pallets, 'typeCode': 'PLT'}
        if boxes:
            request['handlingUnitTwo'] = {'quantity': boxes, 'typeCode': 'LOO'}
        for picking in shipment.picking_ids:
            sale = picking.sale_id if 'sale_id' in picking._fields else False
            if sale and sale.client_order_ref:
                request['references'].append({'number': sale.client_order_ref[:35], 'type': 'PO'})
            if picking.origin:
                request['references'].append({'number': picking.origin[:35], 'type': 'SO'})
        delivery_lines = shipment._bol_delivery_lines()
        if delivery_lines:
            request['instructions'] = {'delivery': ', '.join(delivery_lines)[:300]}
        if shipment.pickup_instructions:
            request.setdefault('instructions', {})['pickup'] = ' '.join(
                shipment.pickup_instructions.split())[:200]
        options = self._tforce_service_options(shipment)
        if options:
            request['serviceOptions'] = options
        if self.tforce_label_type:
            request['documents']['image'].append({
                'type': '30', 'format': '01',
                'label': {'type': self.tforce_label_type, 'startPosition': 1,
                          'numberOfStickers': max(shipment.total_units, 1)},
            })
        if self.tforce_schedule_pickup:
            company = shipment.company_id
            phone = digits_only(self.tforce_contact_phone or shipment.shipper_id.phone or company.phone)
            email = self.tforce_contact_email or shipment.shipper_id.email or company.email
            if not phone or not email:
                raise UserError(_(
                    'Fill in the pickup contact phone and email on the %s shipping method '
                    '(TForce tab) to schedule pickups.', self.name))
            request['pickupRequest'] = {
                'pickup': {
                    'date': fields.Date.to_string(shipment.ship_date or fields.Date.context_today(self)),
                    'time': self._tforce_time(shipment.pickup_ready_time),
                    'openTime': self._tforce_time(min(self.ltl_dock_open_time, shipment.pickup_ready_time)),
                    'closeTime': self._tforce_time(shipment.pickup_close_time),
                },
                'requester': {
                    'companyName': (company.name or '')[:200],
                    'contactName': (self.tforce_contact_name or self.env.user.name or company.name)[:200],
                    'email': email[:100],
                    'phone': {'number': phone[:15]},
                },
                'pomIndicator': False,
            }
        return request

    @api.model
    def _tforce_time(self, hours):
        """10.5 -> '10:30:00'."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        return '%02d:%02d:00' % (min(hour, 23), minute)

    @api.model
    def _tforce_charges(self, rate_detail):
        """TForce's rate lines as charges that add up to the total: gross linehaul, the
        discount as a negative amount, then fuel and each accessorial. TForce also sends
        the discount percentage and the after-discount subtotal; those are left out so the
        lines sum to the total."""
        charges = []
        for line in rate_detail.get('rate') or []:
            code = line.get('code') or ''
            if (line.get('unit') or 'USD').upper() != 'USD' or code in SKIP_CHARGES:
                continue
            try:
                amount = float(line.get('value') or 0.0)
            except (TypeError, ValueError):
                continue
            if code in NEGATIVE_CHARGES:
                amount = -abs(amount)
            charges.append({'code': code, 'name': CHARGE_NAMES.get(code) or line.get('description') or code,
                            'amount': amount})
        total = ((rate_detail.get('shipmentCharges') or {}).get('total') or {}).get('value')
        try:
            total = float(total)
        except (TypeError, ValueError):
            total = None
        if charges and total is not None:
            difference = round(total - sum(c['amount'] for c in charges), 2)
            if abs(difference) >= 0.01:
                charges.append({'code': 'OTHER', 'name': _('Other (difference to TForce total)'),
                                'amount': difference})
        return charges

    @api.model
    def _tforce_transit_days(self, detail):
        tit = detail.get('timeInTransit') or {}
        try:
            return int(tit.get('value') or tit.get('timeInTransit') or 0)
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------ selamta_ltl hooks

    def tforce_ltl_rate(self, shipment):
        self.ensure_one()
        data = self._tforce_call('POST', '/rating/getRate', self._tforce_rate_request(shipment))
        quote_number = (data.get('summary') or {}).get('quoteNumber')
        rates = []
        for detail in data.get('detail') or []:
            status = detail.get('detailStatus') or {}
            total = ((detail.get('shipmentCharges') or {}).get('total') or {}).get('value')
            if total in (None, ''):
                if status.get('message'):
                    raise UserError(_('TForce: %s', status['message']))
                continue
            rates.append({
                'service': (detail.get('service') or {}).get('description'),
                'total': float(total),
                'transit_days': self._tforce_transit_days(detail),
                'quote_number': quote_number,
                'charges': self._tforce_charges(detail),
                'alerts': [a.get('message') for a in detail.get('alerts') or [] if a.get('message')],
            })
        if not rates:
            raise UserError(_('TForce returned no rate: %s', self._tforce_error(data)))
        return rates

    def tforce_ltl_book(self, shipment, rate):
        self.ensure_one()
        data = self._tforce_call('POST', '/shipping/bol/create', self._tforce_bol_request(shipment))
        detail = data.get('detail') or {}
        if not detail.get('pro') and not detail.get('bolId'):
            raise UserError(_('TForce did not create the BOL: %s', self._tforce_error(data)))
        pro = str(detail.get('pro') or '')
        if pro and len(pro) < 9:
            pro = pro.zfill(9)
        pickup = ((detail.get('pickup') or {}).get('transactionReference') or {})
        documents = []
        for image in ((detail.get('documents') or {}).get('image') or []):
            if image.get('data'):
                kind = 'eBOL (carrier copy)' if image.get('type') == '20' else 'labels'
                documents.append(('TForce %s %s.pdf' % (kind, pro or shipment.name), base64.b64decode(image['data'])))
        notes = []
        for rate_detail in detail.get('rateDetail') or []:
            total = ((rate_detail.get('shipmentCharges') or {}).get('total') or {}).get('value')
            if total not in (None, '') and shipment.quoted_amount and abs(float(total) - shipment.quoted_amount) > 0.5:
                notes.append(_('TForce priced the booked BOL at %(total)s, the quote was %(quote)s.',
                               total=total, quote=shipment.quoted_amount))
            for alert in rate_detail.get('alerts') or []:
                if alert.get('message'):
                    notes.append(_('TForce alert: %s', alert['message']))
        shipment.write({'tforce_bol_id': str(detail.get('bolId') or '') or False,
                        'tforce_origin_terminal': detail.get('originServiceCenter') or False})
        if notes:
            shipment.message_post(body='<br/>'.join(notes))
        if self.tforce_environment != 'production':
            shipment.message_post(body=_('Booked in the TForce TEST environment: nothing will be picked up.'))
        return {
            'pro_number': pro or False,
            'pickup_number': pickup.get('confirmationNumber') or False,
            'documents': documents,
        }

    def tforce_ltl_track(self, shipments):
        self.ensure_one()
        by_pro = {}
        for shipment in shipments:
            pro = digits_only(shipment.pro_number)
            if pro:
                by_pro[pro.zfill(9)] = shipment
        results = {}
        pros = list(by_pro)
        for start in range(0, len(pros), 25):
            data = self._tforce_call('POST', '/track/pro/multiple', {'pro': pros[start:start + 25]})
            for detail in data.get('detail') or []:
                shipment = by_pro.get(digits_only(detail.get('pro')).zfill(9))
                if not shipment:
                    continue
                current = detail.get('currentStatus') or {}
                delivery = detail.get('delivery') or {}
                info = {}
                state = TRACKING_STATE.get(current.get('code'))
                if state:
                    info['state'] = state
                status = current.get('description') or ''
                if delivery.get('signedBy'):
                    status += _(' (signed by %s)', delivery['signedBy'])
                if status:
                    info['status'] = status.strip()
                actual = (delivery.get('actual') or {}).get('date')
                if state == 'delivered' and actual:
                    info['delivered_date'] = actual[:10]
                results[shipment.id] = info
        return results

    def tforce_ltl_documents(self, shipment):
        self.ensure_one()
        pro = digits_only(shipment.pro_number)
        if not pro:
            raise UserError(_('%s has no PRO yet.', shipment.name))
        data = self._tforce_call('POST', '/documents/pro', {
            'pro': pro.zfill(9), 'documentCategories': DOCUMENT_CATEGORIES})
        documents = []
        existing = set(self.env['ir.attachment'].search([
            ('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name'))
        for detail in data.get('detail') or []:
            if not detail.get('data'):
                continue
            category = detail.get('category') or (detail.get('documentType') or {}).get('name') or 'DOC'
            name = '%s %s %s.pdf' % (DOCUMENT_NAMES.get(category, category), pro, detail.get('id') or '')
            name = ' '.join(name.split())
            if name in existing:
                continue
            documents.append((name, base64.b64decode(detail['data'])))
        return documents

    # ------------------------------------------------------------------ Odoo delivery hooks

    def tforce_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('TForce rates come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def tforce_send_shipping(self, pickings):
        # Booking happens on the LTL shipment; validating the delivery books nothing.
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def tforce_get_tracking_link(self, picking):
        # TForce's public tracking page; the PRO is typed there.
        return 'https://www.tforcefreight.com/ltl/apps/tracking' if picking.carrier_tracking_ref else False

    def tforce_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the pickup with TForce, then cancel the LTL shipment in Odoo.'))

    def action_tforce_test_connection(self):
        self.ensure_one()
        self.sudo().write({'tforce_access_token': False, 'tforce_token_expiry': False})
        self._tforce_token()
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _('Signed in to TForce (%s).', self._tforce_version())},
        }
