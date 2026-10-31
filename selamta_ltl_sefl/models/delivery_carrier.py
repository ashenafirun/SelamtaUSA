# -*- coding: utf-8 -*-
"""Southeastern Freight Lines Web Connect (sefl.com/seflWebsite/webconnect.jsp, read 30 Oct 2026).

* Rate quote (MySEFL login as HTTP Basic auth): POST form data to
  https://www.sefl.com/webconnect/ratequotes/rest/submitQuote (CustomerAccount, CustomerName,
  CustomerStreet/City/State/Zip, Option S, Terms P, PickupDateMM/DD/YYYY, Origin*/Destination*,
  OrigCountry/DestCountry U, Class1..20, Weight1..20, Pieces1..20, optional DimsOption=I with
  PieceLength/Width/Height/UnitOfMeasure/NumberOfUnits 1..20, accessorial flags chkLGD etc. =
  "on", returnX=Y, rateXML=Y) -> {quoteNumber, errorOccured, errorMessage}. Then GET
  .../rest/{quoteNumber}?ReturnDetail=Y -> status RAT (rated) / ENT (queued, ask again) / UTR
  (rated by hand), rateQuote, transitTime, discountPercent, details [{typeCharge (P commodity,
  GFC gross, Dnnnn discount, NFC net, FS fuel, TTL total, others accessorials), description,
  weight, ratingClass, charges}]. Values are text padded with spaces.
* Tracing: GET https://www.sefl.com/webconnect/tracing?Type=PN&RefNum1..10=&output=JSON ->
  {pro: [{proNumber, pickupDate, currentStatusCode (DLV delivered, VOD void, ...),
  currentStatusDescription, currentStatusDateOnly, location, status, error}]}. Without the
  MySEFL login SEFL sends a condensed answer; it has what tracking needs, and the password
  stays out of the address.
* Documents: POST https://www.sefl.com/document-retrieval/ {pros, imageTypes [DR, WI, FB],
  format: pdf} with Basic auth -> [{pro, type, fileExt, base64Image, error}].
PROs are 7 or 9 digits without the terminal code, dash or leading zeros.
"""
import base64
import logging
import re
import time
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.pdf import merge_pdf

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

