# -*- coding: utf-8 -*-
"""R+L Carriers REST API (technology.rlcarriers.com > API Documentation).

Every call sends the API key in an ``apiKey`` header; hosts https://api.rlc.com (production)
and https://apisandbox.rlc.com (sandbox). Answers carry ``Code``, ``Errors`` (list of
{Property, ErrorMessage, ExceptionMessage}) and ``Messages``; money is text like "$1,852.92".

* Rate quote: POST /RateQuote {"RateQuote": {PickupDate MM/dd/yyyy, Origin, Destination
  (ZipOrPostalCode, CountryCode ISO3), Items [Class, Weight, Width, Height, Length] (1-8),
  AdditionalServices}} -> RateQuote.ServiceLevels [Code STD/GSDS/..., Name, QuoteNumber,
  ServiceDays, Charge, NetCharge], RateQuote.Charges [Type, Title, Weight, Rate, Amount],
  CustomerDiscounts, OriginServiceCenter.
* BOL: POST /BillOfLading {"BillOfLading": {...}, "PickupRequest": {"PickupInformation":
  {PickupDate, ReadyTime, CloseTime ("hh:mm tt")}}, "GenerateUniversalPro"} -> ProNumber,
  PickupRequestNumber. BOL PDF: GET /BillOfLading/PrintBOL?ProNumber= -> BolDocument (base64).
* Pickup cancel: DELETE /PickupRequest {PickupRequestId, Reason}.
* Tracking: GET /ShipmentTracing?TraceNumbers=..&TraceType=PRO -> Shipments [ShipmentNumber,
  ShortStatus, LongStatus, EstimatedDelivery, PickupDate/DeliveryDate {Date, Time}, StatusHistory].
* Documents: GET /DocumentRetrieval/GetDocumentTypes?ProNumber= -> DocumentTypes;
  GET /DocumentRetrieval?ProNumber&DocumentTypes&MediaType=PDF -> Documents [Name, Data, Type].
Request and answer shapes were checked against recorded R+L API exchanges in the open-source
friendly_shipping library (RateQuote, BillOfLading, PrintBOL, PickupRequest, DocumentRetrieval).
"""
import base64
import logging
import re
from datetime import datetime

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

