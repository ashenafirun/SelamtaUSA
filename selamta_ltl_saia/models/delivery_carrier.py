# -*- coding: utf-8 -*-
"""Saia LTL Freight REST APIs (developer portal saiaprodapi.developer.azure-api.net; rate quote
OpenAPI at api.saia.com/rate-quote/public/api-docs/index, read 30 Oct 2026).

Every product has its own subscription key from the developer portal; the Saia Secure (saia.com)
user ID and password give our pricing and our documents.

* Rate quote: POST https://api.saia.com/rate-quote/webservice/ratequote/customer-api, header
  RQ-Key, body {userID, password, payer: Shipper, origin {accountCode, city, state, zipcode},
  destination {city, state, zipcode}, weightUnits LBS, measurementUnit IN, details [{weight
  (total for the line), class (number), length, width, height, units}], accessorials {code:
  [...]}}. Without accountCode Saia picks our account from the login and the address.
  Answer: status, quoteNumber, expirationDate, estimatedDeliveryDate, standardServiceDays,
  discount {discountPercent, discountAmount}, surcharge {fuelSurchargePercent,
  fuelSurchargeAmount, fuelSurchargeAmountWithGss5/10/12}, rateDetails {totalInvoice,
  isGssCompliant, totalInvoiceWithGss5/10/12, gss5/10/12AccessorialCharge}, deficitDetails
  {deficitAmount}, rateDetailItems [{class, weight, rate, amount}], rateAccessorials {accessorials: [{code,
  description, amount}], terminals.originTerminal {name, cityDispatchPhone}. Errors: {status:
  FAIL, fault, errors: [{<field>: {message}}]}; gateway errors {statusCode, message}.
* Tracking: GET https://api.saia.com/customer-api/webservice/track/pro-numbers/{pro}, headers
  Ocp-Apim-Subscription-Key (tracking key) and Api-Version V1, Basic auth with the Saia Secure
  login. Saia does not publish the answer's fields, so they are read loosely.
* Documents: GET https://api.saia.com/imaging/api/v1/getImages?pro=&formatType=pdf
  &documentFilter=DR,WC,IV, header CA-Key, Basic auth -> imageInfo [{status, pageNumber,
  docType, base64}]. PROs are 11 digits.
"""
import base64
import json as json_lib
import logging
import re
from datetime import datetime

import requests
from lxml import etree
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.pdf import merge_pdf

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

HOST = 'https://api.saia.com'
TIMEOUT = 45
TRACK_URL = 'https://www.saia.com/track/details;pro=%s'
# Our accessorial codes -> Saia rate quote accessorial codes (from the rate quote API's list).
ACCESSORIALS = {
    'LIFTGATE_DEL': 'LiftgateService',
    'RESIDENTIAL_DEL': 'ResidentialDelivery',
    'LIMITED_ACCESS_DEL': 'LimitedAccessLocation',
    'INSIDE_DEL': 'InsideDelivery',
    'APPOINTMENT_DEL': 'ArrivalNotice/Appointment',
    'NOTIFY_DEL': 'ArrivalNotice/Appointment',
    'LIFTGATE_PU': 'LiftgateServicePU',
}
# Saia guaranteed services in the rate answer.
GUARANTEED = [
    ('Gss12', 'Saia Guaranteed by noon'),
    ('Gss10', 'Saia Guaranteed by 10 AM'),
    ('Gss5', 'Saia Guaranteed by 5 PM'),
]
DOCUMENT_TYPES = [
    ('DR', 'Delivery receipt'),
    ('WC', 'Weight certificate'),
    ('IV', 'Saia invoice'),
]
VALID_CLASSES = {50, 55, 60, 65, 70, 77.5, 85, 92.5, 100, 110, 125, 150, 175, 200, 250, 300, 400, 500}

