# -*- coding: utf-8 -*-
"""AAA Cooper web services (aaacooper.com > Web Services, documentation behind the login).

* Rate estimate, SOAP: https://api2.aaacooper.com:8200/sapi30/wsGenEst, body
  RateEstimateRequestVO (namespace http://tempuri.org/wsGenRateEstimate/) with Token,
  CustomerNumber, origin/destination, WhoAmI, BillDate MMDDYYYY, PrePaidCollect, AccLine
  (AccCode) and RateEstimateRequestLine (Weight, Class, HandlingUnits, dimensions...).
  Answer RateEstimateResponseVO: ErrorMessage, EstimateNumber, TotalCharges, TotalTransit,
  RateEstimateResponseLine (Description, Charges - negative for discounts, Accessorial).
* Pickup, SOAP: /sapi30/wsPickUpRq, body wsPickUpRqRequest (http://tempuri.org/wsPickUpRq/)
  with TokenID, Pkup* fields, PickupDate MM/DD/YYYY, ReadyTime/CloseTime HH:MM,
  PickupComments, LineItems/LineItem. Answer: PickupRequestNumber, ErrorCode, ErrorMessage,
  AlertMessage, ACTTerminal, ACTTerminalPhone.
* Tracking, SOAP: /sapi30/wsTracking, body GetTrackingRequest (http://tempuri.org/WsGetTracking/)
  with token and ProNumber or BOLNumber. Answer ProLine: ProNumber, Status, PickupDate,
  DeliveryDate, SignedFor, TracingLine.
* Imaging, REST: GET /sapi30/documents?token&proNumber&type(POD, INSPT...)&format=PDF ->
  {"images": [{"url", "type", "format"}]}.
Test hosts (testapi2.aaacooper.com) work only once AAA Cooper sets the account up for them.
"""
import logging
from datetime import date

import requests
from lxml import etree
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.selamta_ltl.models.ltl_common import digits_only

_logger = logging.getLogger(__name__)

