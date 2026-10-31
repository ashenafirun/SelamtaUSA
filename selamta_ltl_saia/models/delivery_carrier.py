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
  {deficitAmount}, rateDetailItems [{class, weight, rate, amount}], rateAccessorials [{code,
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

    # ------------------------------------------------------------------ connection

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
        for charge in self._saia_list(data.get('rateAccessorials')):
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