RATE_URL = 'https://www.sefl.com/webconnect/ratequotes/rest/'
TRACE_URL = 'https://www.sefl.com/webconnect/tracing'
DOCS_URL = 'https://www.sefl.com/document-retrieval/'
PUBLIC_TRACKING_URL = 'https://www.sefl.com/Tracing/index.jsp?Type=PN&RefNum1=%s'
TIMEOUT = 45
MAX_LINES = 20
TRACK_BATCH = 10
QUOTE_WAIT = [1, 1, 2, 2, 3, 3, 4, 4]  # seconds between asks while SEFL is still rating
ACCESSORIALS = {
    'LIFTGATE_DEL': 'chkLGD',
    'RESIDENTIAL_DEL': 'chkPR',
    'LIMITED_ACCESS_DEL': 'chkLAD',
    'INSIDE_DEL': 'chkID',
    'APPOINTMENT_DEL': 'chkAN',
    'NOTIFY_DEL': 'chkAN',
    'LIFTGATE_PU': 'chkLGP',
}
SUBTOTAL_TYPES = {'GFC', 'NFC', 'TTL'}
DOCUMENT_TYPES = [
    ('DR', 'Delivery receipt'),
    ('WI', 'Weight certificate'),
    ('FB', 'Southeastern invoice'),
]


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('sefl', 'Southeastern Freight Lines')],
        ondelete={'sefl': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    sefl_username = fields.Char('MySEFL username', groups='base.group_system', copy=False)
    sefl_password = fields.Char('MySEFL password', groups='base.group_system', copy=False)
    sefl_account = fields.Char(
        'Southeastern account number',
        help='Shipper account number, shown in MySEFL under Shipping Tools > Rate Quotes.')
    sefl_send_dimensions = fields.Boolean(
        'Send pallet dimensions', default=True,
        help='Also send each line\'s dimensions, for accounts on dimension-based pricing.')

    # ------------------------------------------------------------------ connection

    def _sefl_login(self):
        self.ensure_one()
        carrier = self.sudo()
        user, password = (carrier.sefl_username or '').strip(), carrier.sefl_password or ''
        if not user or not password:
            raise UserError(_('Enter the MySEFL username and password on the %s shipping method (Southeastern tab) '
                              'first.', self.name))
        return user, password

    def _sefl_mask(self, text):
        text = str(text or '')
        password = self.sudo().sefl_password or ''
        return text.replace(password, '***') if len(password) > 2 else text

    def _sefl_request(self, method, url, auth=True, **kwargs):
        self.ensure_one()
        headers = {'Accept': 'application/json'}
        headers.update(kwargs.pop('headers', {}))
        if auth:
            kwargs['auth'] = self._sefl_login()
        _logger.info('Southeastern %s %s', method, url)
        try:
            response = requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as error:
            raise UserError(_('Could not reach Southeastern: %s', self._sefl_mask(error))) from error
        if response.status_code == 401:
            raise UserError(_('Southeastern refused the MySEFL login. Check the username and password on the %s '
                              'shipping method.', self.name))
        return response

    @api.model
    def _sefl_json(self, response):
        try:
            data = response.json()
        except ValueError:
            return {}
        return data if isinstance(data, (dict, list)) else {}

    @api.model
    def _sefl_text(self, value):
        return ' '.join(str(value or '').split())

    @api.model
    def _sefl_number(self, value):
        text = re.sub(r'[^0-9.\-]', '', str(value or ''))
        try:
            return round(float(text), 2) if text else 0.0
        except ValueError:
            return 0.0

    def _sefl_failed(self, data):
        return isinstance(data, dict) and str(data.get('errorOccured') or '').strip().lower() == 'true'

    # ------------------------------------------------------------------ request parts

    @api.model
    def _sefl_zip(self, partner):
        if partner.country_id.code == 'CA':
            return ''.join(ch for ch in (partner.zip or '') if ch.isalnum()).upper()[:6]
        postal = digits_only(partner.zip)[:5]
        if len(postal) != 5:
            raise UserError(_('%s needs a 5-digit ZIP code for Southeastern.', partner.display_name))
        return postal

    @api.model
    def _sefl_country(self, partner):
        code = partner.country_id.code or 'US'
        if code not in ('US', 'CA', 'MX'):
            raise UserError(_('Southeastern ships within North America only (%s).', partner.display_name))
        return {'US': 'U', 'CA': 'C', 'MX': 'M'}[code]

    @api.model
    def _sefl_class(self, freight_class):
        """85 -> '85', 77.5 -> '775', 92.5 -> '925' (SEFL's class codes)."""
        try:
            value = float(freight_class)
        except (TypeError, ValueError):
            raise UserError(_('Freight class %s is not a number.', freight_class))
        return str(int(value)) if value == int(value) else str(int(round(value * 10)))

    @api.model
    def _sefl_units(self, shipment):
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the pallets or boxes to %s first.', shipment.name))
        for unit in units:
            if not unit.freight_class or not unit.weight:
                raise UserError(_('Measure and weigh every pallet or box on %s first.', shipment.name))
        if len(units) > MAX_LINES:
            raise UserError(_('Southeastern rates at most %s lines per shipment.', MAX_LINES))
        return units

    def _sefl_rate_form(self, shipment):
        if not (self.sefl_account or '').strip():
            raise UserError(_('Enter the Southeastern account number on the %s shipping method first.', self.name))
        company = shipment.company_id.partner_id
        shipper, consignee = shipment.shipper_id, shipment.partner_id
        ship_date = max(shipment.ship_date or fields.Date.context_today(self), fields.Date.context_today(self))
        form = {
            'CustomerAccount': self.sefl_account.strip(),
            'CustomerName': (company.name or '')[:30],
            'CustomerStreet': (company.street or '')[:30],
            'CustomerCity': (company.city or '')[:30],
            'CustomerState': company.state_id.code or '',
            'CustomerZip': self._sefl_zip(company),
            'Option': 'S',
            'Terms': 'P',
            'PickupDateMM': ship_date.strftime('%m'),
            'PickupDateDD': ship_date.strftime('%d'),
            'PickupDateYYYY': ship_date.strftime('%Y'),
            'OriginCity': (shipper.city or '').upper()[:30],
            'OriginState': shipper.state_id.code or '',
            'OriginZip': self._sefl_zip(shipper),
            'OrigCountry': self._sefl_country(shipper),
            'DestinationCity': (consignee.city or '').upper()[:30],
            'DestinationState': consignee.state_id.code or '',
            'DestinationZip': self._sefl_zip(consignee),
            'DestCountry': self._sefl_country(consignee),
            'returnX': 'Y',
            'rateXML': 'Y',
        }
        units = self._sefl_units(shipment)
        dims = self.sefl_send_dimensions and all(u.length and u.width and u.height for u in units)
        if dims:
            form['DimsOption'] = 'I'
        for index, unit in enumerate(units, 1):
            pieces = max(int(unit.quantity or 1), 1)
            form.update({
                'Class%d' % index: self._sefl_class(unit.freight_class),
                'Weight%d' % index: str(max(int(round(unit.weight)), 1)),
                'WeightUnitOfMeasure%d' % index: 'LBS',
                'Pieces%d' % index: str(pieces),
            })
            if unit.description:
                form['Description%d' % index] = unit.description[:30]
            if dims:
                form.update({
                    'PieceLength%d' % index: str(int(round(unit.length))),
                    'PieceWidth%d' % index: str(int(round(unit.width))),
                    'PieceHeight%d' % index: str(int(round(unit.height))),
                    'UnitOfMeasure%d' % index: 'I',
                    'NumberOfUnits%d' % index: str(pieces),
                })
        for service in shipment.accessorial_ids:
            flag = ACCESSORIALS.get(service.code)
            if flag:
                form[flag] = 'on'
        return form

    # ------------------------------------------------------------------ answers

    def _sefl_quote(self, form):
        """Submit the quote and fetch its details, asking again while SEFL has it queued."""
        response = self._sefl_request('POST', RATE_URL + 'submitQuote', data=form)
        data = self._sefl_json(response)
        if response.status_code >= 400 or self._sefl_failed(data) or not isinstance(data, dict):
            raise UserError(_('Southeastern: %s', self._sefl_mask(
                (data.get('errorMessage') if isinstance(data, dict) else '') or (response.text or '')[:300]
                or _('error %s', response.status_code))))
        number = self._sefl_text(data.get('quoteNumber'))
        if not number:
            raise UserError(_('Southeastern did not return a quote number.'))
        detail = {}
        for wait in [0] + QUOTE_WAIT:
            if wait:
                time.sleep(wait)
            response = self._sefl_request('GET', RATE_URL + number, params={'ReturnDetail': 'Y'})
            detail = self._sefl_json(response)
            if not isinstance(detail, dict):
                detail = {}
            if self._sefl_failed(detail):
                raise UserError(_('Southeastern: %s', self._sefl_mask(detail.get('errorMessage') or number)))
            if not self._sefl_pending(detail):
                break
        status = self._sefl_text(detail.get('status')).upper()
        if self._sefl_pending(detail):
            raise UserError(_('Southeastern is still working on quote %s; try Get rates again in a minute.', number))
        if status == 'UTR':
            raise UserError(_('Southeastern has to rate quote %s by hand; it will be emailed.', number))
        return detail

    def _sefl_pending(self, detail):
        """SEFL is still rating: status ENT, or no status yet with "Quote has not yet been
        processed" (seen 30 Oct 2026)."""
        status = self._sefl_text(detail.get('status')).upper()
        if status in ('RAT', 'UTR'):
            return False
        message = self._sefl_text(detail.get('errorMessage')).lower()
        return status == 'ENT' or 'not yet' in message or not self._sefl_number(detail.get('rateQuote'))

    def _sefl_rate_from_answer(self, data):
        total = self._sefl_number(data.get('rateQuote'))
        if total <= 0:
            raise UserError(_('Southeastern returned no rate: %s',
                              self._sefl_text(data.get('errorMessage') or data.get('specInstr')) or _('no details')))
        lines = []
        for detail in data.get('details') or []:
            kind = self._sefl_text(detail.get('typeCharge')).upper()
            amount = self._sefl_number(detail.get('charges'))
            description = self._sefl_text(detail.get('description'))
            if not amount or kind in SUBTOTAL_TYPES:
                continue
            if kind == 'P':
                lines.append({'code': 'LINEHAUL', 'amount': amount, 'name': _(
                    'Linehaul before discount, class %(cls)s, %(weight)s lb (%(desc)s)',
                    cls=self._sefl_text(detail.get('ratingClass')) or '-',
                    weight=self._sefl_text(detail.get('weight')) or '-', desc=description or '-')})
            elif kind.startswith('D') and 'DISCOUNT' in description.upper():
                lines.append({'code': 'DISC', 'amount': -abs(amount), 'name': description.capitalize()})
            elif kind == 'FS':
                lines.append({'code': 'FUEL', 'amount': amount, 'name': description.capitalize() or _('Fuel surcharge')})
            else:
                lines.append({'code': (kind or 'ACC')[:20], 'amount': amount,
                              'name': description.capitalize() or kind or _('Accessorial')})
        if abs(round(total - sum(line['amount'] for line in lines), 2)) >= 0.01 \
                and any(line['code'] == 'MFC' for line in lines):
            # Minimum charge: SEFL charges the minimum instead of the discounted linehaul.
            minimum_lines = [line for line in lines if line['code'] not in ('LINEHAUL', 'DISC')]
            if abs(round(total - sum(line['amount'] for line in minimum_lines), 2)) < 0.01:
                lines = minimum_lines
        difference = round(total - sum(line['amount'] for line in lines), 2)
        if abs(difference) >= 0.01:
            lines.append({'code': 'OTHER', 'name': _('Other (difference to Southeastern total)'),
                          'amount': difference})
        try:
            days = int(self._sefl_number(data.get('transitTime')))
        except (TypeError, ValueError):
            days = 0
        return {
            'service': _('Southeastern LTL'),
            'total': total,
            'transit_days': days,
            'quote_number': self._sefl_text(data.get('quoteNumber')) or False,
            'charges': lines,
            'sefl_direct': self._sefl_text(data.get('quoteDIP')) or False,
        }

    @api.model
    def _sefl_pro(self, number):
        return digits_only(number).lstrip('0')

    @api.model
    def _sefl_date(self, value):
        text = self._sefl_text(value)
        for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
            try:
                parsed = datetime.strptime(text[:10], fmt).date()
            except ValueError:
                continue
            return parsed if parsed.year > 1900 else False
        return False

    # ------------------------------------------------------------------ selamta_ltl hooks

    def sefl_ltl_rate(self, shipment):
        self.ensure_one()
        return [self._sefl_rate_from_answer(self._sefl_quote(self._sefl_rate_form(shipment)))]

    def sefl_ltl_track(self, shipments):
        self.ensure_one()
        searches = {}
        for shipment in shipments:
            pro = self._sefl_pro(shipment.pro_number)
            if pro:
                searches[pro] = shipment
        results = {}
        pros = list(searches)
        for start in range(0, len(pros), TRACK_BATCH):
            batch = pros[start:start + TRACK_BATCH]
            params = [('Type', 'PN')] + [('RefNum%d' % (i + 1), pro) for i, pro in enumerate(batch)] \
                + [('output', 'JSON')]
            try:
                response = self._sefl_request('GET', TRACE_URL, auth=False, params=params)
            except UserError as error:
                _logger.warning('Southeastern tracking failed for %s: %s', ', '.join(batch), error)
                continue
            data = self._sefl_json(response)
            for entry in (data.get('pro') if isinstance(data, dict) else None) or []:
                shipment = searches.get(self._sefl_pro(entry.get('proNumber')))
                if shipment and not entry.get('error'):
                    results[shipment.id] = self._sefl_tracking_info(entry)
        return results

    def _sefl_tracking_info(self, entry):
        code = self._sefl_text(entry.get('currentStatusCode')).upper()
        text = self._sefl_text(entry.get('currentStatusDescription')) or self._sefl_text(entry.get('location'))
        info = {}
        if code == 'DLV':
            info['state'] = 'delivered'
            delivered = self._sefl_date(entry.get('deliveryDate')) or self._sefl_date(entry.get('currentStatusDateOnly'))
            if delivered:
                info['delivered_date'] = fields.Date.to_string(delivered)
            signed = self._sefl_text(entry.get('signedBy'))
            if signed:
                text = _('%(status)s, signed by %(name)s', status=text or _('Delivered'), name=signed)
        elif code != 'VOD' and (self._sefl_date(entry.get('pickupDate')) or code not in ('', 'ENS')):
            info['state'] = 'in_transit'
            location = self._sefl_text(entry.get('location'))
            if location and location.lower() not in text.lower():
                text = '%s, %s' % (text, location) if text else location
        committed = self._sefl_date(entry.get('committedDate'))
        if committed and info.get('state') != 'delivered':
            text = _('%(status)s, delivery due %(date)s', status=text, date=committed.strftime('%m/%d/%Y'))
        if text:
            info['status'] = text
        return info

    def sefl_ltl_documents(self, shipment):
        self.ensure_one()
        pro = self._sefl_pro(shipment.pro_number)
        if not pro:
            return []
        existing = set(self.env['ir.attachment'].search([
            ('res_model', '=', shipment._name), ('res_id', '=', shipment.id)]).mapped('name'))
        wanted = [(code, label) for code, label in DOCUMENT_TYPES if '%s %s.pdf' % (label, pro) not in existing]
        if not wanted:
            return []
        try:
            response = self._sefl_request('POST', DOCS_URL, json={
                'pros': [pro], 'associated': False, 'imageTypes': [code for code, _label in wanted], 'format': 'pdf'},
                headers={'Content-Type': 'application/json'})
        except UserError as error:
            _logger.info('Southeastern documents for %s not available: %s', pro, error)
            return []
        data = self._sefl_json(response)
        items = data if isinstance(data, list) else (data.get('documents') or data.get('images') or [data])
        names = {'bill of lading': 'BL', 'delivery receipt': 'DR', 'w&i': 'WI', 'freight invoice': 'FB'}
        pages = {}
        for item in items:
            if not isinstance(item, dict) or item.get('error') or not item.get('base64Image'):
                continue
            kind = self._sefl_text(item.get('type'))
            code = names.get(kind.lower(), kind.upper()[:2])
            pages.setdefault(code, []).append(base64.b64decode(item['base64Image']))
        documents = []
        for code, label in wanted:
            parts = pages.get(code)
            if not parts:
                continue
            content = parts[0]
            if len(parts) > 1:
                try:
                    content = merge_pdf(parts)
                except Exception as error:  # keep the first one rather than nothing
                    _logger.info('Could not merge Southeastern %s for %s: %s', code, pro, error)
            documents.append(('%s %s.pdf' % (label, pro), content))
        return documents

    # ------------------------------------------------------------------ Odoo delivery hooks

    def sefl_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('Southeastern rates come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def sefl_send_shipping(self, pickings):
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def sefl_get_tracking_link(self, picking):
        pro = self._sefl_pro(picking.carrier_tracking_ref)
        return PUBLIC_TRACKING_URL % pro if pro else False

    def sefl_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the pickup with Southeastern, then cancel the LTL shipment in Odoo.'))

    def action_sefl_test_connection(self):
        """Sample quote from our dock to Charlotte, NC (500 lb, class 70). Books nothing."""
        self.ensure_one()
        shipper = self.env.company.partner_id
        destination = self.env['res.partner'].new({
            'name': 'Sample', 'city': 'Charlotte', 'zip': '28202', 'country_id': self.env.ref('base.us').id,
            'state_id': self.env['res.country.state'].search(
                [('code', '=', 'NC'), ('country_id.code', '=', 'US')], limit=1).id})
        shipment = self.env['selamta.ltl.shipment'].new({
            'shipper_id': shipper.id, 'partner_id': destination.id, 'carrier_id': self.id,
            'ship_date': fields.Date.context_today(self),
            'unit_ids': [(0, 0, {'unit_type': 'pallet', 'quantity': 1, 'length': 48, 'width': 40,
                                 'height': 48, 'weight': 500, 'class_override': '70'})],
        })
        rate = self._sefl_rate_from_answer(self._sefl_quote(self._sefl_rate_form(shipment)))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _(
                'MySEFL login works. Sample quote %(quote)s (Decatur to Charlotte, 500 lb): %(total).2f, %(days)s days.',
                quote=rate['quote_number'] or '-', total=rate['total'], days=rate['transit_days'])},
        }
