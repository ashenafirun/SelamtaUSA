# -*- coding: utf-8 -*-
"""XPO LTL REST APIs (xpo.com/help-center/api: Rating, BOL, Pickup Request, Shipment Tracking
and Imaging implementation guides).

Login: POST {host}/token with ``Authorization: Basic <key from XPO>`` (base64 of the consumer
key and secret) and the form fields grant_type=password, username and password (the
ltl.xpo.com user) -> access_token (12 hours), expires_in. Every API call then sends
``Authorization: Bearer <access_token>``. Answers are {"code", "transactionTimestamp", "data"};
errors carry "error" {errorCode, message, moreInfo [{message, location}]}. Money is
{"amt", "currencyCd"}; dates are epoch milliseconds (UTC).

* Rate quote: POST /rating/1.0/ratequotes {"shipmentInfo": {paymentTermCd, shipmentDate,
  shipper {acctInstId, address.postalCd}, consignee {address.postalCd}, bill2Party
  {acctInstId, acctMadCd, address.postalCd}, commodity [1-20] {pieceCnt, packageCode,
  grossWeight {weight, weightUom}, nmfcClass, hazmatInd, dimensions {length, width, height,
  dimensionsUom}}, accessorials [{accessorialCd}], palletCnt}} -> data.rateQuote
  {confirmationNbr, totCharge [{amt}], totDiscountAmt, deficitRatingInfo.deficitAmt,
  shipmentInfo.commodity[].charge.chargeAmt, shipmentInfo.accessorials[] {accessorialCd,
  accessorialDesc, chargeAmt}, shipmentInfo.totCommodityCharge}, data.transitTime
  {transitDays, estdDlvrDate, garntInd, origSicCd}. Accessorial GUR prices guaranteed service.
* BOL with pickup: POST /billoflading/1.0/billsoflading?testMode=N|Y {"bol": {requester,
  shipper, consignee, billToCust {address, contactInfo}, commodityLine [{pieceCnt,
  packaging.packageCd, grossWeight.weight, desc, nmfcClass, nmfcItemCd, hazmatInd}],
  chargeToCd, additionalService [{accsrlCode, prepaidOrCollect}], suppRef, remarks,
  pickupInfo {pkupDate, pkupTime, dockCloseTime, contact}}, "autoAssignPro": true}
  -> data.bolInfo {bolInstId, pkupTrmnlSic, pkupCallDate, pkupCallSeq}. The PRO comes from
  GET /billsoflading/{bolInstId}/requester; the PDF from GET /billsoflading/{bolInstId}/pdf;
  PUT /billsoflading/{bolInstId}/cancel cancels the BOL and its pickup.
* Pickup cancel (pickups made another way): PUT /pickuprequest/1.0/pickuprequests/{nbr}/cancel
  ?testMode=N {confirmationNbr, cancelReason}.
* Tracking: GET /tracking/1.0/shipments/shipment-status-details?referenceNumbers=.. (repeated)
  -> data.shipmentStatusDtls [{proNbr, pkupDate, estdDlvrDate, finalDlvrDate, dlvrSigNameTxt,
  shipmentStatus {statusCd, reason, description}}].
* Documents: GET /imaging/1.0/shipments/{pro}/imaged-docs?imageType=DR&imageFormat=PDF
  &multiPartResp=false -> data.imagedDocument [{imageFiles [{base64Data}]}].
The guides' samples use https://api.ltl.xpo.com; XPO's setup email (30 Oct 2026) gives
https://api.xpo.com, so the host is a setting.
"""
import base64
import hashlib
import logging
import re
import time
from datetime import datetime, time as dt_time, timezone

import pytz
import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.pdf import merge_pdf

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

TIMEOUT = 45
MAX_LINES = 20
TRACK_BATCH = 10
DEFAULT_TZ = 'America/New_York'
# Our accessorial codes -> XPO accessorial codes (same codes for rating and BOLs).
ACCESSORIALS = {
    'LIFTGATE_DEL': 'DLG',
    'RESIDENTIAL_DEL': 'RSD',
    'LIMITED_ACCESS_DEL': 'DLA',
    'INSIDE_DEL': 'DID',
    'APPOINTMENT_DEL': 'APT',
    'NOTIFY_DEL': 'DNC',
    'LIFTGATE_PU': 'OLG',
}
GUARANTEED = 'GUR'
PACKAGE_CODES = {'pallet': 'PLT', 'box': 'BOX'}
DOCUMENT_TYPES = [
    ('DR', 'Delivery receipt'),
    ('WI', 'Weight certificate'),
]
# Shipment status codes (tracking guide).
DELIVERED_CODES = {'20', '23'}
CANCELLED_CODES = {'26'}
NOT_PICKED_UP_CODES = {'32'}
PUBLIC_TRACKING_URL = 'https://www.xpo.com/'

