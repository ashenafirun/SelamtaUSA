# -*- coding: utf-8 -*-
"""Daylight Transport ship-daylight API (spec "Daylight Transport Shipping APIs" 1.0.3,
host api.dylt.com, portal dylt-portalapi.apigee.io).

* Sign-in: OAuth2 client credentials (client ID and secret of an app with the
  ship-daylight product) at /oauth/client_credential/accesstoken; the token goes in an
  "Authorization: Bearer" header. On top of that, rate quotes, pickups and images carry the
  MyDaylight username, password and account number (in the body for POSTs, as query
  parameters for GETs).
* POST /rateQuote  {"dyltRateQuoteReq": {...}} -> flat response (success YES/NO,
  quoteNumber, totalCharges...). No dimensions: weight, pieces, pallets and class.
* POST /pickup  {"dyltPickupReqs": {"dyltPickupReq": {...}}} -> {"dyltPickupResp":
  {reservationStatus A/D/P, bookingNumber, reason}}. No PRO: Daylight assigns it at pickup.
* GET /externalTrace/{probill}, /externalTrace/booking/{bookingNumber} -> billNumber,
  currentStatus, actualDeliveryDate, statHistArr.
* GET /image/{probill}/{dr|wic|bol|invoice}/pdf, /image/booking/{bookingNumber}/bol.

Daylight offers no test system for customers: a pickup booked through the API is a real pickup, so booking is
off until it is switched on on the shipping method.
"""
import json
import logging
import re
from datetime import date, timedelta

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