HOSTS = {'production': 'https://api2.aaacooper.com:8200', 'test': 'https://testapi2.aaacooper.com:8200'}
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'
RATE_NS = 'http://tempuri.org/wsGenRateEstimate/'
PICKUP_NS = 'http://tempuri.org/wsPickUpRq/'
TRACK_NS = 'http://tempuri.org/WsGetTracking/'
TIMEOUT = 45
# Our accessorial codes -> AAA Cooper accessorial codes (Rate Estimate documentation).
ACCESSORIALS = {
    'LIFTGATE_DEL': 'LGD',
    'RESIDENTIAL_DEL': 'RSD',
    'LIMITED_ACCESS_DEL': 'RAD',
    'INSIDE_DEL': 'ISD',
    'APPOINTMENT_DEL': 'NCM',  # notify + appointment
    'NOTIFY_DEL': 'NCM',
    'LIFTGATE_PU': 'LGP',
}
HANDLING_UNITS = {'pallet': 'Pallets', 'box': 'Cartons'}
DOCUMENT_TYPES = [('POD', 'Delivery receipt'), ('INSPT', 'Inspection certificate')]


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('aaacooper', 'AAA Cooper')],
        ondelete={'aaacooper': lambda recs: recs.write({'delivery_type': 'fixed', 'fixed_price': 0})})

    aact_environment = fields.Selection(
        [('production', 'Production'),
         ('test', 'Test (only after AAA Cooper sets up the test account)')],
        'AAA Cooper environment', default='production', required=True)
    aact_token = fields.Char(
        'AAA Cooper API token', groups='base.group_system', copy=False,
        help='Security API token from aaacooper.com (Workspace > Admin Tools > Web Services).')
    aact_customer_number = fields.Char(
        'AAA Cooper customer number',
        help='Our AAA Cooper account (Account ID). With it, rate estimates use our pricing and '
             'get an estimate number.')
    aact_pallet_pricing = fields.Boolean(
        'Pallet pricing agreement',
        help='Rate by our pallet pricing agreement with AAA Cooper (sends the PALET code and the '
             'pallet count). Leave off unless the agreement includes pallet pricing.')
    aact_book_pickups = fields.Boolean(
        'Request pickups through the API',
        help='With this on, choosing AAA Cooper in the rate shop sends a real pickup request. With '
             'it off, the estimate is saved and the pickup is requested on aaacooper.com.')
    aact_contact_name = fields.Char('AAA Cooper pickup contact')
    aact_contact_phone = fields.Char('AAA Cooper pickup contact phone')
    aact_contact_email = fields.Char('AAA Cooper pickup contact email')

    # ------------------------------------------------------------------ connection

    def ltl_can(self, operation):
        self.ensure_one()
        if self.delivery_type == 'aaacooper' and operation == 'book' and not self.aact_book_pickups:
            return False
        return super().ltl_can(operation)

    def _aact_token(self):
        self.ensure_one()
        token = (self.sudo().aact_token or '').strip()
        if not token:
            raise UserError(_('Enter the AAA Cooper API token on the %s shipping method (AAA Cooper tab) first.',
                              self.name))
        return token

    def _aact_host(self):
        return HOSTS['test' if self.aact_environment == 'test' else 'production']

    @api.model
    def _aact_request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', TIMEOUT)
        _logger.info('AAA Cooper %s %s', method, url.split('?')[0])
        try:
            return requests.request(method, url, **kwargs)
        except requests.RequestException as error:
            raise UserError(_('Could not reach AAA Cooper: %s', error)) from error

    def _aact_soap(self, service, body):
        """POST a SOAP envelope around ``body`` (an lxml element) to /sapi30/<service> and
        return the first child of soap:Body of the answer."""
        nsmap = {'soap': SOAP_NS, 'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                 'xsd': 'http://www.w3.org/2001/XMLSchema'}
        envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=nsmap)
        etree.SubElement(envelope, '{%s}Body' % SOAP_NS).append(body)
        data = etree.tostring(envelope, xml_declaration=True, encoding='utf-8')
        response = self._aact_request('POST', '%s/sapi30/%s' % (self._aact_host(), service), data=data,
                                      headers={'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': '""'})
        try:
            root = etree.fromstring(response.content)
        except (etree.XMLSyntaxError, ValueError):
            raise UserError(_('AAA Cooper answered %(status)s: %(text)s',
                              status=response.status_code, text=(response.text or '')[:300]))
        fault = root.xpath('//*[local-name()="Fault"]')
        if fault:
            raise UserError(_('AAA Cooper: %s', self._aact_text(fault[0], 'faultstring') or _('unknown error')))
        body_nodes = root.xpath('//*[local-name()="Body"]/*')
        if not body_nodes:
            raise UserError(_('AAA Cooper answered %s without a result.', response.status_code))
        return body_nodes[0]

    @api.model
    def _aact_text(self, node, name, default=''):
        found = node.xpath('./*[local-name()=$name]', name=name)
        return (found[0].text or '').strip() if found and found[0].text else default

    @api.model
    def _aact_children(self, node, name):
        return node.xpath('./*[local-name()=$name]', name=name)

    @api.model
    def _aact_add(self, parent, namespace, name, value=None):
        element = etree.SubElement(parent, '{%s}%s' % (namespace, name))
        if value is not None and value is not False:
            element.text = str(value)
        return element

    @api.model
    def _aact_number(self, value, default=0.0):
        try:
            return float(str(value).replace(',', '').strip())
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------ request parts

    @api.model
    def _aact_country(self, partner):
        code = partner.country_id.code or 'US'
        if code not in ('US', 'CA'):
            raise UserError(_('AAA Cooper ships within the United States and Canada only (%s).',
                              partner.display_name))
        return 'CAN' if code == 'CA' else 'USA'

    @api.model
    def _aact_zip(self, partner):
        if partner.country_id.code == 'CA':
            return ''.join(ch for ch in (partner.zip or '') if ch.isalnum()).upper()[:6]
        postal = digits_only(partner.zip)[:5]
        if len(postal) != 5:
            raise UserError(_('%s needs a 5-digit ZIP code for AAA Cooper.', partner.display_name))
        return postal

    @api.model
    def _aact_phone(self, value, label):
        phone = digits_only(value)
        if len(phone) == 11 and phone.startswith('1'):
            phone = phone[1:]
        if len(phone) < 10:
            raise UserError(_('AAA Cooper needs a 10-digit phone number for the %s.', label))
        return phone[:10]

    @api.model
    def _aact_company_name(self, partner):
        return (partner.commercial_partner_id.name if partner.parent_id else partner.name) or ''

    @api.model
    def _aact_units(self, shipment):
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the pallets or boxes to %s first.', shipment.name))
        for unit in units:
            if not unit.freight_class or not unit.weight:
                raise UserError(_('Measure and weigh every pallet or box on %s first.', shipment.name))
        return units

    def _aact_accessorial_codes(self, shipment):
        codes = []
        for service in shipment.accessorial_ids:
            code = ACCESSORIALS.get(service.code)
            if code and code not in codes:
                codes.append(code)
        return codes

    def _aact_rate_body(self, shipment):
        shipper, consignee = shipment.shipper_id, shipment.partner_id
        units = self._aact_units(shipment)
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        pallets = sum(units.filtered(lambda u: u.unit_type == 'pallet').mapped('quantity'))
        body = etree.Element('{%s}RateEstimateRequestVO' % RATE_NS, nsmap={None: RATE_NS})
        add = lambda name, value=None, parent=body: self._aact_add(parent, RATE_NS, name, value)  # noqa: E731
        add('Token', self._aact_token())
        add('CustomerNumber', digits_only(self.aact_customer_number)[:9] or '')
        add('OriginCity', (shipper.city or '')[:25])
        add('OriginState', shipper.state_id.code or '')
        add('OriginZip', self._aact_zip(shipper))
        add('OriginCountryCode', self._aact_country(shipper))
        add('DestinationCity', (consignee.city or '')[:25])
        add('DestinationState', consignee.state_id.code or '')
        add('DestinationZip', self._aact_zip(consignee))
        add('DestinCountryCode', self._aact_country(consignee))
        add('WhoAmI', 'S')
        add('BillDate', ship_date.strftime('%m%d%Y'))
        add('PrePaidCollect', 'P')
        if pallets:
            add('TotalPalletCount', pallets)
        codes = self._aact_accessorial_codes(shipment)
        if self.aact_pallet_pricing and pallets:
            codes.append('PALET')
        for code in codes:
            add('AccCode', code, parent=add('AccLine'))
        for unit in units:
            line = add('RateEstimateRequestLine')
            add('Weight', max(int(round(unit.weight)), 2), parent=line)
            add('Class', unit.freight_class, parent=line)
            if unit.nmfc_item:
                add('NMFC', unit.nmfc_item, parent=line)
                if unit.nmfc_sub:
                    add('NMFCSub', unit.nmfc_sub, parent=line)
            add('HandlingUnits', unit.quantity, parent=line)
            add('HandlingUnitType', HANDLING_UNITS.get(unit.unit_type, 'Pallets'), parent=line)
            add('CubeU', 'IN', parent=line)
            add('Length', int(round(unit.length or 0)), parent=line)
            add('Height', int(round(unit.height or 0)), parent=line)
            add('Width', int(round(unit.width or 0)), parent=line)
        return body

    @api.model
    def _aact_time(self, hours):
        """10.5 -> '10:30'."""
        hours = hours or 0.0
        hour, minute = int(hours), int(round((hours - int(hours)) * 60))
        if minute == 60:
            hour, minute = hour + 1, 0
        return '%02d:%02d' % (min(hour, 23), minute)

    def _aact_pickup_body(self, shipment, rate):
        shipper, consignee = shipment.shipper_id, shipment.partner_id
        for partner, label in ((shipper, _('shipper')), (consignee, _('consignee'))):
            if not partner.street or not partner.city or not partner.state_id:
                raise UserError(_('%(name)s needs a street, city and state for an AAA Cooper pickup (%(label)s).',
                                  name=partner.display_name, label=label))
        units = self._aact_units(shipment)
        company = shipment.company_id
        email = self.aact_contact_email or shipper.email or company.email
        if not email:
            raise UserError(_('AAA Cooper needs a pickup contact email: fill it in on the %s shipping method.',
                              self.name))
        ship_date = shipment.ship_date or fields.Date.context_today(self)
        kinds = set(units.mapped('unit_type'))
        body = etree.Element('{%s}wsPickUpRqRequest' % PICKUP_NS, nsmap={None: PICKUP_NS})
        add = lambda name, value=None, parent=body: self._aact_add(parent, PICKUP_NS, name, value)  # noqa: E731
        add('TokenID', self._aact_token())
        add('PkupCompanyName', self._aact_company_name(shipper)[:30])
        add('PkupCompanyAddress', shipper.street[:30])
        add('PkupCompanyCity', shipper.city[:20])
        add('PkupCompanyState', shipper.state_id.code)
        add('PkupCompanyZip', self._aact_zip(shipper))
        add('PkupCompanyCountry', self._aact_country(shipper))
        add('PkupCompanyContact', (self.aact_contact_name or self.env.user.name or '')[:30])
        add('PkupCompanyEmail', email[:50])
        add('PkupCompanyPhone', self._aact_phone(
            self.aact_contact_phone or shipper.phone or company.phone, _('pickup contact')))
        add('PickupDate', ship_date.strftime('%m/%d/%Y'))
        add('ReadyTime', self._aact_time(shipment.pickup_ready_time))
        add('CloseTime', self._aact_time(shipment.pickup_close_time))
        comments = ['BOL %s' % shipment.bol_reference]
        if shipment.pickup_instructions:
            comments.append(' '.join(shipment.pickup_instructions.split()))
        comments += shipment._bol_delivery_lines()
        add('PickupComments', '. '.join(comments)[:300])
        line = add('LineItem', parent=add('LineItems'))
        estimate = str(rate.get('quote_number') or '')
        if estimate and len(estimate) <= 10:
            add('EstimateNumber', estimate, parent=line)
        add('BOLID', (shipment.bol_reference or '')[:25], parent=line)
        add('Pieces', sum(units.mapped('quantity')), parent=line)
        add('HandlingUnitType', 'Mixed' if len(kinds) > 1 else HANDLING_UNITS.get(kinds.pop(), 'Pallets'),
            parent=line)
        add('TotalWeight', int(round(sum(units.mapped('weight')))), parent=line)
        add('DestinationCompanyName', self._aact_company_name(consignee)[:30], parent=line)
        add('DestinationCompanyAddress', consignee.street[:30], parent=line)
        add('DestinationCompanyContact',
            ((consignee.name if consignee.parent_id else False) or _('Receiving'))[:30], parent=line)
        phone = consignee.phone or consignee.mobile or consignee.commercial_partner_id.phone
        if digits_only(phone):
            add('DestinationCompanyPhone', self._aact_phone(phone, _('consignee')), parent=line)
        if consignee.email:
            add('DestinationCompanyEmail', consignee.email[:50], parent=line)
        add('DestinationCity', consignee.city[:20], parent=line)
        add('DestinationState', consignee.state_id.code, parent=line)
        add('DestinationZip', self._aact_zip(consignee), parent=line)
        add('DestinationCountry', self._aact_country(consignee), parent=line)
        return body

    # ------------------------------------------------------------------ responses

    def _aact_rate_from_answer(self, answer):
        error = self._aact_text(answer, 'ErrorMessage')
        if error:
            raise UserError(_('AAA Cooper: %s', error))
        total = self._aact_number(self._aact_text(answer, 'TotalCharges'))
        if total <= 0:
            message = self._aact_text(answer, 'InformationMessage') or self._aact_text(answer, 'InformationCode')
            raise UserError(_('AAA Cooper returned no rate: %s', message or _('no details')))
        charges = []
        for line in self._aact_children(answer, 'RateEstimateResponseLine'):
            amount = self._aact_number(self._aact_text(line, 'Charges'))
            if not amount:
                continue
            code = self._aact_text(line, 'Accessorial') or 'LINE'
            description = self._aact_text(line, 'Description')
            if description:
                name = description.capitalize()
            else:
                freight_class = self._aact_text(line, 'Class')
                name = _('Linehaul before discount, class %s', freight_class) if freight_class \
                    else _('Linehaul before discount')
            charges.append({'code': code, 'name': name, 'amount': amount})
        if charges:
            difference = round(total - sum(c['amount'] for c in charges), 2)
            if abs(difference) >= 0.01:
                charges.append({'code': 'OTHER', 'name': _('Other (difference to AAA Cooper total)'),
                                'amount': difference})
        service = _('AAA Cooper')
        if self._aact_text(answer, 'InterlineFlag') == 'X':
            service = _('AAA Cooper (interline)')
        return {
            'service': service,
            'total': total,
            'transit_days': int(self._aact_number(self._aact_text(answer, 'TotalTransit'))),
            'quote_number': self._aact_text(answer, 'EstimateNumber') or False,
            'charges': charges,
        }

    @api.model
    def _aact_date(self, value):
        value = (value or '')[:10]
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return False
        return parsed if parsed.year > 1900 else False

    # ------------------------------------------------------------------ selamta_ltl hooks

    def aaacooper_ltl_rate(self, shipment):
        self.ensure_one()
        return [self._aact_rate_from_answer(self._aact_soap('wsGenEst', self._aact_rate_body(shipment)))]

    def aaacooper_ltl_book(self, shipment, rate):
        self.ensure_one()
        if not self.aact_book_pickups:
            raise UserError(_('Pickup requests through the AAA Cooper API are off on %s; request the pickup on '
                              'aaacooper.com and type the PRO.', self.name))
        answer = self._aact_soap('wsPickUpRq', self._aact_pickup_body(shipment, rate))
        number = self._aact_text(answer, 'PickupRequestNumber').lstrip('0')
        error = self._aact_text(answer, 'ErrorMessage')
        if error or not number:
            raise UserError(_('AAA Cooper did not take the pickup request (%(code)s): %(message)s',
                              code=self._aact_text(answer, 'ErrorCode') or '-', message=error or _('no details')))
        terminal = self._aact_text(answer, 'ACTTerminal')
        phone = self._aact_text(answer, 'ACTTerminalPhone')
        if terminal:
            shipment.aact_terminal = '%s (%s)' % (terminal, phone) if phone else terminal
        notes = [_('AAA Cooper pickup request %s. AAA Cooper assigns the PRO at pickup; tracking fills it in.',
                   number)]
        alert = self._aact_text(answer, 'AlertMessage')
        if alert:
            notes.append(_('AAA Cooper: %s', alert))
        if self.aact_environment == 'test':
            notes.append(_('Requested in the AAA Cooper TEST environment: nothing will be picked up.'))
        shipment.message_post(body=Markup('<br/>').join(notes))
        return {'pickup_number': number}

    def aaacooper_ltl_track(self, shipments):
        self.ensure_one()
        results = {}
        for shipment in shipments:
            pro = digits_only(shipment.pro_number)
            if not pro and not shipment.bol_reference:
                continue
            body = etree.Element('{%s}GetTrackingRequest' % TRACK_NS, nsmap={None: TRACK_NS})
            self._aact_add(body, TRACK_NS, 'token', self._aact_token())
            self._aact_add(body, TRACK_NS, 'ProNumber', pro[:10] if pro else '')
            self._aact_add(body, TRACK_NS, 'BOLNumber', '' if pro else shipment.bol_reference[:25])
            self._aact_add(body, TRACK_NS, 'PONumber', '')
            try:
                answer = self._aact_soap('wsTracking', body)
            except UserError as error:
                _logger.warning('AAA Cooper tracking failed for %s: %s', shipment.name, error)
                continue
            lines = self._aact_children(answer, 'ProLine')
            if lines and not self._aact_text(lines[0], 'ErrorMessage'):
                results[shipment.id] = self._aact_tracking_info(shipment, lines[0])
        return results

    @api.model
    def _aact_tracking_info(self, shipment, line):
        info = {}
        pro = self._aact_text(line, 'ProNumber')
        if pro and not shipment.pro_number:
            info['pro_number'] = pro
        status = self._aact_text(line, 'Status')
        delivered = self._aact_date(self._aact_text(line, 'DeliveryDate'))
        if status.lower().startswith('delivered') and 'interline' not in status.lower():
            info['state'] = 'delivered'
            if delivered:
                info['delivered_date'] = fields.Date.to_string(delivered)
        elif self._aact_date(self._aact_text(line, 'PickupDate')) or status:
            if status.lower() not in ('', 'undetermined'):
                info['state'] = 'in_transit'
        events = self._aact_children(line, 'TracingLine')
        latest = self._aact_text(events[-1], 'Description') if events else ''
        text = status
        if latest and latest.lower() != status.lower():
            text = '%s - %s' % (status, latest) if status else latest
        signed = self._aact_text(line, 'SignedFor')
        if signed and info.get('state') == 'delivered':
            text += _(' (signed by %s)', signed)
        if text:
            info['status'] = text
        return info

    def aaacooper_ltl_documents(self, shipment):
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
            response = self._aact_request('GET', '%s/sapi30/documents' % self._aact_host(), params={
                'token': self._aact_token(), 'proNumber': pro, 'type': doc_type, 'format': 'PDF', 'single': 'Yes'})
            if response.status_code != 200:
                _logger.info('AAA Cooper %s for %s not available (%s)', doc_type, pro, response.status_code)
                continue
            try:
                data = response.json()
            except ValueError:
                continue
            for image in (data.get('images') or [])[:1]:
                if not image.get('url'):
                    continue
                download = self._aact_request('GET', image['url'])
                if download.status_code == 200 and download.content:
                    documents.append((name, download.content))
        return documents

    # ------------------------------------------------------------------ Odoo delivery hooks

    def aaacooper_rate_shipment(self, order):
        return {
            'success': False, 'price': 0.0, 'warning_message': False,
            'error_message': _('AAA Cooper rates come from the LTL shipment on the delivery order '
                               '(LTL shipment > Get rates), once the pallets are measured.'),
        }

    def aaacooper_send_shipping(self, pickings):
        return [{'exact_price': picking.ltl_shipment_id.quoted_amount or 0.0,
                 'tracking_number': picking.carrier_tracking_ref or False} for picking in pickings]

    def aaacooper_get_tracking_link(self, picking):
        return 'https://www.aaacooper.com/Track' if picking.carrier_tracking_ref else False

    def aaacooper_cancel_shipment(self, pickings):
        raise UserError(_('Cancel the pickup with AAA Cooper, then cancel the LTL shipment in Odoo.'))

    def action_aact_test_connection(self):
        """Ask AAA Cooper for a sample rate estimate from our dock to itself (500 lb, class 70).
        Books nothing."""
        self.ensure_one()
        shipper = self.env.company.partner_id
        shipment = self.env['selamta.ltl.shipment'].new({
            'shipper_id': shipper.id, 'partner_id': shipper.id, 'carrier_id': self.id,
            'ship_date': fields.Date.context_today(self),
            'unit_ids': [(0, 0, {'unit_type': 'pallet', 'quantity': 1, 'length': 48, 'width': 40,
                                 'height': 48, 'weight': 500, 'class_override': '70'})],
        })
        rate = self.aaacooper_ltl_rate(shipment)[0]
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _(
                'AAA Cooper token works. Sample estimate %(quote)s: %(total).2f.',
                quote=rate['quote_number'] or '-', total=rate['total'])},
        }
