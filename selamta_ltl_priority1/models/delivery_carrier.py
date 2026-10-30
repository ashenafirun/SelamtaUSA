# -*- coding: utf-8 -*-
"""Priority1 v2 API (api.priority1.com, OpenAPI at /openapi/v2.json).

* Auth: header X-API-KEY with the key Priority1 issues per customer.
* POST /v2/ltl/quotes/rates -> rateQuotes[] (one per carrier): id (the quote to dispatch),
  carrierName, carrierCode, transitDays, deliveryDate, expirationDate,
  rateQuoteDetail {total, charges[{code, description, amount}]}.
* POST /v2/ltl/shipments/dispatch {quoteId, originLocation, destinationLocation, lineItems,
  pickupWindow {date MM/DD/YYYY, startTime HH:mm, endTime}, deliveryWindow,
  shipmentIdentifiers, pickupNote, deliveryNote} -> id, shipmentIdentifiers
  (BILL_OF_LADING, PICKUP...), capacityProviderBolUrl, estimatedDeliveryDate, infoMessages.
  A dispatch books a real pickup.
* POST /v2/ltl/shipments/status {identifierType, identifierValue} -> shipments[] with
  status, actualPickupDate, actualDeliveryDate, shipmentIdentifiers, trackingStatuses[].
* POST /v2/ltl/shipments/images {shipmentImageTypeId, imageFormatTypeId, proNumber,
  bolNumber} -> imageUrl.
"""
import logging
from datetime import timedelta

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

