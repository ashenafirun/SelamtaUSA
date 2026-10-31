# -*- coding: utf-8 -*-
"""Roadrunner Freight web services (freight.rrts.com > System Integration).

Three services are used:

* Rate quote, SOAP: https://webservices.rrts.com/rating/ratequote.asmx, operation
  RateQuoteByAccountV2. The freight.rrts.com username and password go in the SOAP header,
  our account number in the request. Rating books nothing, so it always uses production.
* BOL API, JSON: /BOL/api/bolrequest with HTTP basic authentication (same username and
  password). One call creates the BOL, gets the PRO, schedules the pickup (QuickPickup)
  and returns the BOL PDF. In "Test" the BOL goes to webservices-test.rrts.com, where
  nothing is picked up.
* Tracking Web API, JSON: /TrackWebApi/api/values/{PROs or pickup numbers} and
  /TrackWebApi/api/images. Tracking by PRO or pickup number and delivery receipt (POD)
  images need no sign-in. BOL, weight & inspection and invoice images need the
  Application ID and API key from freight.rrts.com (Tools > Tracking), sent in an
  "amx" header: HMAC-SHA256 of AppId + METHOD + url-encoded URL + Unix time + nonce.
"""
import base64
import hashlib
import hmac
import logging
import math
import time
import uuid
from collections import OrderedDict
from datetime import date
from urllib.parse import quote_plus

import requests
from markupsafe import Markup
from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

RATE_URL = 'https://webservices.rrts.com/rating/ratequote.asmx'
RATE_NS = 'https://webservices.rrts.com/ratequote/'
RATE_OPERATION = 'RateQuoteByAccountV2'
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
BOL_URLS = {
    'production': 'https://webservices.rrts.com/BOL/api/bolrequest',
    'test': 'https://webservices-test.rrts.com/bol/api/bolrequest',
}
TRACK_URL = 'https://webservices.rrts.com/TrackWebApi/api/values/'
IMAGES_URL = 'https://webservices.rrts.com/TrackWebApi/api/images'
PUBLIC_TRACKING_URL = 'https://freight.rrts.com/Tools/Tracking'
TIMEOUT = 45
MAX_COMMODITIES = 9        # BOL API limit
MAX_RATE_CLASSES = 10      # rate quote limit
MAX_ACCESSORIALS = 5       # BOL API limit
MAX_INSTRUCTIONS = 256     # BOL API limit (the first 188 characters print on Roadrunner's BOL)
TRACK_BATCH = 20