HOSTS = {'production': 'https://api.rlc.com', 'sandbox': 'https://apisandbox.rlc.com'}
TIMEOUT = 45
MAX_ITEMS = 8
TRACK_BATCH = 10
# Our accessorial codes -> R+L AdditionalServices (Accessorial Documentation). R+L has no
# delivery notification service; the BOL's delivery instructions carry it.
ACCESSORIALS = {
    'LIFTGATE_DEL': 'DestinationLiftgate',
    'RESIDENTIAL_DEL': 'ResidentialDelivery',
    'LIMITED_ACCESS_DEL': 'LimitedAccessDelivery',
    'INSIDE_DEL': 'InsideDelivery',
    'APPOINTMENT_DEL': 'DeliveryAppointment',
    'LIFTGATE_PU': 'OriginLiftgate',
}
PACKAGE_TYPES = {'pallet': 'PLT', 'box': 'BOX'}
# Rate quote service level codes -> BOL ServiceLevel values.
SERVICE_LEVELS = {
    'STD': 'Standard',
    'GSDS': 'Guaranteed',
    'GSAM': 'GuaranteedByNoon',
    'GSHW': 'GuaranteedHourlyWindow',
}
DOCUMENT_TYPES = [
    ('DeliveryReceipt', 'Delivery receipt'),
    ('WeightCertificate', 'Weight certificate'),
    ('Invoice', 'R+L invoice'),
]
PUBLIC_TRACKING_URL = 'https://www.rlcarriers.com/'


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('rlcarriers', 'R+L Carriers')],
        ondelete={'rlcarriers': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    rlc_environment = fields.Selection(
        [('production', 'Production'),
         ('sandbox', 'Sandbox (BOLs and pickups are not real)')],
        'R+L environment', default='production', required=True,
        help='Rates and tracking always come from R+L production. The sandbox only changes where '
             'BOLs, pickups and documents go.')
    rlc_api_key = fields.Char(
        'R+L API key', groups='base.group_system', copy=False,
        help='API key from technology.rlcarriers.com. It is tied to our R+L account, so quotes '
             'come back at our pricing.')
    rlc_book_shipments = fields.Boolean(
        'Create BOLs through the API',
        help='With this on, choosing R+L in the rate shop creates the R+L BOL and PRO (and the '
             'pickup, if "Schedule the pickup" is on). With it off, the quote is saved and the '
             'shipment is booked on rlcarriers.com.')
    rlc_schedule_pickup = fields.Boolean(
        'Schedule the pickup with the BOL', default=True,
        help='Send a pickup request for the shipment\'s pickup date, ready and close times with '
             'the BOL. Turn off to schedule pickups another way.')
    rlc_universal_pro = fields.Boolean(
        'Universal PRO', default=True,
        help='Ask R+L for a universal PRO, which the driver does not replace with a sticker, so '
             'the PRO on our BOL and labels stays the one R+L tracks. Off: R+L gives a web PRO '
             'starting with W.')
    rlc_food_load = fields.Boolean(
        'Food load', default=True,
        help='Tell R+L the pickup is food (load attribute), so it is not loaded with hazmat or poison.')
    rlc_show_guaranteed = fields.Boolean(
        'Show guaranteed service quotes',
        help='Also list R+L guaranteed service levels in the rate shop, next to standard service.')
    rlc_contact_name = fields.Char('R+L pickup contact')
    rlc_contact_phone = fields.Char('R+L pickup contact phone')
    rlc_contact_email = fields.Char('R+L pickup contact email')

    # ------------------------------------------------------------------ connection

    def ltl_can(self, operation):
        self.ensure_one()
        if self.delivery_type == 'rlcarriers' and operation == 'book' and not self.rlc_book_shipments:
            return False
        return super().ltl_can(operation)

    def _rlc_key(self):
        self.ensure_one()
        key = (self.sudo().rlc_api_key or '').strip()
        if not key:
            raise UserError(_('Enter the R+L API key on the %s shipping method (R+L tab) first.', self.name))
        return key

    def _rlc_host(self, live=False):
        return HOSTS['production' if live or self.rlc_environment != 'sandbox' else 'sandbox']

    def _rlc_call(self, method, path, live=False, **kwargs):
        """Call the R+L API and return the JSON answer; raise UserError with R+L's messages."""
        self.ensure_one()
        url = '%s/%s' % (self._rlc_host(live), path)
        headers = {'apiKey': self._rlc_key(), 'Accept': 'application/json'}
        if 'json' in kwargs:
            headers['Content-Type'] = 'application/json'
        _logger.info('R+L %s %s', method, url)
        try:
            response = requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as error:
            raise UserError(_('Could not reach R+L: %s', error)) from error
        try:
            data = response.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            text = (response.text or '').strip().strip('"')
            if 'api key' in text.lower():
                raise UserError(_('R+L refused the API key (%(text)s). Check it on the %(name)s shipping method.',
                                  text=text, name=self.name))
            raise UserError(_('R+L answered %(status)s: %(text)s',
                              status=response.status_code, text=text[:300] or _('no details')))
        errors = self._rlc_errors(data)
        if errors or response.status_code >= 400:
            message = '; '.join(errors) or '; '.join(data.get('Messages') or []) or data.get('Message') \
                or (response.text or '')[:300]
            if 'api key' in (message or '').lower():
                raise UserError(_('R+L refused the API key (%(text)s). Check it on the %(name)s shipping method.',
                                  text=message, name=self.name))
            raise UserError(_('R+L: %s', message or _('error %s', response.status_code)))
        return data

    @api.model
    def _rlc_errors(self, data):
        messages = []
        for error in data.get('Errors') or []:
            if isinstance(error, dict):
                text = error.get('ErrorMessage') or error.get('ExceptionMessage') or ''
                prop = (error.get('Property') or '').replace('request.', '')
                if text:
                    messages.append('%s (%s)' % (text, prop) if prop else text)
            elif error:
                messages.append(str(error))
        return messages

    @api.model
    def _rlc_money(self, value):
        """'$1,852.92' -> 1852.92; '($12.00)' and '-$12.00' -> -12.0."""
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or '').strip()
        negative = text.startswith('-') or (text.startswith('(') and text.endswith(')'))
        number = re.sub(r'[^0-9.]', '', text)
        try:
            amount = float(number) if number else 0.0
        except ValueError:
            return 0.0
        return -amount if negative else amount

    # ------------------------------------------------------------------ request parts

    @api.model
    def _rlc_country(self, partner):
        code = partner.country_id.code or 'US'
        if code not in ('US', 'CA'):
            raise UserError(_('R+L ships within the United States and Canada only here (%s).', partner.display_name))
        return 'CAN' if code == 'CA' else 'USA'

    @api.model
    def _rlc_zip(self, partner):
        if partner.country_id.code == 'CA':
            return ''.join(ch for ch in (partner.zip or '') if ch.isalnum()).upper()[:6]
        postal = digits_only(partner.zip)[:5]
        if len(postal) != 5:
            raise UserError(_('%s needs a 5-digit ZIP code for R+L.', partner.display_name))
        return postal

    @api.model
    def _rlc_phone(self, value):
        phone = digits_only(value)
        if len(phone) == 11 and phone.startswith('1'):
            phone = phone[1:]
        return '%s-%s-%s' % (phone[:3], phone[3:6], phone[6:10]) if len(phone) >= 10 else ''

    @api.model
    def _rlc_point(self, partner):
        return {
            'City': (partner.city or '')[:30],
            'StateOrProvince': partner.state_id.code or '',
            'ZipOrPostalCode': self._rlc_zip(partner),
            'CountryCode': self._rlc_country(partner),
        }

    @api.model
    def _rlc_company_name(self, partner):
        return (partner.commercial_partner_id.name if partner.parent_id else partner.name) or ''

    def _rlc_address(self, partner, label, phone=None, email=None):
        if not partner.street or not partner.city or not partner.state_id:
            raise UserError(_('%(name)s needs a street, city and state for an R+L BOL (%(label)s).',
                              name=partner.display_name, label=label))
        address = dict(self._rlc_point(partner), **{
            'CompanyName': self._rlc_company_name(partner)[:40],
            'AddressLine1': partner.street[:40],
        })
        if partner.street2:
            address['AddressLine2'] = partner.street2[:40]
        phone = self._rlc_phone(phone or partner.phone or partner.mobile or partner.commercial_partner_id.phone)
        if phone:
            address['PhoneNumber'] = phone
        email = email or partner.email
        if email:
            address['EmailAddress'] = email[:60]
        return address

    @api.model
    def _rlc_units(self, shipment):
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the pallets or boxes to %s first.', shipment.name))
        for unit in units:
            if not unit.freight_class or not unit.weight:
                raise UserError(_('Measure and weigh every pallet or box on %s first.', shipment.name))
        return units

    @api.model
    def _rlc_class(self, freight_class):
        try:
            return '%g' % float(freight_class)
        except (TypeError, ValueError):
            return str(freight_class)

    def _rlc_accessorial_codes(self, shipment):
        codes = []
        for service in shipment.accessorial_ids:
            code = ACCESSORIALS.get(service.code)
            if code and code not in codes:
                codes.append(code)
        return codes

    def _rlc_rate_items(self, shipment):
        """One item per pallet or box with its own weight and dimensions when that fits R+L's
        limit of 8 items; otherwise one item per line with the line's total weight."""
        units = self._rlc_units(shipment)
        pieces = sum(max(int(unit.quantity or 1), 1) for unit in units)
        items = []
        if pieces <= MAX_ITEMS:
            for unit in units:
                count = max(int(unit.quantity or 1), 1)
                total = int(round(unit.weight))
                each = total // count
                for index in range(count):
                    weight = each + (total - each * count if index == count - 1 else 0)
                    item = {'Class': self._rlc_class(unit.freight_class), 'Weight': max(weight, 1)}
                    if unit.length and unit.width and unit.height:
                        item.update({'Length': round(unit.length, 1), 'Width': round(unit.width, 1),
                                     'Height': round(unit.height, 1)})
                    items.append(item)
        else:
            if len(units) > MAX_ITEMS:
                raise UserError(_('R+L rates at most %s lines per shipment.', MAX_ITEMS))
            items = [{'Class': self._rlc_class(unit.freight_class), 'Weight': max(int(round(unit.weight)), 1)}
                     for unit in units]
        return items

    def _rlc_rate_request(self, shipment):
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        quote = {
            'PickupDate': ship_date.strftime('%m/%d/%Y'),
            'Origin': self._rlc_point(shipment.shipper_id),
            'Destination': self._rlc_point(shipment.partner_id),
            'Items': self._rlc_rate_items(shipment),
        }
        codes = self._rlc_accessorial_codes(shipment)
        if codes:
            quote['AdditionalServices'] = codes
        return {'RateQuote': quote}

    @api.model
    def _rlc_time(self, hours):
        """10.5 -> '10:30 AM'."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        hour = min(hour, 23)
        return '%02d:%02d %s' % (hour % 12 or 12, minute, 'AM' if hour < 12 else 'PM')

    @api.model
    def _rlc_references(self, shipment):
        po = sale = False
        for picking in shipment.picking_ids:
            order = picking.sale_id if 'sale_id' in picking._fields else False
            po = po or (order.client_order_ref if order else False)
            sale = sale or picking.origin
        return po, sale

    def _rlc_instructions(self, shipment):
        lines = list(shipment._bol_delivery_lines())
        if shipment.pickup_instructions:
            lines.append('PICKUP: %s' % ' '.join(shipment.pickup_instructions.split()))
        return ', '.join(lines)[:250]

    def _rlc_bol_request(self, shipment, rate):
        units = self._rlc_units(shipment)
        company = shipment.company_id
        shipper = shipment.shipper_id
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        contact_phone = self.rlc_contact_phone or shipper.phone or company.phone
        contact_email = self.rlc_contact_email or shipper.email or company.email
        shipper_address = self._rlc_address(shipper, _('shipper'), phone=contact_phone, email=contact_email)
        if not shipper_address.get('PhoneNumber'):
            raise UserError(_('R+L needs a phone number for the shipper: fill in the pickup contact phone on '
                              'the %s shipping method.', self.name))
        consignee = self._rlc_address(shipment.partner_id, _('consignee'))
        if shipment.partner_id.parent_id and shipment.partner_id.name:
            consignee['Attention'] = shipment.partner_id.name[:40]
        bill = {
            'BOLDate': ship_date.strftime('%m/%d/%Y'),
            'FreightChargePaymentMethod': 'Prepaid',
            'ServiceLevel': rate.get('rlc_service_level') or 'Standard',
            'Shipper': shipper_address,
            'Consignee': consignee,
            'BillTo': self._rlc_address(company.partner_id, _('bill to'), phone=contact_phone, email=contact_email),
            'Items': [],
        }
        for unit in units:
            item = {
                'Class': self._rlc_class(unit.freight_class),
                'Pieces': max(int(unit.quantity or 1), 1),
                'Weight': max(int(round(unit.weight)), 1),
                'PackageType': PACKAGE_TYPES.get(unit.unit_type, 'PLT'),
                'Description': (unit.description or _('Freight'))[:100],
                'IsHazmat': False,
            }
            if unit.nmfc_item:
                item['NMFCItemNumber'] = digits_only(unit.nmfc_item) or unit.nmfc_item
                item['NMFCSubNumber'] = digits_only(unit.nmfc_sub) or '00'
            bill['Items'].append(item)
        codes = self._rlc_accessorial_codes(shipment)
        if codes:
            bill['AdditionalServices'] = codes
        po, _sale = self._rlc_references(shipment)
        references = {'ShipperNumber': (shipment.bol_reference or '')[:30]}
        if rate.get('quote_number'):
            references['RateQuoteNumber'] = str(rate['quote_number'])
        if po:
            references['PONumber'] = po[:30]
        bill['ReferenceNumbers'] = references
        instructions = self._rlc_instructions(shipment)
        if instructions:
            bill['SpecialInstructions'] = instructions
        request = {'BillOfLading': bill, 'GenerateUniversalPro': bool(self.rlc_universal_pro)}
        if self.rlc_schedule_pickup:
            pickup = {
                'PickupDate': ship_date.strftime('%m/%d/%Y'),
                'ReadyTime': self._rlc_time(shipment.pickup_ready_time),
                'CloseTime': self._rlc_time(shipment.pickup_close_time),
            }
            notes = ['BOL %s' % shipment.bol_reference]
            if shipment.pickup_instructions:
                notes.append(' '.join(shipment.pickup_instructions.split()))
            pickup['AdditionalInstructions'] = '. '.join(notes)[:200]
            if self.rlc_food_load:
                pickup['LoadAttributes'] = ['Food']
            request['PickupRequest'] = {'PickupInformation': pickup}
        return request

    # ------------------------------------------------------------------ responses

    def _rlc_rates_from_answer(self, data):
        quote = data.get('RateQuote') or {}
        levels = quote.get('ServiceLevels') or []
        standard = next((level for level in levels if level.get('Code') == 'STD'), levels[0] if levels else None)
        if not standard:
            messages = (quote.get('CategorizedMessages') or {}).get('RatesMessages') or data.get('Messages') or []
            raise UserError(_('R+L returned no rate: %s', '; '.join(messages) or _('no details')))
        center = quote.get('OriginServiceCenter') or {}
        base_lines = self._rlc_charge_lines(quote, standard)
        chosen = [standard] + ([level for level in levels if level is not standard and level.get('Code') != 'STD']
                               if self.rlc_show_guaranteed else [])
        rates = []
        for level in chosen:
            total = self._rlc_money(level.get('NetCharge'))
            if total <= 0:
                continue
            charges = [dict(line) for line in base_lines]
            if level is not standard:
                charges.append({'code': level.get('Code') or 'GTD',
                                'name': level.get('Name') or level.get('Title') or _('Guaranteed service'),
                                'amount': self._rlc_money(level.get('Charge'))})
            difference = round(total - sum(c['amount'] for c in charges), 2)
            if abs(difference) >= 0.01:
                charges.append({'code': 'OTHER', 'name': _('Fuel and other charges (difference to R+L total)'),
                                'amount': difference})
            code = level.get('Code') or 'STD'
            name = level.get('Name') or level.get('Title') or _('Standard Service')
            rates.append({
                'service': _('R+L %s', name),
                'total': total,
                'transit_days': int(level.get('ServiceDays') or 0),
                'quote_number': str(level.get('QuoteNumber') or '') or False,
                'charges': charges,
                'rlc_service_code': code,
                'rlc_service_level': SERVICE_LEVELS.get(code, 'Standard'),
                'rlc_service_center': ' '.join(filter(None, [
                    center.get('Location') or center.get('Code'),
                    center.get('Phone') and '(%s)' % center['Phone']])) or False,
            })
        if not rates:
            raise UserError(_('R+L returned no rate for this shipment.'))
        return rates

    def _rlc_charge_lines(self, quote, standard):
        """Charge lines for standard service. R+L lists per-class linehaul lines and gives the
        gross charge and our discount separately; whatever else is in the net charge (fuel,
        services) becomes the difference line."""
        lines = []
        for charge in quote.get('Charges') or []:
            amount = self._rlc_money(charge.get('Amount'))
            if not amount:
                continue
            title = (charge.get('Title') or '').strip()
            if title.lower().startswith('class'):
                name = _('Linehaul before discount, %(title)s, %(weight)s lb', title=title.lower(),
                         weight=charge.get('Weight') or '-')
                code = 'LINEHAUL'
            else:
                name = title or charge.get('Type') or _('Charge')
                code = (charge.get('Type') or title or 'CHARGE')[:20]
            lines.append({'code': code, 'name': name, 'amount': amount})
        total = self._rlc_money(standard.get('NetCharge'))
        if abs(round(total - sum(line['amount'] for line in lines), 2)) < 0.01:
            return lines  # the lines already add up to the net charge
        has_discount = any(line['amount'] < 0 or 'disc' in line['name'].lower()
                           for line in lines if line['code'] != 'LINEHAUL')
        if not has_discount:
            gross = self._rlc_money(standard.get('Charge'))
            linehaul = sum(line['amount'] for line in lines if line['code'] == 'LINEHAUL')
            if gross and abs(round(gross - linehaul, 2)) >= 0.01:
                lines.append({'code': 'MIN', 'name': _('Gross charge adjustment (minimum charge or weight break)'),
                              'amount': round(gross - linehaul, 2)})
            discount = self._rlc_money(quote.get('CustomerDiscounts'))
            if discount:
                lines.append({'code': 'DISC', 'name': _('Discount'), 'amount': -abs(discount)})
        return lines

    @api.model
    def _rlc_date(self, value):
        if isinstance(value, dict):
            value = value.get('Date')
        value = (value or '').strip()
        for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
            try:
                parsed = datetime.strptime(value[:10], fmt).date()
            except ValueError:
                continue
            return parsed if parsed.year > 1900 else False
        return False

    @api.model
    def _rlc_key_of(self, number):
        return re.sub(r'[^0-9A-Z]', '', str(number or '').upper())

    # ------------------------------------------------------------------ selamta_ltl hooks

    def rlcarriers_ltl_rate(self, shipment):
        self.ensure_one()
        data = self._rlc_call('POST', 'RateQuote', live=True, json=self._rlc_rate_request(shipment))
        return self._rlc_rates_from_answer(data)

    def rlcarriers_ltl_book(self, shipment, rate):
        self.ensure_one()
        if not self.rlc_book_shipments:
            raise UserError(_('BOLs through the R+L API are off on %s; book on rlcarriers.com and type the PRO.',
                              self.name))
        data = self._rlc_call('POST', 'BillOfLading', json=self._rlc_bol_request(shipment, rate))
        pro = str(data.get('ProNumber') or '').strip()
        if not pro:
            raise UserError(_('R+L did not return a PRO: %s', '; '.join(data.get('Messages') or []) or _('no details')))
        pickup = str(data.get('PickupRequestNumber') or data.get('PickupRequestId') or '').strip()
        notes = [_('R+L BOL created, PRO %s.', pro)]
        if pickup:
            notes.append(_('R+L pickup request %s.', pickup))
        elif self.rlc_schedule_pickup:
            notes.append(_('R+L did not confirm a pickup request: schedule the pickup on rlcarriers.com.'))
        documents = []
        try:
            pdf = self._rlc_call('GET', 'BillOfLading/PrintBOL', params={'ProNumber': pro}).get('BolDocument')
            if pdf:
                documents.append(('R+L BOL (carrier copy) %s.pdf' % pro, base64.b64decode(pdf)))
        except UserError as error:
            notes.append(_('R+L BOL PDF not available yet: %s', error.args[0]))
        if self.rlc_environment == 'sandbox':
            notes.append(_('Booked in the R+L SANDBOX: nothing will be picked up.'))
        if rate.get('rlc_service_center'):
            shipment.rlc_service_center = rate['rlc_service_center']
        shipment.message_post(body=Markup('<br/>').join(notes))
        return {'pro_number': pro, 'pickup_number': pickup or False, 'documents': documents}

    def rlcarriers_ltl_cancel(self, shipment):
        self.ensure_one()
        pickup = digits_only(shipment.pickup_number)
        if not pickup:
            raise UserError(_('%s has no R+L pickup request number; cancel it with R+L by phone.', shipment.name))
        self._rlc_call('DELETE', 'PickupRequest', json={
            'PickupRequestId': int(pickup), 'Reason': 'Cancelled by shipper (%s)' % shipment.bol_reference})
        return True

    def rlcarriers_ltl_track(self, shipments):
        self.ensure_one()
        searches = {}
        for shipment in shipments:
            key = self._rlc_key_of(shipment.pro_number)
            if key:
                searches[key] = shipment
        results = {}
        keys = list(searches)
        for start in range(0, len(keys), TRACK_BATCH):
            batch = keys[start:start + TRACK_BATCH]
            try:
                data = self._rlc_call('GET', 'ShipmentTracing', live=True,
                                      params=[('TraceNumbers', key) for key in batch] + [('TraceType', 'PRO')])
            except UserError as error:
                _logger.warning('R+L tracking failed for %s: %s', ', '.join(batch), error)
                continue
            for entry in data.get('Shipments') or []:
                details = entry.get('Shipment') if isinstance(entry.get('Shipment'), dict) else entry
                key = self._rlc_key_of(details.get('ShipmentNumber'))
                shipment = searches.get(key) or next(
                    (s for k, s in searches.items() if digits_only(k) and digits_only(k) == digits_only(key)), None)
                if shipment:
                    results[shipment.id] = self._rlc_tracking_info(details)
        return results

    @api.model
    def _rlc_tracking_info(self, details):
        info = {}
        short = (details.get('ShortStatus') or '').strip()
        long_status = (details.get('LongStatus') or '').strip()
        delivered = self._rlc_date(details.get('DeliveryDate'))
        lowered = ('%s %s' % (short, long_status)).lower()
        said_delivered = (lowered.startswith('delivered') or ' delivered' in lowered) and 'out for' not in lowered
        if delivered or said_delivered:
            info['state'] = 'delivered'
            if delivered:
                info['delivered_date'] = fields.Date.to_string(delivered)
        elif self._rlc_date(details.get('PickupDate')) or details.get('StatusHistory'):
            info['state'] = 'in_transit'
        text = long_status or short
        estimated = (details.get('EstimatedDelivery') or '').strip()
        if estimated and info.get('state') != 'delivered':
            text = _('%(status)s, estimated delivery %(date)s', status=text, date=estimated) if text \
                else _('Estimated delivery %s', estimated)
        if text:
            info['status'] = text
        return info

    def rlcarriers_ltl_documents(self, shipment):
        self.ensure_one()
        pro = self._rlc_key_of(shipment.pro_number)
        if not pro:
            raise UserError(_('%s has no PRO yet.', shipment.name))
        existing = set(self.env['ir.attachment'].search([
            ('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name'))
        try:
            available = set(self._rlc_call('GET', 'DocumentRetrieval/GetDocumentTypes',
                                           params={'ProNumber': pro}).get('DocumentTypes') or [])
        except UserError as error:
            _logger.info('R+L document list for %s not available: %s', pro, error)
            return []
        documents = []
        for doc_type, label in DOCUMENT_TYPES:
            name = '%s %s.pdf' % (label, pro)
            if doc_type not in available or name in existing:
                continue
            try:
                data = self._rlc_call('GET', 'DocumentRetrieval', params={
                    'ProNumber': pro, 'DocumentTypes': doc_type, 'MediaType': 'PDF'})
            except UserError as error:
                _logger.info('R+L %s for %s not available: %s', doc_type, pro, error)
                continue
            for document in (data.get('Documents') or [])[:1]:
                if document.get('Data'):
                    documents.append((name, base64.b64decode(document['Data'])))
        return documents

    # ------------------------------------------------------------------ Odoo delivery hooks

    def rlcarriers_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('R+L rates come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def rlcarriers_send_shipping(self, pickings):
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def rlcarriers_get_tracking_link(self, picking):
        return PUBLIC_TRACKING_URL if picking.carrier_tracking_ref else False

    def rlcarriers_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the LTL shipment in Odoo; it cancels the R+L pickup request.'))

    def action_rlc_test_connection(self):
        """Ask R+L for a sample quote from our dock to itself (500 lb, class 70). Books nothing."""
        self.ensure_one()
        shipper = self.env.company.partner_id
        shipment = self.env['selamta.ltl.shipment'].new({
            'shipper_id': shipper.id, 'partner_id': shipper.id, 'carrier_id': self.id,
            'ship_date': fields.Date.context_today(self),
            'unit_ids': [(0, 0, {'unit_type': 'pallet', 'quantity': 1, 'length': 48, 'width': 40,
                                 'height': 48, 'weight': 500, 'class_override': '70'})],
        })
        data = self._rlc_call('POST', 'RateQuote', live=True, json=self._rlc_rate_request(shipment))
        rate = self._rlc_rates_from_answer(data)[0]
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _(
                'R+L API key works. Sample quote %(quote)s: %(total).2f, %(days)s days.',
                quote=rate['quote_number'] or '-', total=rate['total'], days=rate['transit_days'])},
        }