API_HOST = 'https://api.dylt.com'
TOKEN_URL = API_HOST + '/oauth/client_credential/accesstoken'
PUBLIC_TRACKING_URL = 'https://mydaylight.dylt.com/external/shipment?probill=%s'
TIMEOUT = 45
MAX_WEIGHT = 15000         # per rate quote / pickup item
MAX_PALLETS_PER_ITEM = 10  # rate quote limit
MAX_NOTE = 100             # pickup note line
RATE_DATE_BUSINESS_DAYS = 4
DOCUMENT_TYPES = [('dr', 'Delivery receipt'), ('wic', 'Weight and inspection')]
NO_DAYLIGHT_CODE = '-'     # Daylight code meaning "Daylight has no such charge"


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('daylight', 'Daylight Transport')],
        ondelete={'daylight': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    dylt_client_id = fields.Char(
        'Daylight client ID', groups='base.group_system', copy=False,
        help='Consumer key of your app on dylt-portalapi.apigee.io (My Apps), with the '
             'ship-daylight product added.')
    dylt_client_secret = fields.Char('Daylight client secret', groups='base.group_system', copy=False)
    dylt_access_token = fields.Char(groups='base.group_system', copy=False, readonly=True)
    dylt_token_expiry = fields.Datetime(groups='base.group_system', copy=False, readonly=True)
    dylt_account_number = fields.Char(
        'Daylight account number', help='Our Daylight account: "Account No." on Daylight invoices.')
    dylt_username = fields.Char('MyDaylight username', groups='base.group_system', copy=False)
    dylt_password = fields.Char('MyDaylight password', groups='base.group_system', copy=False)
    dylt_book_pickups = fields.Boolean(
        'Book pickups through the API',
        help='Daylight offers no test system for customers: with this on, choosing Daylight in the rate shop '
             'schedules a real pickup. With it off, the quote is saved and the pickup is booked '
             'on MyDaylight.')
    dylt_contact_name = fields.Char('Daylight pickup contact', help='Shipper contact on the pickup request.')
    dylt_contact_phone = fields.Char('Daylight pickup contact phone')

    # ------------------------------------------------------------------ connection

    def ltl_can(self, operation):
        self.ensure_one()
        if self.delivery_type == 'daylight' and operation == 'book' and not self.dylt_book_pickups:
            return False
        return super().ltl_can(operation)

    def _dylt_login(self):
        """MyDaylight account, username and password (sent with rate, pickup and image calls)."""
        self.ensure_one()
        carrier = self.sudo()
        account = (carrier.dylt_account_number or '').strip()
        if not account or not carrier.dylt_username or not carrier.dylt_password:
            raise UserError(_(
                'Enter the Daylight account number and MyDaylight username and password on the %s '
                'shipping method (Daylight tab) first.', carrier.name))
        return account, carrier.dylt_username.strip(), carrier.dylt_password

    @api.model
    def _dylt_json(self, response):
        try:
            return response.json() if response.content else {}
        except ValueError:
            return {}

    @api.model
    def _dylt_request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', TIMEOUT)
        _logger.info('Daylight %s %s', method, url.split('?')[0])
        try:
            return requests.request(method, url, **kwargs)
        except requests.RequestException as error:
            raise UserError(_('Could not reach Daylight: %s', error)) from error

    def _dylt_token(self):
        self.ensure_one()
        carrier = self.sudo()
        now = fields.Datetime.now()
        if carrier.dylt_access_token and carrier.dylt_token_expiry and carrier.dylt_token_expiry > now:
            return carrier.dylt_access_token
        if not carrier.dylt_client_id or not carrier.dylt_client_secret:
            raise UserError(_(
                'Enter the Daylight client ID and client secret on the %s shipping method first.',
                carrier.name))
        client_id, secret = carrier.dylt_client_id.strip(), carrier.dylt_client_secret.strip()
        # Apigee client-credentials endpoint: credentials as Basic auth, and as form fields
        # for proxies set up to read them there.
        response = self._dylt_request(
            'POST', TOKEN_URL, params={'grant_type': 'client_credentials'},
            data={'client_id': client_id, 'client_secret': secret}, auth=(client_id, secret))
        data = self._dylt_json(response)
        if response.status_code != 200 or not data.get('access_token'):
            raise UserError(_(
                'Daylight refused the sign-in (%(status)s): %(message)s. Check the client ID and '
                'client secret.', status=response.status_code,
                message=self._dylt_error(data, response)))
        try:
            lifetime = int(float(data.get('expires_in') or 3600))
        except (TypeError, ValueError):
            lifetime = 3600
        carrier.write({
            'dylt_access_token': data['access_token'],
            'dylt_token_expiry': now + timedelta(seconds=max(lifetime - 300, 60)),
        })
        return data['access_token']

    @api.model
    def _dylt_error(self, data, response=None):
        messages = []
        if isinstance(data, dict):
            info = data.get('errorInformation') or {}
            if isinstance(info, dict) and info.get('errorMessage'):
                messages.append(info['errorMessage'])
            for key in ('message', 'reason', 'error_description', 'error'):
                if isinstance(data.get(key), str) and data[key]:
                    messages.append(data[key])
            fault = data.get('fault') or {}
            if isinstance(fault, dict) and fault.get('faultstring'):
                messages.append(fault['faultstring'])
        if not messages and isinstance(data, dict) and data:
            # Not in a field we know: show Daylight's own answer (passwords hidden).
            messages.append(json.dumps(self._dylt_masked(data), separators=(',', ':'))[:400])
        if not messages and response is not None:
            messages.append(self._dylt_mask_text(response.text or '')[:300])
        return '; '.join(m for m in messages if m) or _('no details')

    @api.model
    def _dylt_masked(self, data):
        """Copy of a request or answer with passwords and secrets replaced by ***."""
        if isinstance(data, dict):
            return {key: '***' if re.search(r'pass|secret|token', str(key), re.I) and value else self._dylt_masked(value)
                    for key, value in data.items()}
        if isinstance(data, list):
            return [self._dylt_masked(value) for value in data]
        return data

    @api.model
    def _dylt_mask_text(self, text):
        return re.sub(r'(?i)("?[a-z_]*(?:pass|secret|token)[a-z_]*"?\s*[:=]\s*)"[^"]*"', r'\1"***"', text)

    @api.model
    def _dylt_unwrap(self, data):
        """The spec shows a flat rate answer; accept it wrapped in one object too
        ({"dyltRateQuoteResp": {...}})."""
        if isinstance(data, dict) and 'success' not in data and 'totalCharges' not in data:
            for key in ('dyltRateQuoteResp', 'dyltRateQuoteResponse', 'rateQuoteResp', 'response', 'data'):
                if isinstance(data.get(key), dict):
                    return data[key]
            if len(data) == 1 and isinstance(next(iter(data.values())), dict):
                return next(iter(data.values()))
        return data

    def _dylt_call(self, method, path, payload=None, params=None, retry=True, binary=False):
        """Call the ship-daylight API. Returns the JSON, or the raw response for binary=True."""
        self.ensure_one()
        headers = {'Authorization': 'Bearer %s' % self._dylt_token(), 'Accept': 'application/json'}
        if binary:
            headers['Accept'] = 'application/pdf, application/json'
        response = self._dylt_request(method, API_HOST + path, json=payload, params=params, headers=headers)
        if response.status_code == 401 and retry:
            self.sudo().write({'dylt_access_token': False, 'dylt_token_expiry': False})
            return self._dylt_call(method, path, payload, params, retry=False, binary=binary)
        if binary:
            return response
        data = self._dylt_json(response)
        if response.status_code >= 400:
            raise UserError(_('Daylight answered %(status)s: %(message)s',
                              status=response.status_code, message=self._dylt_error(data, response)))
        return data

    # ------------------------------------------------------------------ request parts

    @api.model
    def _dylt_zip(self, partner):
        if (partner.country_id.code or 'US') != 'US':
            raise UserError(_('Daylight rates and pickups through the API are for US addresses (%s).',
                              partner.display_name))
        postal = digits_only(partner.zip)[:5]
        if len(postal) != 5:
            raise UserError(_('%s needs a 5-digit ZIP code for Daylight.', partner.display_name))
        return postal

    @api.model
    def _dylt_phone(self, value, label):
        phone = digits_only(value)
        if len(phone) == 11 and phone.startswith('1'):
            phone = phone[1:]
        if len(phone) < 10:
            raise UserError(_('Daylight needs a 10-digit phone number for the %s.', label))
        return phone[:10]

    @api.model
    def _dylt_company_name(self, partner):
        return (partner.commercial_partner_id.name if partner.parent_id else partner.name) or ''

    @api.model
    def _dylt_customer(self, partner, account=None):
        info = {
            'customerName': self._dylt_company_name(partner)[:60],
            'customerAddress': {
                'streetAddress': (partner.street or '')[:60],
                'city': (partner.city or '')[:30],
                'state': partner.state_id.code or '',
                'zip': self._dylt_zip(partner),
            },
        }
        if partner.street2:
            info['customerAddress']['aptAddress'] = partner.street2[:60]
        if account:
            info['customerNumber'] = account
        return info

    @api.model
    def _dylt_units(self, shipment):
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the pallets or boxes to %s first.', shipment.name))
        for unit in units:
            if not unit.freight_class or not unit.weight:
                raise UserError(_('Measure and weigh every pallet or box on %s first.', shipment.name))
            if unit.weight > MAX_WEIGHT:
                raise UserError(_('Daylight takes at most %(max)s lb per line (%(name)s).',
                                  max=MAX_WEIGHT, name=shipment.name))
            if unit.unit_type == 'pallet' and unit.quantity > MAX_PALLETS_PER_ITEM:
                raise UserError(_('Daylight takes at most %s pallets per line; split the line.',
                                  MAX_PALLETS_PER_ITEM))
        return units

    @api.model
    def _dylt_items(self, shipment):
        items = []
        for unit in self._dylt_units(shipment):
            text = unit.description or _('Freight')
            if shipment.consolidated and unit.for_text:
                text = '%s - for %s' % (text, unit.for_text)
            item = {
                'description': text[:60],
                'pcs': unit.quantity,
                'pallets': unit.quantity if unit.unit_type == 'pallet' else 0,
                'weight': round(unit.weight),
                'actualClass': unit.freight_class,
            }
            if unit.nmfc_item:
                item['nmfcNumber'] = unit.nmfc_item
                if unit.nmfc_sub:
                    item['nmfcSubNumber'] = unit.nmfc_sub
            items.append(item)
        return items

    @api.model
    def _dylt_accessorials(self, shipment):
        """(Daylight accessorial list, names of services that have no Daylight code)."""
        accessorials, missing = [], []
        for service in shipment.accessorial_ids:
            if not service.dylt_code:
                missing.append(service.name)
                continue
            if service.dylt_code.strip() == NO_DAYLIGHT_CODE:
                continue  # Daylight has no such charge; it is printed on our BOL only
            accessorials.append({
                'accName': 'P' if service.code.endswith('_PU') else 'D',
                'accId': service.dylt_code.strip(),
            })
        return accessorials, missing

    @api.model
    def _dylt_add_business_days(self, start, days):
        current = start
        while days > 0:
            current += timedelta(days=1)
            if current.weekday() < 5:
                days -= 1
        return current

    def _dylt_rate_request(self, shipment):
        account, username, password = self._dylt_login()
        request = {
            'accountNumber': account,
            'userName': username,
            'password': password,
            'billTerms': 'PP',
            'serviceType': 'LTL',
            'shipperInfo': self._dylt_customer(shipment.shipper_id, account=account),
            'consigneeInfo': self._dylt_customer(shipment.partner_id),
            'items': {'item': self._dylt_items(shipment)},
        }
        today = fields.Date.context_today(self)
        ship_date = shipment.ship_date
        # Daylight quotes only for pickups within 4 business days; later pickups are quoted
        # without a date (today's pricing).
        if ship_date and today <= ship_date <= self._dylt_add_business_days(today, RATE_DATE_BUSINESS_DAYS):
            request['pickupDate'] = fields.Date.to_string(ship_date)
        accessorials, _missing = self._dylt_accessorials(shipment)
        if accessorials:
            request['accessorials'] = {'accessorial': accessorials}
        return {'dyltRateQuoteReq': request}

    @api.model
    def _dylt_time(self, hours):
        """10.5 -> '10:30:00'."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        return '%02d:%02d:00' % (min(hour, 23), minute)

    def _dylt_pickup_request(self, shipment):
        account, username, password = self._dylt_login()
        accessorials, missing = self._dylt_accessorials(shipment)
        if missing:
            raise UserError(_(
                'Set the Daylight code of %s (Inventory > Configuration > LTL services) before '
                'booking with Daylight; otherwise Daylight would not know it was ordered.',
                ', '.join(missing)))
        shipper, consignee = shipment.shipper_id, shipment.partner_id
        for partner, label in ((shipper, _('shipper')), (consignee, _('consignee'))):
            if not partner.street or not partner.city or not partner.state_id:
                raise UserError(_('%(name)s needs a street, city and state for a Daylight pickup (%(label)s).',
                                  name=partner.display_name, label=label))
        day = fields.Date.to_string(shipment.ship_date or fields.Date.context_today(self))
        request = {
            'accountNumber': account,
            'userName': username,
            'password': password,
            'shipmentID': shipment.bol_reference,
            'billTerms': 'PP',
            'serviceType': 'LTL',
            'shipperName': self._dylt_company_name(shipper)[:60],
            'shipperAddress1': shipper.street[:60],
            'shipperCity': shipper.city[:30],
            'shipperState': shipper.state_id.code,
            'shipperZip': self._dylt_zip(shipper),
            'shipperContactName': (self.dylt_contact_name or self.env.user.name or '')[:60],
            'shipperContactNumber': self._dylt_phone(
                self.dylt_contact_phone or shipper.phone or shipment.company_id.phone, _('shipping contact')),
            'consigneeName': self._dylt_company_name(consignee)[:60],
            'consigneeAddress1': consignee.street[:60],
            'consigneeCity': consignee.city[:30],
            'consigneeState': consignee.state_id.code,
            'consigneeZip': self._dylt_zip(consignee),
            'consigneeContactName': ((consignee.name if consignee.parent_id else False) or _('Receiving'))[:60],
            'consigneeContactNumber': self._dylt_phone(
                consignee.phone or consignee.mobile or consignee.commercial_partner_id.phone,
                _('consignee (%s)', consignee.display_name)),
            'pickupStartDate': day,
            'pickupStartTime': self._dylt_time(shipment.pickup_ready_time),
            'pickupEndDate': day,
            'pickupEndTime': self._dylt_time(shipment.pickup_close_time),
            'items': {'item': self._dylt_items(shipment)},
        }
        if shipper.street2:
            request['shipperAddress2'] = shipper.street2[:60]
        if consignee.street2:
            request['consigneeAddress2'] = consignee.street2[:60]
        lines = shipment._bol_delivery_lines()
        if shipment.pickup_instructions:
            lines.append('PICKUP: %s' % ' '.join(shipment.pickup_instructions.split()))
        if lines:
            request['notes'] = {'note': ', '.join(lines)[:MAX_NOTE]}
        if accessorials:
            request['accessorials'] = {'accessorial': accessorials}
        request['shipReferences'] = {'shipReference': self._dylt_references(shipment)}
        return {'dyltPickupReqs': {'dyltPickupReq': request}}

    @api.model
    def _dylt_references(self, shipment):
        """Reference Matrix: B bill of lading, Q quote number (Daylight asks for it on the
        pickup), P purchase order, R shipper's reference (our sales order)."""
        references, seen = [], set()

        def add(kind, number):
            number = (number or '').strip()
            if number and (kind, number) not in seen:
                seen.add((kind, number))
                references.append({'referenceType': kind, 'referenceNumber': number[:30]})

        add('B', shipment.bol_reference)
        if shipment.carrier_id == self and shipment.quote_source == 'api':
            add('Q', shipment.quote_number)
        for picking in shipment.picking_ids:
            sale = picking.sale_id if 'sale_id' in picking._fields else False
            add('P', sale.client_order_ref if sale else False)
            add('R', picking.origin)
        return references

    # ------------------------------------------------------------------ responses

    @api.model
    def _dylt_list(self, value):
        """The spec types several lists as single objects; accept both."""
        if not value:
            return []
        return value if isinstance(value, list) else [value]

    @api.model
    def _dylt_number(self, value):
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _dylt_date(self, value):
        value = (value or '')[:10]
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return False
        return parsed if parsed.year > 1900 else False

    @api.model
    def _dylt_business_days(self, start, end):
        if not start or not end or end <= start:
            return 0
        days, current = 0, start
        while current < end:
            current += timedelta(days=1)
            if current.weekday() < 5:
                days += 1
        return days

    def _dylt_rate_from_answer(self, data, missing=None):
        data = self._dylt_unwrap(data)
        if str(data.get('success') or '').upper() != 'YES':
            raise UserError(_('Daylight: %s', self._dylt_error(data)))
        totals = data.get('totalCharges') or {}
        net = self._dylt_number(totals.get('netCharge'))
        if net <= 0:
            raise UserError(_('Daylight returned no rate: %s', self._dylt_error(data)))
        items = self._dylt_list((data.get('itemCharges') or {}).get('itemCharge'))
        discount_pct = next((self._dylt_number(i.get('discountPct')) for i in items if i.get('discountPct')), 0.0)
        charges = []
        gross = self._dylt_number(totals.get('grossCharge'))
        if gross:
            charges.append({'code': 'GROSS', 'name': _('Linehaul before discount'), 'amount': gross})
        discount = self._dylt_number(totals.get('discountAmt'))
        if discount:
            name = _('Discount (%s%%)', ('%g' % discount_pct)) if discount_pct else _('Discount')
            charges.append({'code': 'DISCOUNT', 'name': name, 'amount': -abs(discount)})
        accessorial_lines = self._dylt_list((data.get('accessorialCharges') or {}).get('accessorialCharge'))
        for line in accessorial_lines:
            amount = self._dylt_number(line.get('accCharge'))
            if amount:
                code = line.get('reqAccessorial') or 'ACC'
                charges.append({'code': code, 'name': self._dylt_accessorial_name(code), 'amount': amount})
        if not accessorial_lines and self._dylt_number(totals.get('totalAccessorial')):
            charges.append({'code': 'ACC', 'name': _('Accessorials'),
                            'amount': self._dylt_number(totals.get('totalAccessorial'))})
        fuel = self._dylt_number(totals.get('fuelSurcharge'))
        if fuel:
            charges.append({'code': 'FUEL', 'name': _('Fuel surcharge'), 'amount': fuel})
        if charges:
            difference = round(net - sum(c['amount'] for c in charges), 2)
            if abs(difference) >= 0.01:
                charges.append({'code': 'OTHER', 'name': _('Other (difference to Daylight total)'),
                                'amount': difference})
        pickup = self._dylt_date(data.get('pickupDate')) or fields.Date.context_today(self)
        delivery = self._dylt_date(data.get('earliestDeliveryDate'))
        service = _('Daylight LTL')
        if missing:
            service = _('Daylight LTL - NOT INCLUDED: %s (no Daylight code)', ', '.join(missing))
        return {
            'service': service,
            'total': net,
            'transit_days': self._dylt_business_days(pickup, delivery),
            'quote_number': str(data.get('quoteNumber') or '') or False,
            'charges': charges,
        }

    def _dylt_accessorial_name(self, code):
        service = self.env['selamta.ltl.accessorial'].with_context(active_test=False).search(
            [('dylt_code', '=ilike', code)], limit=1)
        return service.name or code

    # ------------------------------------------------------------------ selamta_ltl hooks

    def daylight_ltl_rate(self, shipment):
        self.ensure_one()
        _accessorials, missing = self._dylt_accessorials(shipment)
        data = self._dylt_call('POST', '/rateQuote', self._dylt_rate_request(shipment))
        return [self._dylt_rate_from_answer(data, missing)]

    def dylt_raw_rate_answer(self, shipment_id=False):
        """Request and Daylight's full rate answer (passwords hidden) for a shipment or a sample
        from our dock, as text, to check what Daylight sends. Administrators only; books nothing."""
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only administrators can see raw Daylight answers.'))
        shipment = self.env['selamta.ltl.shipment'].browse(shipment_id) if shipment_id else self._dylt_sample_shipment()
        request = self._dylt_rate_request(shipment)
        response = self._dylt_request('POST', API_HOST + '/rateQuote', json=request, headers={
            'Authorization': 'Bearer %s' % self._dylt_token(), 'Accept': 'application/json'})
        return json.dumps({'request': self._dylt_masked(request), 'status': response.status_code,
                           'answer': self._dylt_masked(self._dylt_json(response))
                           or self._dylt_mask_text(response.text or '')[:2000]}, indent=1)

    def _dylt_sample_shipment(self):
        shipper = self.env.company.partner_id
        return self.env['selamta.ltl.shipment'].new({
            'shipper_id': shipper.id, 'partner_id': shipper.id, 'carrier_id': self.id,
            'ship_date': fields.Date.context_today(self),
            'unit_ids': [(0, 0, {'unit_type': 'pallet', 'quantity': 1, 'length': 48, 'width': 40,
                                 'height': 48, 'weight': 500, 'class_override': '70'})],
        })

    def daylight_ltl_book(self, shipment, rate):
        self.ensure_one()
        if not self.dylt_book_pickups:
            raise UserError(_('Booking through the Daylight API is off on %s; book the pickup on '
                              'MyDaylight and type the PRO.', self.name))
        data = self._dylt_call('POST', '/pickup', self._dylt_pickup_request(shipment))
        answer = data.get('dyltPickupResp') or (data.get('dyltPickupResps') or {}).get('dyltPickupResp') or data
        status = str(answer.get('reservationStatus') or '').upper()
        booking = str(answer.get('bookingNumber') or '').strip()
        if status == 'D' or not booking:
            raise UserError(_('Daylight declined the pickup: %s',
                              answer.get('reason') or self._dylt_error(data)))
        reservation = _('Accepted') if status == 'A' else _('Adjusted: %s', answer.get('reason') or '-')
        shipment.dylt_reservation = reservation
        notes = [_('Daylight booking number %(booking)s (%(status)s). Daylight assigns the PRO at '
                   'pickup; tracking fills it in.', booking=booking, status=reservation)]
        if rate.get('quote_number'):
            notes.append(_('Quote %s: give it to Daylight if the bill differs.', rate['quote_number']))
        shipment.message_post(body=Markup('<br/>').join(notes))
        documents = []
        try:
            _account, username, password = self._dylt_login()
            response = self._dylt_call('GET', '/image/booking/%s/bol' % booking,
                                       params={'userName': username, 'password': password}, binary=True)
            if response.status_code == 200 and (response.content or b'')[:4] == b'%PDF':
                documents.append(('Daylight BOL (carrier copy) %s.pdf' % booking, response.content))
        except UserError as error:
            _logger.warning('Daylight BOL for booking %s not fetched: %s', booking, error)
        return {'pickup_number': booking, 'documents': documents}

    def daylight_ltl_track(self, shipments):
        self.ensure_one()
        results = {}
        for shipment in shipments:
            pro = digits_only(shipment.pro_number)
            booking = digits_only(shipment.pickup_number)
            if pro:
                path = '/externalTrace/%s' % pro
            elif booking:
                path = '/externalTrace/booking/%s' % booking
            else:
                continue
            try:
                data = self._dylt_call('GET', path)
            except UserError as error:
                _logger.warning('Daylight tracking failed for %s: %s', shipment.name, error)
                continue
            if data.get('externalTraceResp'):
                data = data['externalTraceResp']
            results[shipment.id] = self._dylt_tracking_info(shipment, data)
        return results

    @api.model
    def _dylt_tracking_info(self, shipment, data):
        info = {}
        bill = str(data.get('billNumber') or '').strip()
        if bill and bill != '0' and not shipment.pro_number:
            info['pro_number'] = bill
        delivered = self._dylt_date(data.get('actualDeliveryDate'))
        if delivered:
            info['state'] = 'delivered'
            info['delivered_date'] = fields.Date.to_string(delivered)
        elif bill and bill != '0':
            info['state'] = 'in_transit'
        status = (data.get('currentStatus') or '').strip()
        expected = self._dylt_date(data.get('expectedDeliveryDate'))
        if expected and not delivered:
            status = _('%(status)s, expected %(date)s', status=status or _('In transit'),
                       date=expected.strftime('%m/%d/%Y'))
        if status:
            info['status'] = status
        return info

    def daylight_ltl_documents(self, shipment):
        self.ensure_one()
        pro = digits_only(shipment.pro_number)
        if not pro:
            raise UserError(_('%s has no PRO yet.', shipment.name))
        _account, username, password = self._dylt_login()
        existing = set(self.env['ir.attachment'].search([
            ('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name'))
        documents = []
        for doc_type, label in DOCUMENT_TYPES:
            name = '%s %s.pdf' % (label, pro)
            if name in existing:
                continue
            response = self._dylt_call('GET', '/image/%s/%s/pdf' % (pro, doc_type),
                                       params={'userName': username, 'password': password}, binary=True)
            if response.status_code == 200 and (response.content or b'')[:4] == b'%PDF':
                documents.append((name, response.content))
        return documents

    # ------------------------------------------------------------------ Odoo delivery hooks

    def daylight_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('Daylight rates come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def daylight_send_shipping(self, pickings):
        # Booking happens on the LTL shipment; validating the delivery books nothing.
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def daylight_get_tracking_link(self, picking):
        pro = digits_only(picking.carrier_tracking_ref)
        return PUBLIC_TRACKING_URL % pro if pro else False

    def daylight_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the pickup with Daylight, then cancel the LTL shipment in Odoo.'))

    def action_dylt_test_connection(self):
        """Sign in to Daylight and get a sample quote from our dock to itself (500 lb,
        class 70). Books nothing."""
        self.ensure_one()
        self.sudo().write({'dylt_access_token': False, 'dylt_token_expiry': False})
        shipment = self._dylt_sample_shipment()
        rate = self._dylt_rate_from_answer(self._dylt_call('POST', '/rateQuote', self._dylt_rate_request(shipment)))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _(
                'Signed in to Daylight as account %(account)s. Sample quote %(quote)s: %(total).2f.',
                account=self.dylt_account_number, quote=rate['quote_number'] or '-', total=rate['total'])},
        }