API_HOST = 'https://api.priority1.com'
TIMEOUT = 60
# Our accessorial codes -> Priority1 accessorial service codes (api.priority1.com/about,
# Reference Data).
ACCESSORIALS = {
    'LIFTGATE_DEL': 'LGDEL',
    'RESIDENTIAL_DEL': 'RESDEL',
    'LIMITED_ACCESS_DEL': 'LTDDEL',
    'INSIDE_DEL': 'INDEL',
    'APPOINTMENT_DEL': 'APPT',
    'NOTIFY_DEL': 'NOTIFY',
    'LIFTGATE_PU': 'LGPU',
}
PACKAGING = {'pallet': 'Pallet', 'box': 'Box'}
IMAGE_TYPES = [('DeliveryReceipt', 'Delivery receipt'), ('BillOfLading', 'Carrier BOL')]


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('priority1', 'Priority1')],
        ondelete={'priority1': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    p1_api_key = fields.Char(
        'Priority1 API key', groups='base.group_system', copy=False,
        help='The API key Priority1 issued for our account (sent as X-API-KEY).')
    p1_book_shipments = fields.Boolean(
        'Dispatch through the API',
        help='With this on, choosing a Priority1 quote in the rate shop dispatches it: a real '
             'pickup. With it off, the quote is saved and the load is booked on Priority1\'s '
             'website.')
    p1_max_quotes = fields.Integer(
        'Priority1 quotes to show', default=8,
        help='The cheapest quotes Priority1 returns are shown in the rate shop, up to this many.')
    p1_contact_name = fields.Char('Priority1 shipping contact')
    p1_contact_phone = fields.Char('Priority1 shipping contact phone')
    p1_contact_email = fields.Char('Priority1 shipping contact email')

    # ------------------------------------------------------------------ connection

    def ltl_can(self, operation):
        self.ensure_one()
        if self.delivery_type == 'priority1' and operation == 'book' and not self.p1_book_shipments:
            return False
        return super().ltl_can(operation)

    def _p1_key(self):
        self.ensure_one()
        key = (self.sudo().p1_api_key or '').strip()
        if not key:
            raise UserError(_('Enter the Priority1 API key on the %s shipping method (Priority1 tab) first.',
                              self.name))
        return key

    @api.model
    def _p1_json(self, response):
        try:
            return response.json() if response.content else {}
        except ValueError:
            return {}

    @api.model
    def _p1_error(self, data, response=None):
        messages = []
        if isinstance(data, dict):
            for key in ('message', 'title', 'detail', 'error'):
                if isinstance(data.get(key), str) and data[key]:
                    messages.append(data[key])
            errors = data.get('errors')
            if isinstance(errors, dict):
                for field_name, texts in errors.items():
                    texts = texts if isinstance(texts, list) else [texts]
                    messages.append('%s: %s' % (field_name, ' '.join(str(t) for t in texts)))
            elif isinstance(errors, list):
                messages.extend(str(e.get('message') if isinstance(e, dict) else e) for e in errors)
            for message in data.get('messages') or data.get('infoMessages') or []:
                if isinstance(message, dict) and message.get('text') and \
                        str(message.get('severity') or '').lower() in ('error', 'critical'):
                    messages.append(message['text'])
        elif isinstance(data, list):
            messages.extend(str(m) for m in data[:5])
        if not messages and response is not None:
            messages.append((response.text or '')[:300])
        return '; '.join(m for m in messages if m) or _('no details')

    def _p1_call(self, path, payload):
        self.ensure_one()
        headers = {'X-API-KEY': self._p1_key(), 'Content-Type': 'application/json', 'Accept': 'application/json'}
        _logger.info('Priority1 POST %s', path)
        try:
            response = requests.request('POST', API_HOST + path, json=payload, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise UserError(_('Could not reach Priority1: %s', error)) from error
        data = self._p1_json(response)
        if response.status_code in (401, 403):
            raise UserError(_('Priority1 refused the API key (%(status)s). Check the key on the %(name)s '
                              'shipping method.', status=response.status_code, name=self.name))
        if response.status_code >= 400:
            raise UserError(_('Priority1 answered %(status)s: %(message)s',
                              status=response.status_code, message=self._p1_error(data, response)))
        return data

    @api.model
    def _p1_download(self, url):
        """Documents come back as links (BOL, delivery receipt). Returns the file bytes or None."""
        if not url:
            return None
        try:
            response = requests.request('GET', url, timeout=TIMEOUT)
        except requests.RequestException as error:
            _logger.warning('Priority1 document %s not fetched: %s', url, error)
            return None
        return response.content if response.status_code == 200 and response.content else None

    # ------------------------------------------------------------------ request parts

    @api.model
    def _p1_zip(self, partner):
        country = partner.country_id.code or 'US'
        if country == 'CA':
            return ''.join(ch for ch in (partner.zip or '') if ch.isalnum()).upper()
        postal = digits_only(partner.zip)[:5]
        if len(postal) != 5:
            raise UserError(_('%s needs a 5-digit ZIP code for Priority1.', partner.display_name))
        return postal

    @api.model
    def _p1_phone(self, value, label):
        phone = digits_only(value)
        if len(phone) == 11 and phone.startswith('1'):
            phone = phone[1:]
        if len(phone) < 10:
            raise UserError(_('Priority1 needs a 10-digit phone number for the %s.', label))
        return phone[:10]

    @api.model
    def _p1_company_name(self, partner):
        return (partner.commercial_partner_id.name if partner.parent_id else partner.name) or ''

    @api.model
    def _p1_units(self, shipment):
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the pallets or boxes to %s first.', shipment.name))
        for unit in units:
            if not unit.freight_class or not unit.weight:
                raise UserError(_('Measure and weigh every pallet or box on %s first.', shipment.name))
        return units

    @api.model
    def _p1_items(self, shipment):
        items = []
        for unit in self._p1_units(shipment):
            text = unit.description or _('Freight')
            if shipment.consolidated and unit.for_text:
                text = '%s - for %s' % (text, unit.for_text)
            item = {
                'freightClass': unit.freight_class,
                'packagingType': PACKAGING.get(unit.unit_type, 'Pallet'),
                'units': unit.quantity,
                'pieces': unit.quantity,
                'totalWeight': round(unit.weight),
                'length': round(unit.length or 0),
                'width': round(unit.width or 0),
                'height': round(unit.height or 0),
                'description': text[:100],
                'isStackable': False,
                'isHazardous': False,
                'isUsed': False,
            }
            if unit.nmfc_item:
                item['nmfcItemCode'] = unit.nmfc_item
                if unit.nmfc_sub:
                    item['nmfcSubCode'] = unit.nmfc_sub
            items.append(item)
        return items

    @api.model
    def _p1_accessorials(self, shipment):
        codes = []
        for service in shipment.accessorial_ids:
            code = ACCESSORIALS.get(service.code)
            if code and {'code': code} not in codes:
                codes.append({'code': code})
        return codes

    def _p1_rate_request(self, shipment):
        shipper, consignee = shipment.shipper_id, shipment.partner_id
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        return {
            'originCity': shipper.city or '',
            'originStateAbbreviation': shipper.state_id.code or '',
            'originZipCode': self._p1_zip(shipper),
            'originCountryCode': shipper.country_id.code or 'US',
            'destinationCity': consignee.city or '',
            'destinationStateAbbreviation': consignee.state_id.code or '',
            'destinationZipCode': self._p1_zip(consignee),
            'destinationCountryCode': consignee.country_id.code or 'US',
            'pickupDate': '%sT00:00:00' % fields.Date.to_string(ship_date),
            'items': self._p1_items(shipment),
            'accessorialServices': self._p1_accessorials(shipment),
        }

    @api.model
    def _p1_time(self, hours):
        """10.5 -> '10:30'."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        return '%02d:%02d' % (min(hour, 23), minute)

    def _p1_location(self, partner, label, contact_name=None, phone=None, email=None):
        if not partner.street or not partner.city or not partner.state_id:
            raise UserError(_('%(name)s needs a street, city and state for a Priority1 dispatch (%(label)s).',
                              name=partner.display_name, label=label))
        contact = {
            'companyName': self._p1_company_name(partner)[:60],
            'contactName': (contact_name or (partner.name if partner.parent_id else False) or _('Receiving'))[:60],
            'phoneNumber': self._p1_phone(phone or partner.phone or partner.mobile
                                          or partner.commercial_partner_id.phone,
                                          '%s (%s)' % (label, partner.display_name)),
        }
        if email or partner.email:
            contact['email'] = (email or partner.email)[:100]
        return {
            'address': {
                'addressLine1': partner.street[:60],
                'addressLine2': (partner.street2 or '')[:60],
                'city': partner.city[:40],
                'state': partner.state_id.code,
                'postalCode': self._p1_zip(partner),
                'country': partner.country_id.code or 'US',
            },
            'contact': contact,
        }

    def _p1_dispatch_request(self, shipment, rate):
        quote_id = rate.get('p1_quote_id')
        if not quote_id:
            raise UserError(_('This Priority1 rate has no quote ID; get rates again.'))
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        # Priority1's quoted delivery date can be counted from the day of the quote, not the
        # pickup date; never ask for delivery before pickup plus the transit days.
        earliest = self._p1_add_business_days(ship_date, max(rate.get('transit_days') or 1, 1))
        quoted = fields.Date.to_date((rate.get('p1_delivery_date') or '')[:10] or False)
        delivery_date = max(quoted, earliest) if quoted else earliest
        company = shipment.company_id
        request = {
            'quoteId': int(quote_id) if str(quote_id).isdigit() else quote_id,
            'originLocation': self._p1_location(
                shipment.shipper_id, _('shipper'),
                contact_name=self.p1_contact_name or self.env.user.name,
                phone=self.p1_contact_phone or shipment.shipper_id.phone or company.phone,
                email=self.p1_contact_email or shipment.shipper_id.email or company.email),
            'destinationLocation': self._p1_location(shipment.partner_id, _('consignee')),
            'lineItems': self._p1_items(shipment),
            'pickupWindow': {
                'date': ship_date.strftime('%m/%d/%Y'),
                'startTime': self._p1_time(shipment.pickup_ready_time),
                'endTime': self._p1_time(shipment.pickup_close_time),
            },
            'deliveryWindow': {
                'date': delivery_date.strftime('%m/%d/%Y'),
                'startTime': '08:00',
                'endTime': '17:00',
            },
            'shipmentIdentifiers': self._p1_identifiers(shipment),
        }
        delivery_lines = shipment._bol_delivery_lines()
        if delivery_lines:
            request['deliveryNote'] = ', '.join(delivery_lines)[:250]
        pickup_lines = []
        if shipment.pickup_instructions:
            pickup_lines.append(' '.join(shipment.pickup_instructions.split()))
        pickup_lines += [s.name.upper() for s in shipment.accessorial_ids if s.code.endswith('_PU')]
        if pickup_lines:
            request['pickupNote'] = ', '.join(pickup_lines)[:250]
        return request

    @api.model
    def _p1_add_business_days(self, start, days):
        current = start
        while days > 0:
            current += timedelta(days=1)
            if current.weekday() < 5:
                days -= 1
        return current

    @api.model
    def _p1_identifiers(self, shipment):
        identifiers, seen = [], set()

        def add(kind, value, primary=False):
            value = (value or '').strip()
            if value and (kind, value) not in seen:
                seen.add((kind, value))
                identifiers.append({'type': kind, 'value': value[:50], 'primaryForType': primary})

        add('CUSTOMER_REFERENCE', shipment.name, primary=True)
        for picking in shipment.picking_ids:
            sale = picking.sale_id if 'sale_id' in picking._fields else False
            add('PURCHASE_ORDER', sale.client_order_ref if sale else False,
                primary=not any(i['type'] == 'PURCHASE_ORDER' for i in identifiers))
            add('CUSTOMER_REFERENCE', picking.origin)
        return identifiers

    # ------------------------------------------------------------------ responses

    @api.model
    def _p1_number(self, value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @api.model
    def _p1_charges(self, detail, total):
        charges = []
        for line in detail.get('charges') or []:
            amount = self._p1_number(line.get('amount'))
            if amount:
                charges.append({'code': line.get('code') or 'CHG',
                                'name': line.get('description') or line.get('code') or _('Charge'),
                                'amount': amount})
        if charges:
            difference = round(total - sum(c['amount'] for c in charges), 2)
            if abs(difference) >= 0.01:
                charges.append({'code': 'OTHER', 'name': _('Other (difference to Priority1 total)'),
                                'amount': difference})
        return charges

    @api.model
    def _p1_identifier(self, identifiers, kind):
        for identifier in identifiers or []:
            if str(identifier.get('type') or '').upper() == kind and identifier.get('value'):
                return str(identifier['value']).strip()
        return False

    # ------------------------------------------------------------------ selamta_ltl hooks

    def priority1_ltl_rate(self, shipment):
        self.ensure_one()
        data = self._p1_call('/v2/ltl/quotes/rates', self._p1_rate_request(shipment))
        rates = []
        for quote in data.get('rateQuotes') or []:
            detail = quote.get('rateQuoteDetail') or {}
            total = self._p1_number(detail.get('total'), None)
            if total is None or total <= 0 or not quote.get('id'):
                continue
            carrier = (quote.get('carrierName') or _('Unknown carrier')).strip()
            service = _('%(carrier)s via Priority1', carrier=carrier)
            level = quote.get('serviceLevelDescription') or quote.get('serviceLevel')
            if level and 'standard' not in str(level).lower() and str(level).lower() != 'normal':
                service = '%s - %s' % (service, level)
            rates.append({
                'service': service,
                'total': total,
                'transit_days': int(self._p1_number(quote.get('transitDays'))),
                'quote_number': str(quote.get('carrierQuoteNumber') or quote['id']),
                'expires': (quote.get('expirationDate') or '')[:10] or False,
                'charges': self._p1_charges(detail, total),
                'p1_quote_id': quote['id'],
                'p1_carrier_name': carrier,
                'p1_carrier_scac': quote.get('carrierCode') or False,
                'p1_delivery_date': quote.get('deliveryDate') or False,
            })
        if not rates:
            reasons = [q.get('message') for q in data.get('invalidRateQuotes') or [] if q.get('message')]
            raise UserError(_('Priority1 returned no quote: %s',
                              '; '.join(reasons[:3]) or self._p1_error(data)))
        rates.sort(key=lambda r: r['total'])
        return rates[:max(self.p1_max_quotes, 1)]

    def priority1_ltl_book(self, shipment, rate):
        self.ensure_one()
        if not self.p1_book_shipments:
            raise UserError(_('Dispatching through the Priority1 API is off on %s; book the load on '
                              'Priority1\'s website and type the PRO.', self.name))
        data = self._p1_call('/v2/ltl/shipments/dispatch', self._p1_dispatch_request(shipment, rate))
        identifiers = data.get('shipmentIdentifiers') or []
        bol = self._p1_identifier(identifiers, 'BILL_OF_LADING')
        pickup = self._p1_identifier(identifiers, 'PICKUP')
        pro = self._p1_identifier(identifiers, 'PRO')
        if not data.get('id') and not bol:
            raise UserError(_('Priority1 did not dispatch the load: %s', self._p1_error(data)))
        shipment.write({
            'p1_carrier_name': rate.get('p1_carrier_name') or False,
            'p1_carrier_scac': rate.get('p1_carrier_scac') or False,
            'p1_shipment_id': str(data.get('id') or '') or False,
        })
        notes = [_('Dispatched through Priority1 with %(carrier)s. Priority1 BOL %(bol)s.',
                   carrier=rate.get('p1_carrier_name') or '-', bol=bol or '-')]
        if data.get('estimatedDeliveryDate'):
            notes.append(_('Estimated delivery: %s', str(data['estimatedDeliveryDate'])[:10]))
        cost = self._p1_number(data.get('totalCost'), None)
        if cost and shipment.quoted_amount and abs(cost - shipment.quoted_amount) > 0.5:
            notes.append(_('Priority1 priced the dispatch at %(cost)s, the quote was %(quote)s.',
                           cost=cost, quote=shipment.quoted_amount))
        for message in data.get('infoMessages') or []:
            if isinstance(message, dict) and message.get('text'):
                notes.append(_('Priority1: %s', message['text']))
        if not pro:
            notes.append(_('The carrier assigns the PRO at pickup; tracking fills it in.'))
        shipment.message_post(body=Markup('<br/>').join(notes))
        documents = []
        pdf = self._p1_download(data.get('capacityProviderBolUrl'))
        if pdf and pdf[:4] == b'%PDF':
            documents.append(('%s BOL (carrier copy) %s.pdf' % (rate.get('p1_carrier_name') or 'Carrier', bol or shipment.name), pdf))
        return {
            'bol_number': bol or False,
            'pickup_number': pickup or False,
            'pro_number': pro or False,
            'documents': documents,
        }

    def priority1_ltl_track(self, shipments):
        self.ensure_one()
        results = {}
        for shipment in shipments:
            if shipment.bol_number:
                request = {'identifierType': 'BILL_OF_LADING', 'identifierValue': shipment.bol_number}
            elif shipment.pro_number:
                request = {'identifierType': 'PRO', 'identifierValue': shipment.pro_number}
            else:
                continue
            try:
                data = self._p1_call('/v2/ltl/shipments/status', request)
            except UserError as error:
                _logger.warning('Priority1 tracking failed for %s: %s', shipment.name, error)
                continue
            found = (data.get('shipments') or [None])[0]
            if found:
                results[shipment.id] = self._p1_tracking_info(shipment, found)
        return results

    @api.model
    def _p1_tracking_info(self, shipment, found):
        info = {}
        pro = self._p1_identifier(found.get('shipmentIdentifiers'), 'PRO')
        if pro and not shipment.pro_number:
            info['pro_number'] = pro
        status = str(found.get('status') or '').strip()
        delivered = (found.get('actualDeliveryDate') or '')[:10]
        if status.lower() == 'delivered' or delivered:
            info['state'] = 'delivered'
            if delivered:
                info['delivered_date'] = delivered
        elif found.get('actualPickupDate') or status.lower() in ('in transit', 'picked up', 'out for delivery'):
            info['state'] = 'in_transit'
        events = found.get('trackingStatuses') or []
        latest = max(events, key=lambda e: e.get('timeStamp') or '', default=None)
        text = status
        if latest:
            place = ', '.join(filter(None, [latest.get('city'), latest.get('state')]))
            text = ' - '.join(filter(None, [latest.get('status') or status, latest.get('statusReason'), place]))
        if text:
            info['status'] = text
        return info

    def priority1_ltl_documents(self, shipment):
        self.ensure_one()
        if not shipment.pro_number and not shipment.bol_number:
            raise UserError(_('%s has no PRO or BOL number yet.', shipment.name))
        existing = set(self.env['ir.attachment'].search([
            ('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name'))
        reference = shipment.pro_number or shipment.bol_number
        documents = []
        for image_type, label in IMAGE_TYPES:
            name = '%s %s.pdf' % (label, reference)
            if name in existing:
                continue
            try:
                data = self._p1_call('/v2/ltl/shipments/images', {
                    'shipmentImageTypeId': image_type, 'imageFormatTypeId': 'PDF',
                    'proNumber': shipment.pro_number or '', 'bolNumber': shipment.bol_number or ''})
            except UserError as error:
                _logger.info('Priority1 %s for %s not available: %s', image_type, shipment.name, error)
                continue
            content = self._p1_download(data.get('imageUrl'))
            if content:
                documents.append((name, content))
        return documents

    def priority1_ltl_cancel(self, shipment):
        self.ensure_one()
        if not shipment.p1_shipment_id or not str(shipment.p1_shipment_id).isdigit():
            raise UserError(_('%s has no Priority1 shipment ID; cancel it with Priority1 by phone, then '
                              'cancel it here.', shipment.name))
        self._p1_call('/v2/ltl/shipments/cancel', {'id': int(shipment.p1_shipment_id)})
        return True

    # ------------------------------------------------------------------ Odoo delivery hooks

    def priority1_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('Priority1 quotes come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def priority1_send_shipping(self, pickings):
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def priority1_get_tracking_link(self, picking):
        return False

    def priority1_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the load with Priority1, then cancel the LTL shipment in Odoo.'))

    def action_p1_test_connection(self):
        """Ask Priority1 for sample quotes from our dock to itself (500 lb, class 70). Books nothing."""
        self.ensure_one()
        shipper = self.env.company.partner_id
        shipment = self.env['selamta.ltl.shipment'].new({
            'shipper_id': shipper.id, 'partner_id': shipper.id, 'carrier_id': self.id,
            'ship_date': fields.Date.context_today(self),
            'unit_ids': [(0, 0, {'unit_type': 'pallet', 'quantity': 1, 'length': 48, 'width': 40,
                                 'height': 48, 'weight': 500, 'class_override': '70'})],
        })
        rates = self.priority1_ltl_rate(shipment)
        best = rates[0]
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _(
                'Priority1 key works: %(count)s quotes, cheapest %(service)s %(total).2f.',
                count=len(rates), service=best['service'], total=best['total'])},
        }