# Our accessorial codes -> Roadrunner accessorial / service codes (BOL API Appendix B,
# rate quote ServiceCode).
ACCESSORIALS = {
    'LIFTGATE_DEL': 'LGD',
    'RESIDENTIAL_DEL': 'RSD',
    'LIMITED_ACCESS_DEL': 'LTD',
    'INSIDE_DEL': 'ID',
    'APPOINTMENT_DEL': 'APT',
    'NOTIFY_DEL': 'NC',
    'LIFTGATE_PU': 'LGP',
}
UNIT_DESC = {'pallet': 'Pallet', 'box': 'Box'}
CHARGE_NAMES = {
    'DIS': 'Discount',
    'FSC': 'Fuel surcharge',
    'FSB': 'Beyond fuel surcharge',
    'LHS': 'Linehaul surcharge',
    'HND': 'Linehaul surcharge',
    'AS': 'Linehaul, rated at the next weight break',
    'LGD': 'Liftgate at delivery',
    'LGP': 'Liftgate at pickup',
    'RSD': 'Residential delivery',
    'LTD': 'Limited access delivery',
    'ID': 'Inside delivery',
    'APT': 'Delivery appointment',
    'NC': 'Call before delivery',
    'GWD': 'Grocery warehouse delivery',
}
NEGATIVE_CHARGES = {'DIS'}
MOVING_CODES = {'PU', 'CLO', 'DSP', 'ARV', 'UNL', 'ARQ', 'OFD'}
POD_TYPE = 'POD'
SIGNED_IMAGE_TYPES = ['BOL', 'WI', 'INVOICE']
DOCUMENT_NAMES = {
    'POD': 'Delivery receipt', 'WI': 'Weight and inspection', 'BOL': 'Roadrunner signed BOL',
    'INVOICE': 'Roadrunner invoice',
}


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('roadrunner', 'Roadrunner Freight')],
        ondelete={'roadrunner': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    rrts_environment = fields.Selection(
        [('test', 'Test - BOLs go to Roadrunner\'s test system, nothing is picked up'),
         ('production', 'Production')],
        'Roadrunner environment', default='test', required=True)
    rrts_account_number = fields.Char(
        'Roadrunner account number',
        help='Our Roadrunner account: the "Bill To" number on Roadrunner invoices.')
    rrts_username = fields.Char(
        'freight.rrts.com username', groups='base.group_system', copy=False,
        help='The username used to sign in on freight.rrts.com. Roadrunner\'s rate quote and '
             'BOL services use the website sign-in.')
    rrts_password = fields.Char('freight.rrts.com password', groups='base.group_system', copy=False)
    rrts_app_id = fields.Char(
        'Tracking application ID', groups='base.group_system', copy=False,
        help='Optional. From freight.rrts.com, Tools > Tracking (API key). Needed only for '
             'the signed BOL, weight & inspection and invoice images; tracking and delivery '
             'receipts work without it.')
    rrts_api_key = fields.Char('Tracking API key', groups='base.group_system', copy=False)
    rrts_schedule_pickup = fields.Boolean(
        'Schedule Roadrunner pickup when booking', default=True,
        help='Ask Roadrunner for a pickup (QuickPickup) in the same call that creates the BOL, '
             'for the shipment\'s pickup date, ready time and dock closing time.')
    rrts_label_style = fields.Selection(
        [('4', '4x6 labels'), ('6', '6 labels per sheet'), ('F', 'Full page labels')],
        'Roadrunner labels with the BOL',
        help='Leave empty: we print our own 4x6 labels from the shipment.')
    rrts_contact_name = fields.Char(
        'Shipping contact name', help='Shipper contact on the BOL and requester of the pickup.')
    rrts_contact_email = fields.Char('Shipping contact email')
    rrts_contact_phone = fields.Char('Shipping contact phone')

    # ------------------------------------------------------------------ connection

    def _rrts_credentials(self):
        self.ensure_one()
        carrier = self.sudo()
        if not carrier.rrts_username or not carrier.rrts_password:
            raise UserError(_(
                'Enter the freight.rrts.com username and password on the %s shipping method '
                '(Roadrunner tab) first.', carrier.name))
        return carrier.rrts_username.strip(), carrier.rrts_password

    def _rrts_account(self):
        self.ensure_one()
        account = digits_only(self.rrts_account_number)
        if not account:
            raise UserError(_(
                'Enter the Roadrunner account number (Bill To on Roadrunner invoices) on the %s '
                'shipping method first.', self.name))
        return account

    @api.model
    def _rrts_request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', TIMEOUT)
        _logger.info('Roadrunner %s %s', method, url)
        try:
            return requests.request(method, url, **kwargs)
        except requests.RequestException as error:
            raise UserError(_('Could not reach Roadrunner: %s', error)) from error

    @api.model
    def _rrts_json(self, response):
        try:
            return response.json() if response.content else {}
        except ValueError:
            return {}

    def _rrts_amx_header(self, method, url):
        """Roadrunner tracking "amx" authorization: HMAC-SHA256 with the API key over
        APPID + METHOD + url-encoded full URL (upper-case %XX, like .NET
        HttpUtility.UrlEncode with capitals) + Unix time + nonce, Base64."""
        self.ensure_one()
        carrier = self.sudo()
        app_id = (carrier.rrts_app_id or '').strip().upper()
        api_key = (carrier.rrts_api_key or '').strip()
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        raw = '%s%s%s%s%s' % (app_id, method.upper(), quote_plus(url, safe='!*()'), timestamp, nonce)
        signature = base64.b64encode(
            hmac.new(api_key.encode('ascii'), raw.encode('utf-8'), hashlib.sha256).digest()).decode()
        return 'amx %s:%s:%s:%s' % (app_id, signature, nonce, timestamp)

    def _rrts_can_sign(self):
        carrier = self.sudo()
        return bool(carrier.rrts_app_id and carrier.rrts_api_key)

    # ------------------------------------------------------------------ request parts

    @api.model
    def _rrts_zip(self, partner):
        country = partner.country_id.code or 'US'
        if country == 'CA':
            postal = ''.join(ch for ch in (partner.zip or '') if ch.isalnum()).upper()
            if len(postal) != 6:
                raise UserError(_('%s needs a 6-character Canadian postal code for Roadrunner.',
                                  partner.display_name))
            return postal
        postal = digits_only(partner.zip)[:5]
        if len(postal) != 5:
            raise UserError(_('%s needs a 5-digit ZIP code for Roadrunner.', partner.display_name))
        return postal

    @api.model
    def _rrts_phone(self, value, label):
        phone = digits_only(value)
        if len(phone) == 11 and phone.startswith('1'):
            phone = phone[1:]
        if len(phone) < 10:
            raise UserError(_('Roadrunner needs a 10-digit phone number for the %s.', label))
        phone = phone[:10]
        return '(%s) %s-%s' % (phone[:3], phone[3:6], phone[6:])

    @api.model
    def _rrts_address(self, partner, label, contact=None):
        country = partner.country_id.code or 'US'
        if country not in ('US', 'CA'):
            raise UserError(_('Roadrunner ships within the United States and Canada only (%s).',
                              partner.display_name))
        if not partner.street or not partner.city or not partner.state_id:
            raise UserError(_('%(name)s needs a street, city and state for a Roadrunner BOL (%(label)s).',
                              name=partner.display_name, label=label))
        company = partner.commercial_partner_id.name if partner.parent_id else partner.name
        person = contact or (partner.name if partner.parent_id else False) or _('Receiving')
        address = {
            'Company': (company or '')[:60],
            'Contact': person[:60],
            'Address': ', '.join(filter(None, [partner.street, partner.street2]))[:60],
            'City': partner.city[:30],
            'State': partner.state_id.code,
            'Country': 'Canada' if country == 'CA' else 'United States',
            'Zip': self._rrts_zip(partner),
            'Phone': self._rrts_phone(
                partner.phone or partner.mobile or partner.commercial_partner_id.phone,
                '%s (%s)' % (label, partner.display_name)),
        }
        if partner.email:
            address['Email'] = partner.email[:100]
        return address

    def _rrts_accessorial_codes(self, shipment):
        codes = OrderedDict()
        for accessorial in shipment.accessorial_ids:
            code = ACCESSORIALS.get(accessorial.code)
            if code:
                codes[code] = True
        return list(codes)

    @api.model
    def _rrts_check_units(self, shipment):
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the pallets or boxes to %s first.', shipment.name))
        for unit in units:
            if not unit.freight_class or not unit.weight:
                raise UserError(_('Measure and weigh every pallet or box on %s first.', shipment.name))
        return units

    @api.model
    def _rrts_commodities(self, shipment):
        units = self._rrts_check_units(shipment)
        if len(units) > MAX_COMMODITIES:
            raise UserError(_(
                'Roadrunner takes at most %(max)s pallet or box lines on one BOL; %(name)s has '
                '%(count)s. Combine lines of the same size and class (Count column).',
                max=MAX_COMMODITIES, name=shipment.name, count=len(units)))
        commodities = []
        for unit in units:
            kind = UNIT_DESC.get(unit.unit_type, 'Pallet')
            text = unit.description or _('Freight')
            if shipment.consolidated and unit.for_text:
                text = '%s - for %s' % (text, unit.for_text)
            item = {
                'UnitDesc': kind,
                'UnitQnty': unit.quantity,
                'PkgDesc': kind,
                'PkgQnty': unit.quantity,
                'Description': text[:100],
                'Weight': round(unit.weight),
                'ClassCode': float(unit.freight_class),
                'Length': int(math.ceil(unit.length or 0)),
                'Width': int(math.ceil(unit.width or 0)),
                'Height': int(math.ceil(unit.height or 0)),
                'Cube': 0,  # 0 = Roadrunner calculates it from length, width and height
            }
            if unit.nmfc_item:
                item['NMFC'] = digits_only(unit.nmfc_item)[:6] or unit.nmfc_item[:6]
                if unit.nmfc_sub:
                    item['NMFCSub'] = unit.nmfc_sub[:3]
            commodities.append(item)
        return commodities

    @api.model
    def _rrts_time(self, hours):
        """10.5 -> '10:30' (24-hour, as QuickPickup expects)."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        return '%02d:%02d' % (min(hour, 23), minute)

    @api.model
    def _rrts_instructions(self, shipment):
        text = ', '.join(shipment._bol_delivery_lines())
        if shipment.pickup_instructions:
            pickup = ' '.join(shipment.pickup_instructions.split())
            text = '%s; PICKUP: %s' % (text, pickup) if text else 'PICKUP: %s' % pickup
        return text[:MAX_INSTRUCTIONS]

    @api.model
    def _rrts_references(self, shipment):
        references, seen = [], set()
        for picking in shipment.picking_ids:
            sale = picking.sale_id if 'sale_id' in picking._fields else False
            for number, kind in ((sale.client_order_ref if sale else False, 'PO'), (picking.origin, 'SO')):
                if number and (number, kind) not in seen:
                    seen.add((number, kind))
                    references.append({'RefNo': number[:30], 'RefType': kind})
        return references

    def _rrts_bol_request(self, shipment):
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        request = {
            'MainAccountNumber': self._rrts_account(),
            'PayTerms': 'P',
            'ShipDt': fields.Date.to_string(ship_date),
            'BOLNumber': shipment.bol_reference,
            'ProNumAutoGenerated': True,
            'ShipperAddr': self._rrts_address(
                shipment.shipper_id, _('shipper'), contact=self.rrts_contact_name or self.env.user.name),
            'ConsigneeAddr': self._rrts_address(shipment.partner_id, _('consignee')),
            'Commodities': self._rrts_commodities(shipment),
            'GenerateBOL': True,
            'GetRateQuote': True,
            'CustomerType': 'O',
            'PrintLabel': False,
        }
        requester_phone = self.rrts_contact_phone or shipment.shipper_id.phone or shipment.company_id.phone
        request['ReqName'] = (self.rrts_contact_name or self.env.user.name or '')[:60]
        if requester_phone:
            request['ReqPhone'] = self._rrts_phone(requester_phone, _('shipping contact'))
        requester_email = self.rrts_contact_email or shipment.shipper_id.email or shipment.company_id.email
        if requester_email:
            request['ReqEmail'] = requester_email[:100]
        codes = self._rrts_accessorial_codes(shipment)
        if len(codes) > MAX_ACCESSORIALS:
            raise UserError(_('Roadrunner takes at most %s services per BOL.', MAX_ACCESSORIALS))
        if codes:
            request['Accessorials'] = [{'AccessorialCode': code} for code in codes]
        instructions = self._rrts_instructions(shipment)
        if instructions:
            request['Instructions'] = instructions
        references = self._rrts_references(shipment)
        if references:
            request['BOLCustomerReference'] = references
            po = next((r['RefNo'] for r in references if r['RefType'] == 'PO'), False)
            if po:
                request['PONumber'] = po
        if self.rrts_schedule_pickup:
            request.update({
                'QuickPickup': True,
                'FreightReady': self._rrts_time(shipment.pickup_ready_time),
                'FreightClosed': self._rrts_time(shipment.pickup_close_time),
            })
        if self.rrts_label_style:
            request.update({
                'PrintLabel': True,
                'LabelStyle': self.rrts_label_style,
                'StartingPosition': 1,
                'NumberOfLabels': min(max(shipment.total_units, 1), 10),
            })
        return request

    def _rrts_rate_envelope(self, shipment, account=None):
        """SOAP envelope for RateQuoteByAccountV2. Elements follow the service schema order
        (QuoteRequest fields, then Account)."""
        username, password = self._rrts_credentials()
        units = self._rrts_check_units(shipment)
        weights = OrderedDict()
        for unit in units:
            weights[unit.freight_class] = weights.get(unit.freight_class, 0) + unit.weight
        if len(weights) > MAX_RATE_CLASSES:
            raise UserError(_('Roadrunner rates at most %s different classes per shipment.', MAX_RATE_CLASSES))
        pallets = sum(units.filtered(lambda u: u.unit_type == 'pallet').mapped('quantity'))
        cube = sum(units.mapped('cube'))

        nsmap = {'soap': SOAP_NS, 'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=nsmap)
        header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
        auth = etree.SubElement(header, '{%s}AuthenticationHeader' % RATE_NS, nsmap={None: RATE_NS})
        etree.SubElement(auth, '{%s}UserName' % RATE_NS).text = username
        etree.SubElement(auth, '{%s}Password' % RATE_NS).text = password
        body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
        operation = etree.SubElement(body, '{%s}%s' % (RATE_NS, RATE_OPERATION), nsmap={None: RATE_NS})
        request = etree.SubElement(operation, '{%s}request' % RATE_NS)

        def add(parent, name, value=None):
            node = etree.SubElement(parent, '{%s}%s' % (RATE_NS, name))
            if value is not None:
                node.text = str(value)
            return node

        add(request, 'OriginZip', self._rrts_zip(shipment.shipper_id))
        add(request, 'DestinationZip', self._rrts_zip(shipment.partner_id))
        details = add(request, 'ShipmentDetails')
        for freight_class, weight in weights.items():
            detail = add(details, 'ShipmentDetail')
            add(detail, 'ActualClass', freight_class)
            add(detail, 'Weight', int(round(weight)))
        add(request, 'OriginType', 'O')
        add(request, 'PaymentType', 'P')
        add(request, 'PalletCount', pallets)
        add(request, 'CubicFeet', int(math.ceil(cube)))
        add(request, 'Pieces', max(shipment.total_units, 1))
        codes = self._rrts_accessorial_codes(shipment)
        if codes:
            options = add(request, 'ServiceDeliveryOptions')
            for code in codes:
                add(add(options, 'ServiceOptions'), 'ServiceCode', code)
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        add(request, 'ShipDate', '%sT00:00:00' % fields.Date.to_string(ship_date))
        add(request, 'Account', account or self._rrts_account())
        return etree.tostring(envelope, xml_declaration=True, encoding='utf-8')

    # ------------------------------------------------------------------ responses

    @api.model
    def _rrts_xml_text(self, node, name, default=''):
        found = node.xpath('./*[local-name()=$name]', name=name)
        return (found[0].text or '').strip() if found else default

    @api.model
    def _rrts_float(self, value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _rrts_soap_rate(self, envelope):
        response = self._rrts_request('POST', RATE_URL, data=envelope, headers={
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': '"%s%s"' % (RATE_NS, RATE_OPERATION),
        })
        try:
            root = etree.fromstring(response.content)
        except (etree.XMLSyntaxError, ValueError):
            raise UserError(_('Roadrunner rate quote answered %(status)s: %(text)s',
                              status=response.status_code, text=(response.text or '')[:300]))
        fault = root.xpath('//*[local-name()="Fault"]')
        if fault:
            message = self._rrts_xml_text(fault[0], 'faultstring') or _('unknown error')
            raise UserError(_('Roadrunner: %s', message))
        result = root.xpath('//*[local-name()="%sResult"]' % RATE_OPERATION)
        if not result:
            raise UserError(_('Roadrunner rate quote answered %(status)s without a quote.',
                              status=response.status_code))
        return result[0]

    def _rrts_rate_from_result(self, result):
        net = self._rrts_float(self._rrts_xml_text(result, 'NetCharge'), -1)
        lines = result.xpath('./*[local-name()="RateDetails"]/*[local-name()="QuoteDetail"]')
        if net < 0:
            reasons = [self._rrts_xml_text(line, 'ExtraMessages') for line in lines]
            raise UserError(_('Roadrunner cannot rate this shipment online: %s',
                              '; '.join(r for r in reasons if r) or _('call Roadrunner for a quote')))
        charges = []
        for line in lines:
            amount = self._rrts_float(self._rrts_xml_text(line, 'Charge'))
            if amount == -1 or not amount:
                continue
            code = self._rrts_xml_text(line, 'Code')
            description = self._rrts_xml_text(line, 'Description')
            if not code:
                actual = self._rrts_xml_text(line, 'ActualClass')
                rated = self._rrts_xml_text(line, 'RatedClass')
                weight = self._rrts_xml_text(line, 'Weight')
                name = _('Linehaul before discount, class %(cls)s, %(weight)s lb',
                         cls=rated or actual, weight=weight)
                if rated and actual and rated != actual:
                    name += _(' (class %s rated as %s)', actual, rated)
                code = 'LINEHAUL'
            else:
                name = CHARGE_NAMES.get(code) or description or code
            if code in NEGATIVE_CHARGES:
                amount = -abs(amount)
            charges.append({'code': code, 'name': name, 'amount': amount})
        if charges:
            difference = round(net - sum(c['amount'] for c in charges), 2)
            if abs(difference) >= 0.01:
                charges.append({'code': 'OTHER', 'name': _('Other (difference to Roadrunner total)'),
                                'amount': difference})
        routing = result.xpath('./*[local-name()="RoutingInfo"]')
        transit = 0
        if routing:
            transit = int(self._rrts_float(self._rrts_xml_text(routing[0], 'EstimatedTransitDays')))
        return {
            'service': _('Roadrunner Standard'),
            'total': net,
            'transit_days': transit,
            'quote_number': self._rrts_xml_text(result, 'QuoteNumber') or False,
            'charges': charges,
        }

    # ------------------------------------------------------------------ selamta_ltl hooks

    def roadrunner_ltl_rate(self, shipment):
        self.ensure_one()
        result = self._rrts_soap_rate(self._rrts_rate_envelope(shipment))
        return [self._rrts_rate_from_result(result)]

    def roadrunner_ltl_book(self, shipment, rate):
        self.ensure_one()
        request = self._rrts_bol_request(shipment)
        username, password = self._rrts_credentials()
        url = BOL_URLS['production' if self.rrts_environment == 'production' else 'test']
        response = self._rrts_request('POST', url, json=request, auth=(username, password),
                                      headers={'Content-Type': 'application/json'})
        data = self._rrts_json(response)
        if response.status_code == 401:
            raise UserError(_('Roadrunner refused the sign-in. Check the freight.rrts.com username '
                              'and password on the %s shipping method.', self.name))
        if response.status_code >= 400 or data.get('HasError') or not data:
            message = data.get('ErrorMessage') or data.get('Message') or (response.text or '')[:300]
            raise UserError(_('Roadrunner did not create the BOL (%(status)s): %(message)s',
                              status=response.status_code, message=message or _('no details')))
        pro = (str(data.get('PRONumber') or data.get('ProNumber') or '')).strip()
        bol = (str(data.get('BOLNumber') or '')).strip()
        documents = []
        pdf = data.get('Base64PDFData') or data.get('Base64PDFDate')
        if pdf:
            documents.append(('Roadrunner BOL (carrier copy) %s.pdf' % (pro or bol or shipment.name),
                              base64.b64decode(pdf)))
        notes = []
        if data.get('QuoteNumber'):
            notes.append(_('Roadrunner quote on the booked BOL: %s', data['QuoteNumber']))
        quote = data.get('QuoteResponse') or {}
        booked_total = quote.get('netChargeField', quote.get('NetCharge')) if isinstance(quote, dict) else None
        booked_total = self._rrts_float(booked_total, None)
        if booked_total is not None and booked_total >= 0 and shipment.quoted_amount \
                and abs(booked_total - shipment.quoted_amount) > 0.5:
            notes.append(_('Roadrunner priced the booked BOL at %(total)s, the quote was %(quote)s.',
                           total=booked_total, quote=shipment.quoted_amount))
        if not pro:
            notes.append(_('Roadrunner did not send the PRO back. It is filled in from tracking once '
                           'Roadrunner has it (by pickup number), or type it from the BOL.'))
        terminal = ' '.join(filter(None, [data.get('TerminalName'),
                                          data.get('TerminalPhone') and '(%s)' % data['TerminalPhone']]))
        if terminal:
            shipment.rrts_terminal = terminal
        if self.rrts_environment != 'production':
            notes.append(_('Booked in the Roadrunner TEST system: nothing will be picked up.'))
        if notes:
            shipment.message_post(body=Markup('<br/>').join(notes))
        result = {
            'pro_number': pro or False,
            'pickup_number': (str(data.get('PickUpNumber') or '')).strip() or False,
            'documents': documents,
        }
        if bol and bol != shipment.bol_reference:
            result['bol_number'] = bol
        return result

    def roadrunner_ltl_track(self, shipments):
        self.ensure_one()
        searches = OrderedDict()
        for shipment in shipments:
            key = digits_only(shipment.pro_number) or (shipment.pickup_number or '').strip()
            if key:
                searches[key] = shipment
        results = {}
        keys = list(searches)
        for start in range(0, len(keys), TRACK_BATCH):
            url = TRACK_URL + ','.join(quote_plus(k) for k in keys[start:start + TRACK_BATCH])
            response = self._rrts_request('GET', url, headers={'Accept': 'application/json'})
            data = self._rrts_json(response)
            if response.status_code >= 400:
                raise UserError(_('Roadrunner tracking answered %(status)s: %(text)s',
                                  status=response.status_code, text=(response.text or '')[:300]))
            for found in data.get('SearchResults') or []:
                item = str(found.get('SearchItem') or '').strip()
                shipment = searches.get(item) or searches.get(digits_only(item))
                details = found.get('Shipment') or {}
                if shipment and details:
                    results[shipment.id] = self._rrts_tracking_info(shipment, details)
        return results

    @api.model
    def _rrts_valid_date(self, value):
        """'2026-11-03T13:57:00' -> '2026-11-03'; .NET empty dates (0001-01-01) -> False."""
        value = (value or '')[:10]
        try:
            return value if date.fromisoformat(value).year > 1900 else False
        except ValueError:
            return False

    @api.model
    def _rrts_tracking_info(self, shipment, details):
        info = {}
        pro = str(details.get('ProNumber') or '').strip()
        if pro and not shipment.pro_number:
            info['pro_number'] = pro
        comments = details.get('Comments') or []
        codes = {c.get('ActivityCode') for c in comments if c.get('ActivityCode')}
        delivered = self._rrts_valid_date(details.get('DeliveredDateTime'))
        if delivered or 'DEL' in codes:
            info['state'] = 'delivered'
            if delivered:
                info['delivered_date'] = delivered
        elif details.get('PickedUp') or codes & MOVING_CODES:
            info['state'] = 'in_transit'
        latest = max(comments, key=lambda c: c.get('StatusDateTime') or '', default=None)
        status = (latest or {}).get('StatusComment') or details.get('OperationalStatus') or ''
        if details.get('Location') and info.get('state') != 'delivered':
            status = '%s (%s)' % (status, details['Location']) if status else details['Location']
        if status:
            info['status'] = status.strip()
        return info

    def roadrunner_ltl_documents(self, shipment):
        self.ensure_one()
        pro = digits_only(shipment.pro_number)
        if not pro:
            raise UserError(_('%s has no PRO yet.', shipment.name))
        existing = set(self.env['ir.attachment'].search([
            ('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name'))
        documents = self._rrts_images(pro, [POD_TYPE], existing)
        if self._rrts_can_sign():
            try:
                documents += self._rrts_images(pro, SIGNED_IMAGE_TYPES, existing, signed=True)
            except UserError as error:
                _logger.warning('Roadrunner signed images failed for %s: %s', shipment.name, error)
                shipment.message_post(body=_(
                    'Roadrunner did not send the BOL, weight & inspection and invoice images: %s. '
                    'Check the tracking application ID and API key.', error.args[0]))
        return documents

    def _rrts_images(self, pro, image_types, existing, signed=False):
        payload = [{'ImageType': kind, 'ProNumber': int(pro)} for kind in image_types]
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if signed:
            headers['Authorization'] = self._rrts_amx_header('POST', IMAGES_URL)
        response = self._rrts_request('POST', IMAGES_URL, json=payload, headers=headers)
        if response.status_code >= 400:
            raise UserError(_('Roadrunner images answered %(status)s: %(text)s',
                              status=response.status_code, text=(response.text or '')[:200]))
        data = self._rrts_json(response)
        documents = []
        for entry in (data if isinstance(data, list) else [data]):
            if not isinstance(entry, dict) or entry.get('HasError'):
                continue
            for image in entry.get('Images') or []:
                if not image.get('Base64Image'):
                    continue
                filename = image.get('FileName') or '%s_%s.jpg' % (image_types[0], pro)
                kind = filename.split('_')[0].upper()
                name = '%s %s' % (DOCUMENT_NAMES.get(kind, 'Roadrunner'), filename)
                if name in existing:
                    continue
                existing.add(name)
                documents.append((name, base64.b64decode(image['Base64Image'])))
        return documents

    # ------------------------------------------------------------------ Odoo delivery hooks

    def roadrunner_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('Roadrunner rates come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def roadrunner_send_shipping(self, pickings):
        # Booking happens on the LTL shipment; validating the delivery books nothing.
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def roadrunner_get_tracking_link(self, picking):
        # Roadrunner's public tracking page; the PRO is typed there.
        return PUBLIC_TRACKING_URL if picking.carrier_tracking_ref else False

    def roadrunner_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the pickup with Roadrunner, then cancel the LTL shipment in Odoo.'))

    def action_rrts_test_connection(self):
        """Sign in to Roadrunner rating with a sample quote from our dock to itself
        (500 lb, class 70). Books nothing."""
        self.ensure_one()
        shipper = self.env.company.partner_id
        shipment = self.env['selamta.ltl.shipment'].new({
            'shipper_id': shipper.id, 'partner_id': shipper.id, 'carrier_id': self.id,
            'ship_date': fields.Date.context_today(self),
            'unit_ids': [(0, 0, {'unit_type': 'pallet', 'quantity': 1, 'length': 48, 'width': 40,
                                 'height': 48, 'weight': 500, 'class_override': '70'})],
        })
        rate = self._rrts_rate_from_result(self._rrts_soap_rate(self._rrts_rate_envelope(shipment)))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _(
                'Signed in to Roadrunner as account %(account)s. Sample quote %(quote)s: %(total).2f.',
                account=self._rrts_account(), quote=rate['quote_number'] or '-', total=rate['total'])},
        }