# Booking: Saia's SOAP web services on saiasecure.com (help pages soap.asmx?op=Create, read
# 2 Nov 2026). Login is the Saia Secure user ID and password in the request; no portal key.
# * Pickup Create: request {Details {DetailItem {DestinationZipcode, DestinationCountry, Pieces,
#   Package, Weight, Freezable, SaiaGuaranteed}}, UserID, Password, TestMode, AccountNumber,
#   CompanyName, Street, Box, City, State, Zipcode, ContactName, ContactPhone, PickupDate
#   (YYYY-MM-DD), ReadyTime, CloseTime (HH:MM:SS, ready at least 90 minutes before close),
#   SpecialInstructions} -> CreateResult {PickupTerminal {...}, Code, Element, Fault, Message,
#   TestMode, PickupNumber, TotalPieces, TotalWeight, NextBusinessDate (with code S04)}.
# * Bill of Lading Create: request {Shipper, Consignee (AccountNumber, ContactName, Address1,
#   Address2, City, State, Zipcode, Zipcode4), COD, Details {DetailItem {PONumber, Class,
#   Package, Pieces, Weight, FoodItem, Hazardous, UNHazmatID, UNPackageGroup, UNBulk,
#   Description, NmfcCode, SubClass}}, Accessorials {AccessorialItem {Code}}, ..., UserID,
#   Password, TestMode, ShipmentDate, BillingTerms, BLNumber, ..., QuoteNumber, ...} ->
#   CreateResult {Code, Element, Fault, Message, TestMode, ProNumber, CheckDigit, PDF, HTML,
#   Barcode}. A non-empty Code means the call failed; Fault C = our request, S = Saia's side.
# Elements are sent in the order of Saia's schema; number elements (decimal) are always sent.
SOAP_URL = 'https://www.saiasecure.com/webservice/%s/soap.asmx'
SOAP_ENV = 'http://schemas.xmlsoap.org/soap/envelope/'
BOL_NS = 'http://www.SaiaSecure.com/WebService/BOL'
PICKUP_NS = 'http://www.SaiaSecure.com/WebService/Pickup'
PACKAGES = {'pallet': 'SK', 'box': 'BX'}
BILLING_TERMS = {'prepaid': 'Prepaid', 'collect': 'Collect'}


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('saia', 'Saia')],
        ondelete={'saia': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    saia_username = fields.Char(
        'Saia user ID', groups='base.group_system', copy=False,
        help='The saia.com (Saia Secure) user ID. It gives our pricing on quotes and our documents.')
    saia_password = fields.Char('Saia password', groups='base.group_system', copy=False)
    saia_account_code = fields.Char(
        'Saia account number',
        help='Optional. Leave empty to let Saia pick our account from the login and the dock\'s '
             'address. If filled in, it must be the account registered at the dock\'s ZIP code.')
    saia_rq_key = fields.Char(
        'Rate Quote key', groups='base.group_system', copy=False,
        help='Subscription key of the "REST Rate Quote Customer API" product on '
             'saiaprodapi.developer.azure-api.net.')
    saia_tracking_key = fields.Char(
        'Tracking key', groups='base.group_system', copy=False,
        help='Subscription key of the "Tracking REST Customer API" product.')
    saia_imaging_key = fields.Char(
        'Imaging key', groups='base.group_system', copy=False,
        help='Subscription key of the "Customer Imaging API" product (delivery receipts, weight '
             'certificates, invoices). Optional.')
    saia_show_guaranteed = fields.Boolean(
        'Show guaranteed quotes',
        help='Also list Saia\'s guaranteed services (by noon, 10 AM, 5 PM) when Saia offers them.')
    saia_book_shipments = fields.Boolean(
        'Book through the API',
        help='With this on, choosing Saia in the rate shop requests a real pickup and creates the '
             'BOL with Saia (PRO number and Saia\'s BOL). With it off, the quote is saved and the '
             'load is booked on saia.com.')
    saia_test_mode = fields.Boolean(
        'Test mode',
        help='Send bookings with Saia\'s TestMode: Saia checks them and answers, but nothing is '
             'filed and nothing is picked up.')
    saia_contact_name = fields.Char('Saia pickup contact')
    saia_contact_phone = fields.Char('Saia pickup contact phone')
    saia_contact_email = fields.Char('Saia pickup contact email')

    # ------------------------------------------------------------------ connection

    def ltl_can(self, operation):
        self.ensure_one()
        if self.delivery_type == 'saia' and operation == 'book' and not self.saia_book_shipments:
            return False
        return super().ltl_can(operation)

    def _saia_secret(self, field, label):
        value = (self.sudo()[field] or '').strip()
        if not value:
            raise UserError(_('Enter the %(label)s on the %(name)s shipping method (Saia tab) first.',
                              label=label, name=self.name))
        return value

    def _saia_login(self):
        self.ensure_one()
        return (self._saia_secret('saia_username', _('Saia user ID')),
                self._saia_secret('saia_password', _('Saia password')))

    def _saia_mask(self, text):
        """Never show a key or the password in a message."""
        text = str(text or '')
        carrier = self.sudo()
        for field in ('saia_password', 'saia_rq_key', 'saia_tracking_key', 'saia_imaging_key'):
            value = (carrier[field] or '').strip()
            if value and len(value) > 3:
                text = text.replace(value, '***')
        return text

    def _saia_request(self, method, path, key_header, key, auth=False, **kwargs):
        self.ensure_one()
        url = '%s/%s' % (HOST, path)
        headers = {key_header: key, 'Accept': 'application/json'}
        headers.update(kwargs.pop('headers', {}))
        if 'json' in kwargs:
            headers['Content-Type'] = 'application/json'
        if auth:
            kwargs['auth'] = self._saia_login()
        _logger.info('Saia %s %s', method, url)
        try:
            return requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as error:
            raise UserError(_('Could not reach Saia: %s', self._saia_mask(error))) from error

    @api.model
    def _saia_json(self, response):
        try:
            data = response.json()
        except ValueError:
            return {}
        return data if isinstance(data, (dict, list)) else {}

    def _saia_errors(self, data, response=None):
        messages = []
        if isinstance(data, dict):
            for entry in data.get('errors') or []:
                if isinstance(entry, dict):
                    for prop, detail in entry.items():
                        if isinstance(detail, dict) and detail.get('message'):
                            messages.append('%s (%s)' % (detail['message'], prop))
                        elif isinstance(detail, str):
                            messages.append(detail)
            errors = data.get('errors')
            if isinstance(errors, dict):  # field validation: {"pro": {"msg": "..."}}
                for prop, detail in errors.items():
                    if isinstance(detail, dict) and (detail.get('msg') or detail.get('message')):
                        messages.append('%s (%s)' % (detail.get('msg') or detail.get('message'), prop))
            for key in ('error', 'message', 'Message'):
                if not messages and isinstance(data.get(key), str) and data[key]:
                    messages.append(data[key])
        if not messages and response is not None:
            messages.append((response.text or '').strip()[:300] or _('error %s', response.status_code))
        return self._saia_mask('; '.join(messages))

    def _saia_check(self, response, data):
        failed = isinstance(data, dict) and str(data.get('status') or '').upper() == 'FAIL'
        try:
            gateway = int((data.get('statusCode') if isinstance(data, dict) else None) or 200)
        except (TypeError, ValueError):
            gateway = 200
        if response.status_code >= 400 or failed or gateway >= 400:
            message = self._saia_errors(data, response)
            if response.status_code == 401 or 'subscription key' in message.lower():
                raise UserError(_('Saia refused the key or login (%(text)s). Check the Saia tab of the %(name)s '
                                  'shipping method.', text=message, name=self.name))
            raise UserError(_('Saia: %s', message))
        return data

    # ------------------------------------------------------------------ request parts

    @api.model
    def _saia_zip(self, partner):
        if partner.country_id.code == 'CA':
            return ''.join(ch for ch in (partner.zip or '') if ch.isalnum()).upper()[:6]
        if (partner.country_id.code or 'US') != 'US':
            raise UserError(_('Saia quotes here are for US and Canadian addresses (%s).', partner.display_name))
        postal = digits_only(partner.zip)[:5]
        if len(postal) != 5:
            raise UserError(_('%s needs a 5-digit ZIP code for Saia.', partner.display_name))
        return postal

    @api.model
    def _saia_point(self, partner):
        return {
            'city': ' '.join((partner.city or '').split()).upper(),
            'state': partner.state_id.code or '',
            'zipcode': self._saia_zip(partner),
        }

    @api.model
    def _saia_class(self, freight_class):
        try:
            value = float(freight_class)
        except (TypeError, ValueError):
            raise UserError(_('Freight class %s is not a number.', freight_class))
        if value not in VALID_CLASSES:
            raise UserError(_('Saia does not rate class %s.', freight_class))
        return int(value) if value == int(value) else value

    @api.model
    def _saia_units(self, shipment):
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the pallets or boxes to %s first.', shipment.name))
        for unit in units:
            if not unit.freight_class or not unit.weight:
                raise UserError(_('Measure and weigh every pallet or box on %s first.', shipment.name))
        return units

    def _saia_accessorial_codes(self, shipment):
        codes = []
        for service in shipment.accessorial_ids:
            code = ACCESSORIALS.get(service.code)
            if code and code not in codes:
                codes.append(code)
        return codes

    def _saia_rate_request(self, shipment):
        user, password = self._saia_login()
        details = []
        for unit in self._saia_units(shipment):
            line = {
                'weight': max(int(round(unit.weight)), 1),
                'class': self._saia_class(unit.freight_class),
                'units': max(int(unit.quantity or 1), 1),
            }
            if unit.length and unit.width and unit.height:
                line.update({'length': int(round(unit.length)), 'width': int(round(unit.width)),
                             'height': int(round(unit.height))})
            details.append(line)
        origin = self._saia_point(shipment.shipper_id)
        if (self.saia_account_code or '').strip():
            origin['accountCode'] = self.saia_account_code.strip()
        return {
            'userID': user,
            'password': password,
            'payer': 'Shipper',
            'origin': origin,
            'destination': self._saia_point(shipment.partner_id),
            'weightUnits': 'LBS',
            'measurementUnit': 'IN',
            'details': details,
            'accessorials': {'code': self._saia_accessorial_codes(shipment)},
        }

    # ------------------------------------------------------------------ answers

    @api.model
    def _saia_number(self, value):
        if isinstance(value, str):
            value = re.sub(r'[^0-9.\-]', '', value)
        try:
            return round(float(value or 0.0), 2)
        except (TypeError, ValueError):
            return 0.0

    @api.model
    def _saia_list(self, value):
        if not value:
            return []
        return value if isinstance(value, list) else [value]

    @api.model
    def _saia_date(self, value):
        text = str(value or '').strip()
        for fmt, size in (('%Y-%m-%d', 10), ('%m/%d/%Y', 10)):
            try:
                parsed = datetime.strptime(text[:size], fmt).date()
            except ValueError:
                continue
            return parsed if parsed.year > 1900 else False
        return False

    def _saia_base_lines(self, data):
        lines = []
        for item in self._saia_list(data.get('rateDetailItems')):
            amount = self._saia_number(item.get('amount'))
            if amount:
                lines.append({'code': 'LINEHAUL', 'amount': amount, 'name': _(
                    'Linehaul before discount, class %(cls)s, %(weight)s lb',
                    cls=item.get('class') or '-', weight=item.get('weight') or '-')})
        deficit = self._saia_number((data.get('deficitDetails') or {}).get('deficitAmount'))
        if deficit:
            lines.append({'code': 'DEFICIT', 'name': _('Deficit weight (rated at the next weight break)'),
                          'amount': deficit})
        discount = data.get('discount') or {}
        amount = self._saia_number(discount.get('discountAmount'))
        if amount:
            percent = self._saia_number(discount.get('discountPercent'))
            lines.append({'code': 'DISC', 'amount': -abs(amount),
                          'name': _('Discount (%s%%)', '%g' % percent) if percent else _('Discount')})
        accessorials = data.get('rateAccessorials')
        if isinstance(accessorials, dict):  # real answer: {"accessorials": [...]}
            accessorials = accessorials.get('accessorials') or accessorials.get('accessorial') or []
        for charge in self._saia_list(accessorials):
            amount = self._saia_number(charge.get('amount'))
            if not amount:
                continue
            title = ' '.join(str(charge.get('description') or charge.get('code') or '').split())
            title = re.sub(r'\s+\d+(\.\d+)?$', '', title)  # "EXCESSIVE LENGTH    6" -> "EXCESSIVE LENGTH"
            lines.append({'code': (charge.get('internalCode') or charge.get('code') or 'ACC')[:20],
                          'name': title.capitalize() if title.isupper() else (title or _('Accessorial')),
                          'amount': amount})
        return lines

    def _saia_finish(self, lines, total):
        difference = round(total - sum(line['amount'] for line in lines), 2)
        if abs(difference) >= 0.01:
            lines.append({'code': 'OTHER', 'name': _('Other (difference to Saia total)'), 'amount': difference})
        return lines

    def _saia_rates_from_answer(self, data):
        details = data.get('rateDetails') or {}
        total = self._saia_number(details.get('totalInvoice'))
        if total <= 0:
            raise UserError(_('Saia returned no rate: %s', self._saia_errors(data) or _('no details')))
        surcharge = data.get('surcharge') or {}
        fuel = self._saia_number(surcharge.get('fuelSurchargeAmount'))
        base = self._saia_base_lines(data)
        terminal = (data.get('terminals') or {}).get('originTerminal') or {}
        terminal_text = ' '.join(filter(None, [
            terminal.get('name'), terminal.get('cityDispatchPhone') and '(%s)' % terminal['cityDispatchPhone']])) \
            or False
        common = {
            'quote_number': str(data.get('quoteNumber') or '') or False,
            'expires': fields.Date.to_string(self._saia_date(data.get('expirationDate')))
            if self._saia_date(data.get('expirationDate')) else False,
            'transit_days': int(data.get('standardServiceDays') or 0),
            'saia_terminal': terminal_text,
        }
        standard_lines = [dict(line) for line in base]
        if fuel:
            percent = self._saia_number(surcharge.get('fuelSurchargePercent'))
            standard_lines.append({'code': 'FUEL', 'amount': fuel, 'name': _('Fuel surcharge (%s%%)', '%g' % percent)
                                   if percent else _('Fuel surcharge')})
        rates = [dict(common, service=_('Saia Standard'), total=total, saia_service='STD',
                      charges=self._saia_finish(standard_lines, total))]
        if self.saia_show_guaranteed and details.get('isGssCompliant') not in (False, 'N', 'false'):
            for key, label in GUARANTEED:
                gss_total = self._saia_number(details.get('totalInvoiceWith' + key))
                if gss_total <= total:
                    continue
                lines = [dict(line) for line in base]
                gss_fuel = self._saia_number(surcharge.get('fuelSurchargeAmountWith' + key)) or fuel
                if gss_fuel:
                    lines.append({'code': 'FUEL', 'name': _('Fuel surcharge'), 'amount': gss_fuel})
                charge = self._saia_number(details.get(key.lower() + 'AccessorialCharge'))
                if charge:
                    lines.append({'code': key.upper(), 'name': _('Guaranteed service'), 'amount': charge})
                rates.append(dict(common, service=label, total=gss_total, saia_service=key.upper(),
                                  charges=self._saia_finish(lines, gss_total)))
        return rates

    @api.model
    def _saia_pro(self, number):
        pro = digits_only(number)
        return pro.zfill(11) if pro and len(pro) < 11 else pro

    # ------------------------------------------------------------------ selamta_ltl hooks

    def saia_ltl_rate(self, shipment):
        self.ensure_one()
        key = self._saia_secret('saia_rq_key', _('Saia Rate Quote key'))
        response = self._saia_request('POST', 'rate-quote/webservice/ratequote/customer-api', 'RQ-Key', key,
                                      json=self._saia_rate_request(shipment))
        data = self._saia_check(response, self._saia_json(response))
        return self._saia_rates_from_answer(data)

    # ------------------------------------------------------------------ booking (SOAP)

    @api.model
    def _saia_add(self, parent, ns, name, value=None):
        element = etree.SubElement(parent, '{%s}%s' % (ns, name))
        if value is not None:
            element.text = str(value)
        return element

    def _saia_soap(self, service, ns, request):
        """Send Create(request) to a saiasecure.com SOAP service; return CreateResult."""
        self.ensure_one()
        envelope = etree.Element('{%s}Envelope' % SOAP_ENV, nsmap={'soap': SOAP_ENV})
        body = etree.SubElement(envelope, '{%s}Body' % SOAP_ENV)
        create = etree.SubElement(body, '{%s}Create' % ns, nsmap={None: ns})
        create.append(request)
        payload = etree.tostring(envelope, xml_declaration=True, encoding='utf-8')
        url = SOAP_URL % service
        _logger.info('Saia POST %s', url)
        try:
            response = requests.request('POST', url, data=payload, timeout=TIMEOUT, headers={
                'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': '"%s/Create"' % ns})
        except requests.RequestException as error:
            raise UserError(_('Could not reach Saia: %s', self._saia_mask(error))) from error
        try:
            root = etree.fromstring(response.content or b'')
        except (etree.XMLSyntaxError, ValueError):
            raise UserError(_('Saia answered %(status)s: %(text)s', status=response.status_code,
                              text=self._saia_mask((response.text or '').strip()[:300]) or _('no details')))
        fault = root.find('.//{%s}Fault' % SOAP_ENV)
        if fault is not None:
            raise UserError(_('Saia: %s', self._saia_mask(' '.join(
                (fault.findtext('faultstring') or fault.findtext('.//faultstring') or '').split()) or _('error'))))
        result = root.find('.//{%s}CreateResult' % ns)
        if result is None:
            raise UserError(_('Saia answered %(status)s without a result.', status=response.status_code))
        return result

    @api.model
    def _saia_result(self, result, ns, name):
        return ' '.join((result.findtext('{%s}%s' % (ns, name)) or '').split())

    def _saia_result_error(self, result, ns):
        code = self._saia_result(result, ns, 'Code')
        if not code:
            return False
        message = self._saia_result(result, ns, 'Message') or _('no details')
        element = self._saia_result(result, ns, 'Element')
        return '%s%s (%s)' % (message, ' [%s]' % element if element else '', code)

    @api.model
    def _saia_phone(self, value, label):
        phone = digits_only(value)
        if len(phone) == 11 and phone.startswith('1'):
            phone = phone[1:]
        if len(phone) != 10:
            raise UserError(_('Saia needs a 10-digit phone number for the %s.', label))
        return phone

    @api.model
    def _saia_clock(self, hours):
        """10.5 -> '10:30:00'."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        return '%02d:%02d:00' % (min(hour, 23), minute)

    def _saia_contact(self, shipment):
        shipper, company = shipment.shipper_id, shipment.company_id
        return {
            'name': (self.saia_contact_name or self.env.user.name or company.name or '')[:30],
            'phone': self._saia_phone(self.saia_contact_phone or shipper.phone or shipper.mobile or company.phone,
                                      _('pickup contact (Saia tab or the shipper)')),
            'email': self.saia_contact_email or shipper.email or company.email or '',
        }

    @api.model
    def _saia_check_address(self, partner, label):
        if not partner.street or not partner.city or not partner.state_id:
            raise UserError(_('%(name)s needs a street, city and state for a Saia booking (%(label)s).',
                              name=partner.display_name, label=label))

    def _saia_test_flag(self):
        return 'Y' if self.saia_test_mode else 'N'

    def _saia_pickup_request(self, shipment, rate):
        ns = PICKUP_NS
        shipper, consignee = shipment.shipper_id, shipment.partner_id
        self._saia_check_address(shipper, _('shipper'))
        account = (self.saia_account_code or '').strip()
        if not account:
            raise UserError(_('Enter the Saia account number on the %s shipping method (Saia tab) first: Saia '
                              'pickups need it.', self.name))
        if shipment.pickup_close_time - shipment.pickup_ready_time < 1.5:
            raise UserError(_('Saia needs the freight ready at least 90 minutes before the dock closes; change '
                              'the pickup window on %s.', shipment.name))
        user, password = self._saia_login()
        units = self._saia_units(shipment)
        contact = self._saia_contact(shipment)
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        guaranteed = 'Y' if (rate.get('saia_service') or 'STD') != 'STD' else 'N'
        request = etree.Element('{%s}request' % ns)
        add = lambda name, value=None, parent=request: self._saia_add(parent, ns, name, value)  # noqa: E731
        item = add('DetailItem', parent=add('Details'))
        add('DestinationZipcode', self._saia_zip(consignee), item)
        add('DestinationCountry', consignee.country_id.code or 'US', item)
        add('Pieces', sum(max(int(u.quantity or 1), 1) for u in units), item)
        add('Package', 'SK' if 'pallet' in units.mapped('unit_type') else 'BX', item)
        add('Weight', int(round(sum(units.mapped('weight')))), item)
        add('Freezable', 'N', item)
        add('SaiaGuaranteed', guaranteed, item)
        add('UserID', user)
        add('Password', password)
        add('TestMode', self._saia_test_flag())
        add('AccountNumber', account)
        add('CompanyName', (shipper.commercial_partner_id.name or shipper.name or '')[:40])
        add('Street', shipper.street[:40])
        add('Box', '')
        add('City', shipper.city[:30])
        add('State', shipper.state_id.code)
        add('Zipcode', self._saia_zip(shipper))
        add('ContactName', contact['name'])
        add('ContactPhone', contact['phone'])
        add('PickupDate', ship_date.strftime('%Y-%m-%d'))
        add('ReadyTime', self._saia_clock(shipment.pickup_ready_time))
        add('CloseTime', self._saia_clock(shipment.pickup_close_time))
        notes = ['BOL %s' % shipment.bol_reference]
        if shipment.pickup_instructions:
            notes.append(' '.join(shipment.pickup_instructions.split()))
        add('SpecialInstructions', '. '.join(notes)[:200])
        return request

    def _saia_bol_request(self, shipment, rate):
        ns = BOL_NS
        shipper, consignee = shipment.shipper_id, shipment.partner_id
        self._saia_check_address(consignee, _('consignee'))
        terms = BILLING_TERMS.get(shipment.freight_terms)
        if not terms:
            raise UserError(_('Saia bookings here are prepaid or collect; %s is billed to a third party. Book it '
                              'on saia.com.', shipment.name))
        user, password = self._saia_login()
        contact = self._saia_contact(shipment)
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        request = etree.Element('{%s}request' % ns)
        add = lambda name, value=None, parent=request: self._saia_add(parent, ns, name, value)  # noqa: E731

        def party(name, partner, account, contact_name):
            block = add(name)
            add('AccountNumber', account, block)
            add('ContactName', contact_name[:30], block)
            add('Address1', (partner.street or '')[:30], block)
            add('Address2', (partner.street2 or '')[:30], block)
            add('City', (partner.city or '')[:30], block)
            add('State', partner.state_id.code or '', block)
            add('Zipcode', self._saia_zip(partner), block)
            add('Zipcode4', '', block)

        party('Shipper', shipper, (self.saia_account_code or '').strip(), contact['name'])
        party('Consignee', consignee, '',
              consignee.commercial_partner_id.name if consignee.parent_id else consignee.name or '')
        cod = add('COD')
        add('CompanyCheck', '', cod)
        add('BillingTerms', '', cod)
        add('Amount', 0, cod)
        details = add('Details')
        for unit in self._saia_units(shipment):
            item = add('DetailItem', parent=details)
            add('PONumber', '', item)
            add('Class', '%g' % self._saia_class(unit.freight_class), item)
            add('Package', PACKAGES.get(unit.unit_type, 'SK'), item)
            add('Pieces', max(int(unit.quantity or 1), 1), item)
            add('Weight', max(int(round(unit.weight)), 1), item)
            add('FoodItem', 'Y', item)
            add('Hazardous', 'N', item)
            add('UNHazmatID', '', item)
            add('UNPackageGroup', '', item)
            add('UNBulk', '', item)
            add('Description', (unit.description or _('Freight'))[:50], item)
            add('NmfcCode', unit.nmfc_item or '', item)
            add('SubClass', unit.nmfc_sub or '', item)
        accessorials = add('Accessorials')
        for code in self._saia_accessorial_codes(shipment):
            add('Code', code, add('AccessorialItem', parent=accessorials))
        add('ExcessiveLengthTotalInches', '')
        add('FullValueCoverage', 0)
        add('UserID', user)
        add('Password', password)
        add('TestMode', self._saia_test_flag())
        add('ShipmentDate', ship_date.strftime('%Y-%m-%d'))
        add('BillingTerms', terms)
        add('BLNumber', (shipment.bol_reference or '')[:20])
        add('ShipperNumber', '')
        add('StoreNumber', '')
        add('TrailerNumber', '')
        add('PONumber', (shipment.order_refs or '')[:20])
        add('DepartmentNumber', '')
        add('QuoteNumber', str(rate.get('quote_number') or shipment.quote_number or '')[:20])
        add('Email', contact['email'][:50])
        add('PrintRates', 'N')
        add('Customs', 'N')
        add('GuaranteedDelivery', 'Y' if (rate.get('saia_service') or 'STD') != 'STD' else '')
        add('EmergencyPhone', 0)
        add('SpecialInstructions', '. '.join(shipment._bol_delivery_lines())[:250])
        add('VICS', 'N')
        add('WeightUnits', 'LBS')
        add('TotalCube', 0)
        add('TotalCubeUnits', '')
        add('DeclaredValue', 0)
        add('BorderLocation', '')
        return request

    @api.model
    def _saia_bol_pro(self, result):
        pro = digits_only(self._saia_result(result, BOL_NS, 'ProNumber').split('.')[0])
        check = digits_only(self._saia_result(result, BOL_NS, 'CheckDigit').split('.')[0])
        if pro and check and len(pro) == 10:
            pro += check[-1]
        return self._saia_pro(pro) if pro and int(pro) else False

    def saia_ltl_book(self, shipment, rate):
        """Request the pickup (the truck), then file the BOL with Saia for the PRO and Saia's
        BOL. When the pickup is booked but the BOL is not, the booking stands: the driver
        takes our BOL and the PRO is typed in from it."""
        self.ensure_one()
        if not self.saia_book_shipments:
            raise UserError(_('Booking through the Saia API is off on %s; book on saia.com and type the PRO.',
                              self.name))
        pickup = self._saia_soap('pickup', PICKUP_NS, self._saia_pickup_request(shipment, rate))
        error = self._saia_result_error(pickup, PICKUP_NS)
        if error:
            next_day = self._saia_result(pickup, PICKUP_NS, 'NextBusinessDate')
            if next_day:
                raise UserError(_('Saia cannot pick up on that date (%(error)s). Its next business day is '
                                  '%(day)s: change the pickup date and choose the rate again.',
                                  error=error, day=next_day))
            raise UserError(_('Saia did not take the pickup request: %s', error))
        pickup_number = digits_only(self._saia_result(pickup, PICKUP_NS, 'PickupNumber').split('.')[0]).lstrip('0')
        notes = [_('Saia pickup %s requested.', pickup_number or '-')]
        terminal = ' '.join(filter(None, [
            pickup.findtext('{%s}PickupTerminal/{%s}Name' % (PICKUP_NS, PICKUP_NS)),
            pickup.findtext('{%s}PickupTerminal/{%s}CityDispatchPhone' % (PICKUP_NS, PICKUP_NS))]))
        if terminal.strip():
            notes.append(_('Pickup terminal: %s', ' '.join(terminal.split())))
        result = {'pickup_number': pickup_number or False, 'documents': []}
        try:
            bol = self._saia_soap('BOL', BOL_NS, self._saia_bol_request(shipment, rate))
            error = self._saia_result_error(bol, BOL_NS)
            if error:
                raise UserError(error)
        except UserError as error:
            notes.append(_('Saia did not file the BOL (%s). The pickup is booked: print the Odoo BOL for the '
                           'driver and type the PRO from it.', error.args[0] if error.args else error))
            bol = None
        if bol is not None:
            pro = self._saia_bol_pro(bol)
            result['pro_number'] = pro
            notes.append(_('Saia BOL filed, PRO %s.', pro or '-'))
            pdf_text = self._saia_result(bol, BOL_NS, 'PDF').replace(' ', '')
            if pdf_text:
                try:
                    pdf = base64.b64decode(pdf_text)
                except (ValueError, TypeError):
                    pdf = b''
                if pdf[:4] == b'%PDF':
                    result['documents'].append(('Saia BOL (carrier copy) %s.pdf' % (pro or shipment.name), pdf))
        if self.saia_test_mode:
            notes.append(_('Sent in Saia TEST mode: nothing is filed and nothing will be picked up.'))
        shipment.message_post(body=Markup('<br/>').join(notes))
        return result

    def saia_raw_answer(self, kind='rate', shipment_id=False):
        """Saia's full answer (password and keys hidden) for a rate quote, a tracking or a
        document lookup, as text, to check what Saia sends. Administrators only; books nothing."""
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only administrators can see raw Saia answers.'))
        shipment = self.env['selamta.ltl.shipment'].browse(shipment_id) if shipment_id else self._saia_sample_shipment()
        if kind == 'track':
            response = self._saia_track_request(self._saia_pro(shipment.pro_number))
            request = {'pro': self._saia_pro(shipment.pro_number)}
        else:
            request = self._saia_rate_request(shipment)
            response = self._saia_request('POST', 'rate-quote/webservice/ratequote/customer-api', 'RQ-Key',
                                          self._saia_secret('saia_rq_key', _('Saia Rate Quote key')), json=request)
            request = dict(request, password='***')
        return self._saia_mask(json_lib.dumps({'request': request, 'status': response.status_code,
                                               'answer': self._saia_json(response) or (response.text or '')[:2000]},
                                              indent=1))

    def _saia_track_request(self, pro):
        key = self._saia_secret('saia_tracking_key', _('Saia Tracking key'))
        return self._saia_request('GET', 'customer-api/webservice/track/pro-numbers/%s' % pro,
                                  'Ocp-Apim-Subscription-Key', key, auth=True,
                                  headers={'Api-Version': 'V1', 'Tracking-Key': key})

    def saia_ltl_track(self, shipments):
        self.ensure_one()
        results = {}
        for shipment in shipments:
            pro = self._saia_pro(shipment.pro_number)
            if not pro:
                continue
            try:
                response = self._saia_track_request(pro)
                data = self._saia_check(response, self._saia_json(response))
            except UserError as error:
                _logger.warning('Saia tracking failed for %s: %s', pro, error)
                continue
            info = self._saia_tracking_info(data)
            if info:
                results[shipment.id] = info
        return results

    @api.model
    def _saia_find(self, data, keys):
        """First non-empty value for any of ``keys`` anywhere in the answer (Saia does not
        publish the tracking answer's fields)."""
        if isinstance(data, dict):
            for key in keys:
                for name, value in data.items():
                    if name.lower() == key.lower() and value not in (None, '', [], {}) \
                            and not isinstance(value, (dict, list)):
                        return value
            values = list(data.values())
        elif isinstance(data, list):
            values = data
        else:
            return None
        for value in values:
            if isinstance(value, (dict, list)):
                found = self._saia_find(value, keys)
                if found not in (None, ''):
                    return found
        return None

    def _saia_tracking_info(self, data):
        status = self._saia_find(data, ['statusDescription', 'currentStatus', 'shipmentStatus', 'status',
                                        'activityDescription', 'description'])
        status = ' '.join(str(status or '').split())
        if status.upper() in ('SUCCESS', 'OK', 'FAIL'):
            status = ' '.join(str(self._saia_find(data, ['statusDescription', 'currentStatus', 'shipmentStatus',
                                                         'activityDescription', 'description']) or '').split())
        delivered = self._saia_date(self._saia_find(data, ['deliveryDate', 'deliveredDate', 'actualDeliveryDate']))
        pickup = self._saia_date(self._saia_find(data, ['pickupDate', 'pickUpDate', 'shipDate']))
        estimated = self._saia_date(self._saia_find(data, ['estimatedDeliveryDate', 'etaDate', 'eta']))
        lowered = status.lower()
        info = {}
        if delivered or ('deliver' in lowered and 'out for' not in lowered and 'attempt' not in lowered):
            info['state'] = 'delivered'
            if delivered:
                info['delivered_date'] = fields.Date.to_string(delivered)
            signed = self._saia_find(data, ['signature', 'signedBy', 'receivedBy', 'deliveryReceiver'])
            if signed:
                status = _('%(status)s, signed by %(name)s', status=status or _('Delivered'), name=signed)
        elif pickup or (status and 'pickup' not in lowered and 'not' not in lowered):
            info['state'] = 'in_transit'
        if estimated and info.get('state') != 'delivered':
            status = _('%(status)s, estimated delivery %(date)s', status=status,
                       date=estimated.strftime('%m/%d/%Y')) if status \
                else _('Estimated delivery %s', estimated.strftime('%m/%d/%Y'))
        if status:
            info['status'] = status
        return info

    def saia_ltl_documents(self, shipment):
        self.ensure_one()
        key = (self.sudo().saia_imaging_key or '').strip()
        pro = self._saia_pro(shipment.pro_number)
        if not key or not pro:
            return []
        existing = set(self.env['ir.attachment'].search([
            ('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name'))
        wanted = [(code, label) for code, label in DOCUMENT_TYPES if '%s %s.pdf' % (label, pro) not in existing]
        if not wanted:
            return []
        try:
            response = self._saia_request('GET', 'imaging/api/v1/getImages', 'CA-Key', key, auth=True, params={
                'pro': pro, 'formatType': 'pdf', 'documentFilter': ','.join(code for code, _label in wanted)},
                headers={'Api-Version': 'V1'})
            data = self._saia_check(response, self._saia_json(response))
        except UserError as error:
            _logger.info('Saia documents for %s not available: %s', pro, error)
            return []
        pages = {}
        for image in sorted(self._saia_list(data.get('imageInfo')), key=lambda i: i.get('pageNumber') or 0):
            if str(image.get('status') or '').upper() == 'SUCCESS' and image.get('base64'):
                pages.setdefault(image.get('docType'), []).append(base64.b64decode(image['base64']))
        documents = []
        for code, label in wanted:
            parts = pages.get(code)
            if not parts:
                continue
            content = parts[0]
            if len(parts) > 1:
                try:
                    content = merge_pdf(parts)
                except Exception as error:  # keep the first page rather than nothing
                    _logger.info('Could not merge Saia %s pages for %s: %s', code, pro, error)
            documents.append(('%s %s.pdf' % (label, pro), content))
        return documents

    # ------------------------------------------------------------------ Odoo delivery hooks

    def saia_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('Saia rates come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def saia_send_shipping(self, pickings):
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def saia_get_tracking_link(self, picking):
        pro = digits_only(picking.carrier_tracking_ref)
        return TRACK_URL % pro if pro else False

    def saia_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the pickup with Saia, then cancel the LTL shipment in Odoo.'))

    def _saia_sample_shipment(self):
        shipper = self.env.company.partner_id
        return self.env['selamta.ltl.shipment'].new({
            'shipper_id': shipper.id, 'partner_id': shipper.id, 'carrier_id': self.id,
            'ship_date': fields.Date.context_today(self),
            'unit_ids': [(0, 0, {'unit_type': 'pallet', 'quantity': 1, 'length': 48, 'width': 40,
                                 'height': 48, 'weight': 500, 'class_override': '70'})],
        })

    def action_saia_test_connection(self):
        """Ask Saia for a sample quote from our dock to itself (500 lb, class 70). Books nothing."""
        self.ensure_one()
        key = self._saia_secret('saia_rq_key', _('Saia Rate Quote key'))
        response = self._saia_request('POST', 'rate-quote/webservice/ratequote/customer-api', 'RQ-Key', key,
                                      json=self._saia_rate_request(self._saia_sample_shipment()))
        data = self._saia_check(response, self._saia_json(response))
        rate = self._saia_rates_from_answer(data)[0]
        account = data.get('accountCode') or '-'
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _(
                'Saia login and Rate Quote key work (account %(account)s). Sample quote %(quote)s: %(total).2f, '
                '%(days)s days.', account=account, quote=rate['quote_number'] or '-', total=rate['total'],
                days=rate['transit_days'])},
        }