# Login tokens per database, shipping method and credentials, for this worker process.
_TOKENS = {}


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('xpo', 'XPO')],
        ondelete={'xpo': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    xpo_host = fields.Selection(
        [('https://api.xpo.com', 'api.xpo.com'),
         ('https://api.ltl.xpo.com', 'api.ltl.xpo.com (older address)')],
        'XPO API address', default='https://api.xpo.com', required=True)
    xpo_environment = fields.Selection(
        [('production', 'Production'),
         ('test', 'Test mode (BOLs and pickups go to XPO\'s test system)')],
        'XPO BOLs and pickups', default='production', required=True,
        help='Rates and tracking always come from XPO production. Test mode only changes where '
             'BOLs and pickups go.')
    xpo_api_key = fields.Char(
        'XPO key', groups='base.group_system', copy=False,
        help='The key from XPO\'s API setup email (the long text after "Basic").')
    xpo_username = fields.Char(
        'XPO user ID', groups='base.group_system', copy=False,
        help='The ltl.xpo.com user that XPO set up for the API. XPO deletes users that do not '
             'log in to ltl.xpo.com at least once every 6 months.')
    xpo_password = fields.Char(
        'XPO password', groups='base.group_system', copy=False,
        help='Password of that user on ltl.xpo.com.')
    xpo_shipper_account = fields.Char(
        'XPO pickup account', help='Our XPO pickup and delivery (P&D) account number at the dock.')
    xpo_billto_account = fields.Char(
        'XPO bill-to account', help='Our XPO bill-to account number (the one that carries our pricing).')
    xpo_billto_code = fields.Char(
        'XPO bill-to code', help='Letter code of the bill-to account, like ABCDE123000.')
    xpo_show_guaranteed = fields.Boolean(
        'Show guaranteed quotes',
        help='When XPO offers guaranteed service (G!) for the lane, also list its price in the rate shop.')
    xpo_book_shipments = fields.Boolean(
        'Create BOLs through the API',
        help='With this on, choosing XPO in the rate shop creates the XPO BOL and PRO (and the '
             'pickup, if "Schedule the pickup" is on). With it off, the quote is saved and the '
             'shipment is booked on ltl.xpo.com.')
    xpo_schedule_pickup = fields.Boolean(
        'Schedule the pickup with the BOL', default=True,
        help='Send a pickup request for the shipment\'s pickup date, ready and close times with the BOL.')
    xpo_contact_name = fields.Char('XPO pickup contact')
    xpo_contact_phone = fields.Char('XPO pickup contact phone')
    xpo_contact_email = fields.Char('XPO pickup contact email')

    # ------------------------------------------------------------------ connection

    def ltl_can(self, operation):
        self.ensure_one()
        if self.delivery_type == 'xpo' and operation == 'book' and not self.xpo_book_shipments:
            return False
        return super().ltl_can(operation)

    def _xpo_credentials(self):
        self.ensure_one()
        carrier = self.sudo()
        key = re.sub(r'^\s*basic\s+', '', carrier.xpo_api_key or '', flags=re.I).strip()
        user = (carrier.xpo_username or '').strip()
        password = carrier.xpo_password or ''
        if not key or not user or not password:
            raise UserError(_('Enter the XPO key, user ID and password on the %s shipping method (XPO tab) first.',
                              self.name))
        return key, user, password

    def _xpo_token(self, renew=False):
        """XPO access token for this shipping method, kept until shortly before it expires."""
        self.ensure_one()
        key, user, password = self._xpo_credentials()
        digest = hashlib.sha256(('%s\n%s\n%s\n%s' % (self.xpo_host, key, user, password)).encode()).hexdigest()
        cache_key = (self.env.cr.dbname, self.id, digest)
        cached = _TOKENS.get(cache_key)
        if cached and not renew and cached[1] > time.time():
            return cached[0]
        url = '%s/token' % self.xpo_host
        _logger.info('XPO POST %s', url)
        try:
            response = requests.request('POST', url, timeout=TIMEOUT, headers={
                'Authorization': 'Basic %s' % key,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            }, data={'grant_type': 'password', 'username': user, 'password': password})
        except requests.RequestException as error:
            raise UserError(_('Could not reach XPO: %s', error)) from error
        data = self._xpo_json(response)
        token = data.get('access_token')
        if response.status_code >= 400 or not token:
            detail = data.get('error_description') or data.get('error') or data.get('message') \
                or (response.text or '').strip()[:200] or response.status_code
            raise UserError(_('XPO refused the login (%(detail)s). Check the key, user ID and password on the '
                              '%(name)s shipping method; the password is the one for ltl.xpo.com.',
                              detail=detail, name=self.name))
        try:
            lifetime = int(data.get('expires_in') or 3600)
        except (TypeError, ValueError):
            lifetime = 3600
        _TOKENS[cache_key] = (token, time.time() + max(lifetime - 300, 60))
        return token

    @api.model
    def _xpo_json(self, response):
        try:
            data = response.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _xpo_request(self, method, path, params=None, json=None, test_mode=None):
        """Send an API call with the access token (renewed once if XPO says it expired)."""
        self.ensure_one()
        url = '%s/%s' % (self.xpo_host, path)
        params = list((params or {}).items()) if isinstance(params, dict) else list(params or [])
        if test_mode is not None:
            params.append(('testMode', 'Y' if test_mode else 'N'))
        _logger.info('XPO %s %s', method, url)
        response = None
        for attempt in range(2):
            headers = {'Authorization': 'Bearer %s' % self._xpo_token(renew=bool(attempt)),
                       'Accept': 'application/json'}
            if json is not None:
                headers['Content-Type'] = 'application/json'
            try:
                response = requests.request(method, url, headers=headers, params=params or None,
                                            json=json, timeout=TIMEOUT)
            except requests.RequestException as error:
                raise UserError(_('Could not reach XPO: %s', error)) from error
            if response.status_code != 401:
                break
        return response

    def _xpo_call(self, method, path, params=None, json=None, test_mode=None):
        """Call the XPO API and return the JSON answer; raise UserError with XPO's messages."""
        response = self._xpo_request(method, path, params=params, json=json, test_mode=test_mode)
        data = self._xpo_json(response)
        code = str(data.get('code') or '')
        if response.status_code >= 400 or data.get('error') or code[:1] in ('4', '5'):
            messages = self._xpo_errors(data)
            if response.status_code == 401:
                raise UserError(_('XPO refused the call (not authorized): %s',
                                  '; '.join(messages) or _('check that XPO switched this API on for our user')))
            raise UserError(_('XPO: %s', '; '.join(messages) or (response.text or '').strip()[:300]
                              or _('error %s', response.status_code)))
        if not data:
            raise UserError(_('XPO answered %(status)s without data: %(text)s',
                              status=response.status_code, text=(response.text or '').strip()[:300]))
        return data

    @api.model
    def _xpo_errors(self, data):
        error = data.get('error')
        messages = []
        if isinstance(error, dict):
            if error.get('message'):
                messages.append(str(error['message']).strip())
            for info in error.get('moreInfo') or []:
                if isinstance(info, dict) and info.get('message'):
                    text = str(info['message']).strip()
                    location = (info.get('location') or '').strip()
                    text = '%s (%s)' % (text, location) if location else text
                    if text not in messages:
                        messages.append(text)
        elif error:
            messages.append(str(data.get('error_description') or error))
        fault = data.get('fault')
        if isinstance(fault, dict) and fault.get('faultstring'):
            messages.append(fault['faultstring'])
        if not messages and data.get('message'):
            messages.append(str(data['message']))
        return messages

    @api.model
    def _xpo_amount(self, value):
        """{'amt': 541.01} or [{'amt': 541.01, 'currencyCd': 'USD'}] -> 541.01."""
        if isinstance(value, list):
            value = next((item for item in value if isinstance(item, dict)
                          and (item.get('currencyCd') or 'USD') == 'USD'), value[0] if value else {})
        if isinstance(value, dict):
            value = value.get('amt')
        try:
            return round(float(value or 0.0), 2)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _xpo_find(self, data, key):
        """First non-empty value of ``key`` anywhere in a JSON answer."""
        if isinstance(data, dict):
            if data.get(key) not in (None, '', [], {}):
                return data[key]
            values = data.values()
        elif isinstance(data, list):
            values = data
        else:
            return None
        for value in values:
            found = self._xpo_find(value, key)
            if found not in (None, '', [], {}):
                return found
        return None

    # ------------------------------------------------------------------ dates and times

    def _xpo_tz(self, partner=None):
        names = [partner and partner.tz, self.env.company.partner_id.tz, self.env.user.tz, DEFAULT_TZ]
        for name in names:
            if name:
                try:
                    return pytz.timezone(name)
                except pytz.UnknownTimeZoneError:
                    continue
        return pytz.timezone(DEFAULT_TZ)

    def _xpo_moment(self, day, hours, partner=None):
        """Shipment date and a time like 10.5 (10:30) -> aware datetime at the dock."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        return self._xpo_tz(partner).localize(datetime.combine(day, dt_time(min(hour, 23), minute)))

    @api.model
    def _xpo_iso(self, moment, millis=False):
        """'2026-11-02T10:30:00-05:00', or '2026-11-02T10:30:00.000-0500' as in the rating guide."""
        offset = moment.strftime('%z')
        text = moment.strftime('%Y-%m-%dT%H:%M:%S')
        if millis:
            return '%s.000%s' % (text, offset)
        return '%s%s:%s' % (text, offset[:3], offset[3:])

    def _xpo_date(self, value):
        """Epoch milliseconds (or an ISO date) -> date at the dock."""
        if value in (None, '', 0):
            return False
        if isinstance(value, str) and not value.strip().lstrip('-').isdigit():
            try:
                return datetime.strptime(value.strip()[:10], '%Y-%m-%d').date()
            except ValueError:
                return False
        try:
            seconds = float(value) / 1000.0
        except (TypeError, ValueError):
            return False
        if seconds <= 0:
            return False
        moment = datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(self._xpo_tz())
        return moment.date() if moment.year > 1971 else False

    # ------------------------------------------------------------------ request parts

    @api.model
    def _xpo_country(self, partner):
        code = partner.country_id.code or 'US'
        if code not in ('US', 'CA'):
            raise UserError(_('XPO ships within the United States and Canada only here (%s).', partner.display_name))
        return code

    @api.model
    def _xpo_zip(self, partner):
        if partner.country_id.code == 'CA':
            return ''.join(ch for ch in (partner.zip or '') if ch.isalnum()).upper()[:6]
        postal = digits_only(partner.zip)[:5]
        if len(postal) != 5:
            raise UserError(_('%s needs a 5-digit ZIP code for XPO.', partner.display_name))
        return postal

    @api.model
    def _xpo_phone(self, value):
        phone = digits_only(value)
        if len(phone) == 11 and phone.startswith('1'):
            phone = phone[1:]
        return '%s-%s' % (phone[:3], phone[3:10]) if len(phone) >= 10 else ''

    @api.model
    def _xpo_company_name(self, partner):
        return (partner.commercial_partner_id.name if partner.parent_id else partner.name) or ''

    def _xpo_address(self, partner, label):
        if not partner.street or not partner.city or not partner.state_id:
            raise UserError(_('%(name)s needs a street, city and state for an XPO BOL (%(label)s).',
                              name=partner.display_name, label=label))
        address = {
            'addressLine1': partner.street[:30],
            'cityName': partner.city[:30],
            'stateCd': partner.state_id.code,
            'countryCd': self._xpo_country(partner),
            'postalCd': self._xpo_zip(partner),
        }
        if partner.street2:
            address['addressLine2'] = partner.street2[:30]
        return address

    def _xpo_contact(self, partner, phone=None, email=None, name=None):
        contact = {'companyName': self._xpo_company_name(partner)[:40]}
        if name:
            contact['fullName'] = name[:40]
        phone = self._xpo_phone(phone or partner.phone or partner.mobile or partner.commercial_partner_id.phone)
        if phone:
            contact['phone'] = {'phoneNbr': phone}
        email = email or partner.email
        if email:
            contact['email'] = {'emailAddr': email[:60]}
        return contact

    @api.model
    def _xpo_units(self, shipment):
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the pallets or boxes to %s first.', shipment.name))
        for unit in units:
            if not unit.freight_class or not unit.weight:
                raise UserError(_('Measure and weigh every pallet or box on %s first.', shipment.name))
        if len(units) > MAX_LINES:
            raise UserError(_('XPO takes at most %s lines per shipment.', MAX_LINES))
        return units

    @api.model
    def _xpo_class(self, freight_class):
        try:
            return '%g' % float(freight_class)
        except (TypeError, ValueError):
            return str(freight_class or '')

    def _xpo_accessorial_codes(self, shipment):
        codes = []
        for service in shipment.accessorial_ids:
            code = ACCESSORIALS.get(service.code)
            if code and code not in codes:
                codes.append(code)
        return codes

    def _xpo_rate_request(self, shipment, guaranteed=False):
        units = self._xpo_units(shipment)
        shipper = shipment.shipper_id
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        commodities = []
        for unit in units:
            line = {
                'pieceCnt': max(int(unit.quantity or 1), 1),
                'packageCode': PACKAGE_CODES.get(unit.unit_type, 'PLT'),
                'grossWeight': {'weight': max(int(round(unit.weight)), 1), 'weightUom': 'LBS'},
                'nmfcClass': self._xpo_class(unit.freight_class),
                'hazmatInd': False,
            }
            if unit.length and unit.width and unit.height:
                line['dimensions'] = {'length': round(unit.length, 1), 'width': round(unit.width, 1),
                                      'height': round(unit.height, 1), 'dimensionsUom': 'INCH'}
            commodities.append(line)
        origin = {'address': {'postalCd': self._xpo_zip(shipper)}}
        if self.xpo_shipper_account:
            origin['acctInstId'] = self.xpo_shipper_account.strip()
        info = {
            'paymentTermCd': 'P',
            'shipmentDate': self._xpo_iso(self._xpo_moment(ship_date, shipment.pickup_ready_time or 12.0, shipper),
                                          millis=True),
            'shipper': origin,
            'consignee': {'address': {'postalCd': self._xpo_zip(shipment.partner_id)}},
            'commodity': commodities,
            'accessorials': [{'accessorialCd': code} for code in self._xpo_accessorial_codes(shipment)],
        }
        if guaranteed:
            info['accessorials'].append({'accessorialCd': GUARANTEED})
        if self.xpo_billto_account:
            bill_to = {'acctInstId': self.xpo_billto_account.strip(),
                       'address': {'postalCd': self._xpo_zip(shipment.company_id.partner_id)}}
            if self.xpo_billto_code:
                bill_to['acctMadCd'] = self.xpo_billto_code.strip()
            info['bill2Party'] = bill_to
        pallets = sum(max(int(unit.quantity or 1), 1) for unit in units if unit.unit_type == 'pallet')
        if pallets:
            info['palletCnt'] = pallets
        return {'shipmentInfo': info}

    @api.model
    def _xpo_references(self, shipment):
        po = False
        for picking in shipment.picking_ids:
            order = picking.sale_id if 'sale_id' in picking._fields else False
            po = po or (order.client_order_ref if order else False)
        return po

    def _xpo_remarks(self, shipment, rate):
        lines = list(shipment._bol_delivery_lines())
        if shipment.pickup_instructions:
            lines.append('PICKUP: %s' % ' '.join(shipment.pickup_instructions.split()))
        po = self._xpo_references(shipment)
        if po:
            lines.append('PO %s' % po)
        if rate.get('quote_number'):
            lines.append('XPO quote %s' % rate['quote_number'])
        return ', '.join(lines)[:250]

    def _xpo_bol_request(self, shipment, rate):
        units = self._xpo_units(shipment)
        company = shipment.company_id
        shipper = shipment.shipper_id
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        contact_name = self.xpo_contact_name or company.name
        contact_phone = self.xpo_contact_phone or shipper.phone or company.phone
        contact_email = self.xpo_contact_email or shipper.email or company.email
        shipper_contact = self._xpo_contact(shipper, phone=contact_phone, email=contact_email, name=contact_name)
        if not shipper_contact.get('phone'):
            raise UserError(_('XPO needs a phone number for the shipper: fill in the pickup contact phone on '
                              'the %s shipping method.', self.name))
        consignee = shipment.partner_id
        consignee_contact = self._xpo_contact(
            consignee, name=consignee.name if consignee.parent_id and consignee.name else None)
        if not consignee_contact.get('phone'):
            raise UserError(_('XPO needs a phone number for %s (consignee).', consignee.display_name))
        shipper_party = {'address': self._xpo_address(shipper, _('shipper')), 'contactInfo': shipper_contact}
        if self.xpo_shipper_account:
            shipper_party['acctInstId'] = self.xpo_shipper_account.strip()
        bol = {
            'requester': {'role': 'S'},
            'shipper': shipper_party,
            'consignee': {'address': self._xpo_address(consignee, _('consignee')),
                          'contactInfo': consignee_contact},
            'commodityLine': [],
            'chargeToCd': 'P',
            'suppRef': {'shippersRefNbr': (shipment.bol_reference or '')[:30]},
        }
        if self.xpo_billto_account:
            bol['billToCust'] = {
                'acctInstId': self.xpo_billto_account.strip(),
                'address': self._xpo_address(company.partner_id, _('bill to')),
                'contactInfo': self._xpo_contact(company.partner_id, phone=contact_phone, email=contact_email),
            }
        for unit in units:
            line = {
                'pieceCnt': max(int(unit.quantity or 1), 1),
                'packaging': {'packageCd': PACKAGE_CODES.get(unit.unit_type, 'PLT')},
                'grossWeight': {'weight': max(int(round(unit.weight)), 1)},
                'desc': (unit.description or _('Freight'))[:100],
                'nmfcClass': self._xpo_class(unit.freight_class),
                'hazmatInd': False,
            }
            if unit.nmfc_item:
                item = digits_only(unit.nmfc_item)
                sub = digits_only(unit.nmfc_sub)
                line['nmfcItemCd'] = '%s-%s' % (item, sub.zfill(2)) if item and sub else (item or unit.nmfc_item)
            bol['commodityLine'].append(line)
        codes = self._xpo_accessorial_codes(shipment)
        if rate.get('xpo_service') == GUARANTEED:
            codes.append(GUARANTEED)
        if codes:
            bol['additionalService'] = [{'accsrlCode': code, 'prepaidOrCollect': 'P'} for code in codes]
        remarks = self._xpo_remarks(shipment, rate)
        if remarks:
            bol['remarks'] = remarks
        if self.xpo_schedule_pickup:
            ready = self._xpo_moment(ship_date, shipment.pickup_ready_time, shipper)
            close = self._xpo_moment(ship_date, shipment.pickup_close_time, shipper)
            pickup_contact = {'companyName': shipper_contact['companyName'], 'fullName': contact_name[:40],
                              'phone': shipper_contact['phone']}
            if contact_email:
                pickup_contact['email'] = {'emailAddr': contact_email[:60]}
            bol['pickupInfo'] = {
                'pkupDate': self._xpo_iso(ready),
                'pkupTime': self._xpo_iso(ready),
                'dockCloseTime': self._xpo_iso(close),
                'contact': pickup_contact,
            }
        return {'bol': bol, 'autoAssignPro': True}

    # ------------------------------------------------------------------ responses

    def _xpo_rate_from_answer(self, data, guaranteed=False):
        body = data.get('data') or {}
        quote = body.get('rateQuote') or {}
        total = self._xpo_amount(quote.get('totCharge'))
        if total <= 0:
            messages = [m.get('message') for m in body.get('msgs') or [] if isinstance(m, dict) and m.get('message')]
            raise UserError(_('XPO returned no rate: %s', '; '.join(messages) or _('no details')))
        transit = body.get('transitTime') or {}
        estimated = self._xpo_date(transit.get('estdDlvrDate'))
        return {
            'service': _('XPO Guaranteed (G!)') if guaranteed else _('XPO Standard'),
            'total': total,
            'transit_days': int(transit.get('transitDays') or 0),
            'quote_number': str(quote.get('confirmationNbr') or '') or False,
            'charges': self._xpo_charge_lines(quote, total),
            'xpo_service': GUARANTEED if guaranteed else 'STD',
            'xpo_guaranteed_available': bool(transit.get('garntInd')),
            'xpo_estimated_delivery': fields.Date.to_string(estimated) if estimated else False,
            'xpo_terminal': transit.get('origSicCd') or False,
        }

    def _xpo_charge_lines(self, quote, total):
        """Charge lines adding up to XPO's total: linehaul per line before discount, deficit
        weight, discount, then XPO's accessorial lines (fuel surcharge included). The rating
        guide's sample: linehaul 1,840.30 - discount 1,423.66 + HMS 22.50 + FSC 101.87 = 541.01."""
        info = quote.get('shipmentInfo') or {}
        lines = []
        for commodity in info.get('commodity') or []:
            amount = self._xpo_amount((commodity.get('charge') or {}).get('chargeAmt'))
            if not amount:
                continue
            weight = (commodity.get('grossWeight') or {}).get('weight')
            lines.append({'code': 'LINEHAUL', 'amount': amount, 'name': _(
                'Linehaul before discount, class %(cls)s, %(weight)s lb',
                cls=self._xpo_class(commodity.get('nmfcClass')), weight='%g' % weight if weight else '-')})
        commodity_total = round(sum(line['amount'] for line in lines), 2)
        deficit = self._xpo_amount((quote.get('deficitRatingInfo') or {}).get('deficitAmt'))
        if deficit:
            lines.append({'code': 'DEFICIT', 'name': _('Deficit weight (rated at the next weight break)'),
                          'amount': deficit})
        gross = self._xpo_amount(info.get('totCommodityCharge') or quote.get('totCommodityCharge'))
        if gross and abs(gross - commodity_total) >= 0.01 and abs(gross - commodity_total - deficit) >= 0.01:
            lines.append({'code': 'MIN', 'name': _('Gross charge adjustment (minimum charge or weight break)'),
                          'amount': round(gross - commodity_total - deficit, 2)})
        discount = self._xpo_amount(quote.get('totDiscountAmt'))
        if discount:
            percent = quote.get('actlDiscountPct')
            name = _('Discount (%s%%)', '%g' % float(percent)) if isinstance(percent, (int, float)) and percent \
                else _('Discount')
            lines.append({'code': 'DISC', 'name': name, 'amount': -abs(discount)})
        for charge in info.get('accessorials') or []:
            amount = self._xpo_amount(charge.get('chargeAmt'))
            if not amount:
                continue
            code = (charge.get('accessorialCd') or '').strip().upper()
            title = ' '.join((charge.get('accessorialDesc') or '').split())
            if discount and 'discount' in title.lower():
                continue  # already in the discount line
            name = title.capitalize() if title.isupper() else title
            lines.append({'code': (code or 'ACC')[:20], 'name': name or code or _('Accessorial'), 'amount': amount})
        difference = round(total - sum(line['amount'] for line in lines), 2)
        if abs(difference) >= 0.01:
            lines.append({'code': 'OTHER', 'name': _('Other (difference to XPO total)'), 'amount': difference})
        return lines

    @api.model
    def _xpo_pro_key(self, number):
        return digits_only(number).lstrip('0')

    # ------------------------------------------------------------------ selamta_ltl hooks

    def xpo_ltl_rate(self, shipment):
        self.ensure_one()
        data = self._xpo_call('POST', 'rating/1.0/ratequotes', json=self._xpo_rate_request(shipment))
        rate = self._xpo_rate_from_answer(data)
        rates = [rate]
        if self.xpo_show_guaranteed and rate['xpo_guaranteed_available']:
            try:
                answer = self._xpo_call('POST', 'rating/1.0/ratequotes',
                                        json=self._xpo_rate_request(shipment, guaranteed=True))
                rates.append(self._xpo_rate_from_answer(answer, guaranteed=True))
            except UserError as error:
                _logger.info('XPO guaranteed quote failed: %s', error)
        return rates

    def xpo_raw_rate_answer(self, shipment_id=False):
        """Request and XPO's full answer for a shipment (or a sample from our dock), to check
        what XPO sends. Settings administrators only; books nothing."""
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only administrators can see raw XPO answers.'))
        shipment = self.env['selamta.ltl.shipment'].browse(shipment_id) if shipment_id \
            else self._xpo_sample_shipment()
        request = self._xpo_rate_request(shipment)
        return {'request': request, 'answer': self._xpo_call('POST', 'rating/1.0/ratequotes', json=request)}

    def xpo_ltl_book(self, shipment, rate):
        self.ensure_one()
        if not self.xpo_book_shipments:
            raise UserError(_('BOLs through the XPO API are off on %s; book on ltl.xpo.com and type the PRO.',
                              self.name))
        test_mode = self.xpo_environment == 'test'
        data = self._xpo_call('POST', 'billoflading/1.0/billsoflading', test_mode=test_mode,
                              json=self._xpo_bol_request(shipment, rate))
        info = (data.get('data') or {}).get('bolInfo') or data.get('data') or {}
        bol_id = str(info.get('bolInstId') or '').strip()
        if not bol_id:
            raise UserError(_('XPO did not confirm the BOL: %s', str(data)[:300]))
        shipment.write({'xpo_bol_inst_id': bol_id, 'xpo_test_booking': test_mode,
                        'xpo_terminal': info.get('pkupTrmnlSic') or rate.get('xpo_terminal') or False})
        notes = [_('XPO BOL created (XPO id %s).', bol_id)]
        pro = str(self._xpo_find(info, 'proNbr') or '').strip()
        if not pro:
            try:
                details = self._xpo_call('GET', 'billoflading/1.0/billsoflading/%s/requester' % bol_id,
                                         test_mode=test_mode)
                pro = str(self._xpo_find(details.get('data'), 'proNbr') or '').strip()
            except UserError as error:
                _logger.info('XPO BOL %s details not available: %s', bol_id, error)
        if pro:
            notes.append(_('XPO PRO %s.', pro))
        else:
            notes.append(_('XPO has not given the PRO yet: look it up on ltl.xpo.com and type it on the shipment.'))
        pickup = str(info.get('pkupInstId') or '').strip()
        if not pickup and info.get('pkupCallSeq'):
            call_date = self._xpo_date(info.get('pkupCallDate'))
            pickup = '%s-%s%s' % (info.get('pkupTrmnlSic') or 'XPO', info['pkupCallSeq'],
                                  call_date and ' (%s)' % call_date.strftime('%m/%d') or '')
        if pickup:
            notes.append(_('XPO pickup request %s.', pickup))
        elif self.xpo_schedule_pickup:
            notes.append(_('XPO did not confirm a pickup request: schedule the pickup on ltl.xpo.com.'))
        documents = []
        try:
            pdf = self._xpo_bol_pdf(bol_id, test_mode)
            if pdf:
                documents.append(('XPO BOL (carrier copy) %s.pdf' % (pro or bol_id), pdf))
        except UserError as error:
            notes.append(_('XPO BOL PDF not available yet: %s', error.args[0]))
        if test_mode:
            notes.append(_('Booked in XPO TEST MODE: nothing will be picked up.'))
        shipment.message_post(body=Markup('<br/>').join(notes))
        return {'pro_number': pro or False, 'pickup_number': pickup or False, 'documents': documents}

    def _xpo_bol_pdf(self, bol_id, test_mode):
        response = self._xpo_request('GET', 'billoflading/1.0/billsoflading/%s/pdf' % bol_id, test_mode=test_mode)
        if response.status_code >= 400:
            raise UserError('; '.join(self._xpo_errors(self._xpo_json(response))) or _('error %s', response.status_code))
        content = response.content or b''
        if content[:4] == b'%PDF':
            return content
        return self._xpo_pdf_in(self._xpo_json(response))

    @api.model
    def _xpo_pdf_in(self, data):
        """A base64 PDF anywhere in a JSON answer."""
        if isinstance(data, dict):
            values = data.values()
        elif isinstance(data, list):
            values = data
        elif isinstance(data, str) and len(data) > 100:
            try:
                content = base64.b64decode(data, validate=False)
            except (ValueError, TypeError):
                return None
            return content if content[:4] == b'%PDF' else None
        else:
            return None
        for value in values:
            found = self._xpo_pdf_in(value)
            if found:
                return found
        return None

    def xpo_ltl_cancel(self, shipment):
        self.ensure_one()
        if shipment.xpo_bol_inst_id:
            self._xpo_call('PUT', 'billoflading/1.0/billsoflading/%s/cancel' % shipment.xpo_bol_inst_id,
                           test_mode=shipment.xpo_test_booking, json={})
            return True
        number = (shipment.pickup_number or '').strip()
        if re.fullmatch(r'[A-Z0-9]{3}-\d+-\d+', number.upper()):
            self._xpo_call('PUT', 'pickuprequest/1.0/pickuprequests/%s/cancel' % number.upper(), test_mode=False,
                           json={'confirmationNbr': number.upper(),
                                 'cancelReason': 'Cancelled by shipper (%s)' % shipment.bol_reference})
            return True
        raise UserError(_('%s has no XPO BOL or pickup confirmation number; cancel it with XPO by phone.',
                          shipment.name))

    def xpo_ltl_track(self, shipments):
        self.ensure_one()
        searches = {}
        for shipment in shipments:
            key = self._xpo_pro_key(shipment.pro_number)
            if key:
                searches[key] = shipment
        results = {}
        keys = list(searches)
        for start in range(0, len(keys), TRACK_BATCH):
            batch = keys[start:start + TRACK_BATCH]
            try:
                data = self._xpo_call('GET', 'tracking/1.0/shipments/shipment-status-details',
                                      params=[('referenceNumbers', key) for key in batch])
            except UserError as error:
                _logger.warning('XPO tracking failed for %s: %s', ', '.join(batch), error)
                continue
            for details in (data.get('data') or {}).get('shipmentStatusDtls') or []:
                shipment = searches.get(self._xpo_pro_key(details.get('proNbr')))
                if shipment:
                    results[shipment.id] = self._xpo_tracking_info(details)
        return results

    def _xpo_tracking_info(self, details):
        info = {}
        status = details.get('shipmentStatus') or {}
        code = str(status.get('statusCd') or '').strip()
        text = ' '.join(str(status.get('description') or status.get('reason') or '').split())
        delivered = self._xpo_date(details.get('finalDlvrDate'))
        if code in DELIVERED_CODES or (delivered and code not in CANCELLED_CODES):
            info['state'] = 'delivered'
            if delivered:
                info['delivered_date'] = fields.Date.to_string(delivered)
            signed = ' '.join(str(details.get('dlvrSigNameTxt') or '').split())
            if signed:
                text = _('%(status)s, signed by %(name)s', status=text or _('Delivered'), name=signed)
        elif code not in CANCELLED_CODES and (self._xpo_date(details.get('pkupDate'))
                                               or (code and code not in NOT_PICKED_UP_CODES)):
            info['state'] = 'in_transit'
        estimated = self._xpo_date(details.get('estdDlvrDate'))
        if estimated and info.get('state') != 'delivered':
            date_text = estimated.strftime('%m/%d/%Y')
            text = _('%(status)s, estimated delivery %(date)s', status=text, date=date_text) if text \
                else _('Estimated delivery %s', date_text)
        if text:
            info['status'] = text
        return info

    def xpo_ltl_documents(self, shipment):
        self.ensure_one()
        pro = digits_only(shipment.pro_number)
        if not pro:
            raise UserError(_('%s has no PRO yet.', shipment.name))
        existing = set(self.env['ir.attachment'].search([
            ('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name'))
        documents = []
        for doc_type, label in DOCUMENT_TYPES:
            name = '%s %s.pdf' % (label, pro)
            if name in existing:
                continue
            try:
                data = self._xpo_call('GET', 'imaging/1.0/shipments/%s/imaged-docs' % pro, params={
                    'imageType': doc_type, 'imageFormat': 'PDF', 'multiPartResp': 'false'})
            except UserError as error:
                _logger.info('XPO %s for %s not available: %s', doc_type, pro, error)
                continue
            pages = []
            for document in (data.get('data') or {}).get('imagedDocument') or []:
                for image in document.get('imageFiles') or []:
                    if image.get('base64Data'):
                        pages.append(base64.b64decode(image['base64Data']))
            if not pages:
                continue
            content = pages[0]
            if len(pages) > 1:
                try:
                    content = merge_pdf(pages)
                except Exception as error:  # keep the first page rather than nothing
                    _logger.info('Could not merge the XPO %s pages for %s: %s', doc_type, pro, error)
            documents.append((name, content))
        return documents

    # ------------------------------------------------------------------ Odoo delivery hooks

    def xpo_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('XPO rates come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def xpo_send_shipping(self, pickings):
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def xpo_get_tracking_link(self, picking):
        return PUBLIC_TRACKING_URL if picking.carrier_tracking_ref else False

    def xpo_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the LTL shipment in Odoo; it cancels the XPO BOL and pickup.'))

    def _xpo_sample_shipment(self):
        shipper = self.env.company.partner_id
        return self.env['selamta.ltl.shipment'].new({
            'shipper_id': shipper.id, 'partner_id': shipper.id, 'carrier_id': self.id,
            'ship_date': fields.Date.context_today(self),
            'unit_ids': [(0, 0, {'unit_type': 'pallet', 'quantity': 1, 'length': 48, 'width': 40,
                                 'height': 48, 'weight': 500, 'class_override': '70'})],
        })

    def action_xpo_test_connection(self):
        """Log in to XPO and ask for a sample quote from our dock to itself (500 lb, class 70).
        Books nothing."""
        self.ensure_one()
        data = self._xpo_call('POST', 'rating/1.0/ratequotes',
                              json=self._xpo_rate_request(self._xpo_sample_shipment()))
        rate = self._xpo_rate_from_answer(data)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _(
                'XPO login works. Sample quote %(quote)s: %(total).2f, %(days)s days.',
                quote=rate['quote_number'] or '-', total=rate['total'], days=rate['transit_days'])},
        }
