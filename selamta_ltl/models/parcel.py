# -*- coding: utf-8 -*-
"""Parcel next to LTL, on the same shipment.

A shipping method marked "Parcel carrier" is quoted in the LTL rate shop for small loads.
For UPS (Odoo's "UPS" provider, delivery type ups_rest) everything works from the boxes
typed on the LTL shipment, so a shipment needs no delivery order and its boxes need not
match a sales order:

* Rates: every UPS service for those boxes (Rating API, Shoptimeintransit), with our
  negotiated price when UPS returns one, and the transit days.
* Choosing a UPS rate creates the UPS shipment (Shipping API): one label per box, saved on
  the shipment as a 4x6 PDF, and the tracking numbers on the shipment and on its delivery
  orders (so validating a delivery does not buy a second label).
* "Request pickup" on the shipment: on, an on-call UPS pickup is requested for the pickup
  date and window after the labels are made (UPS may charge for it; the charge UPS quotes is
  noted); off, labels only and the boxes go to a UPS Store or drop-off location.
* Cancelling the shipment voids it with UPS (and cancels the pickup). Tracking comes from
  the UPS Track API.

The UPS app is the one of Odoo's own UPS connector (client ID, secret and account number
on the shipping method); the app needs the Rating, Shipping and Tracking API products on
developer.ups.com. Other parcel carriers keep the old behaviour: priced through the sales
orders, labels made by validating the delivery. Parcel deliveries are listed under
LTL & Parcel > Parcel deliveries with their tracking status.
"""
import base64
import io
import logging
import math
import re
import uuid
from datetime import date, timedelta

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round

_logger = logging.getLogger(__name__)

UPS_HOSTS = {'production': 'https://onlinetools.ups.com', 'test': 'https://wwwcie.ups.com'}
UPS_API_VERSION = 'v2409'
TIMEOUT = 30
TRACK_DAYS = 21                 # follow parcels shipped in the last three weeks
PARCEL_MAX_WEIGHT_DEFAULT = 300  # lb; heavier loads are not quoted as parcel
PARCEL_BOX_NAME = 'Parcel box 20x12x12'
RESIDENTIAL_CODE = 'RESIDENTIAL_DEL'

# UPS limits for one package (domestic): 150 lb, 108 in long, 165 in length plus girth.
UPS_MAX_BOX_WEIGHT = 150.0
UPS_MAX_LENGTH = 108.0
UPS_MAX_SIZE = 165.0
UPS_MAX_PACKAGES = 200
UPS_CUSTOMER_PACKAGE = '02'
UPS_PICKUP_DAILY, UPS_PICKUP_COUNTER, UPS_PICKUP_ONE_TIME = '01', '03', '06'
UPS_OVERWEIGHT = 70.0  # lb; the pickup request says when a box is heavier

UPS_SERVICE_NAMES = {
    '03': 'UPS Ground',
    '93': 'UPS Ground Saver',
    '12': 'UPS 3 Day Select',
    '02': 'UPS 2nd Day Air',
    '59': 'UPS 2nd Day Air A.M.',
    '13': 'UPS Next Day Air Saver',
    '01': 'UPS Next Day Air',
    '14': 'UPS Next Day Air Early',
    '75': 'UPS Heavy Goods',
    '11': 'UPS Standard',
    '65': 'UPS Saver',
    '07': 'UPS Worldwide Express',
    '08': 'UPS Worldwide Expedited',
    '54': 'UPS Worldwide Express Plus',
}

# Labels go on one 4 x 6 in page each (thermal label printers), at 200 dpi.
LABEL_DPI = 200
LABEL_PAGE = (4 * LABEL_DPI, 6 * LABEL_DPI)
LABEL_MARGIN = 10


def _money(block):
    """Amount of a UPS charge block ({'MonetaryValue': '12.34', ...}), 0.0 when missing."""
    try:
        return float((block or {}).get('MonetaryValue') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _as_list(value):
    if not value:
        return []
    return value if isinstance(value, list) else [value]


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    ltl_parcel = fields.Boolean(
        'Parcel carrier',
        help='Quote this shipping method (for example UPS) in the LTL rate shop for small loads, '
             'and list its deliveries under LTL & Parcel > Parcel deliveries. UPS is priced from '
             'the boxes on the shipment, and choosing it makes the UPS labels on the shipment.')
    ltl_parcel_token = fields.Char(groups='base.group_system', copy=False, readonly=True)
    ltl_parcel_token_expiry = fields.Datetime(groups='base.group_system', copy=False, readonly=True)

    # ------------------------------------------------------------------ quotes without a hook

    def ltl_parcel_rate(self, shipment):
        """Parcel price for the shipment's orders through this shipping method's own rating
        (Odoo's standard rate_shipment on each sale order). Used for parcel carriers that
        cannot be priced from the boxes. Returns (total, message)."""
        self.ensure_one()
        orders = shipment.picking_ids.mapped('sale_id') if 'sale_id' in shipment.picking_ids._fields else []
        if not orders:
            raise UserError(_('Parcel quotes need the shipment\'s delivery orders to come from sales orders.'))
        total, notes = 0.0, []
        for order in orders:
            result = self.rate_shipment(order)
            if not result.get('success'):
                raise UserError(result.get('error_message') or _('%s returned no price.', self.name))
            total += result.get('carrier_price', result.get('price')) or 0.0
            if result.get('warning_message'):
                notes.append(result['warning_message'])
        return total, ' '.join(notes)

    # ------------------------------------------------------------------ tracking (deliveries)

    def ltl_parcel_track(self, pickings):
        """{picking.id: {'status', 'delivered_date'}} from the carrier, when this shipping
        method's provider has a tracking hook (<delivery_type>_ltl_parcel_track)."""
        self.ensure_one()
        method = getattr(self, '%s_ltl_parcel_track' % self.delivery_type, None)
        return method(pickings) if method else {}

    # ------------------------------------------------------------------ UPS connection

    def _ltl_ups_credentials(self):
        """(client ID, client secret, shipper number, environment) of Odoo's UPS connector."""
        self.ensure_one()
        carrier = self.sudo()
        values = [carrier[name] if name in carrier._fields else False
                  for name in ('ups_client_id', 'ups_client_secret', 'ups_shipper_number')]
        if not all(values):
            raise UserError(_('%s has no UPS client ID, secret and account number.', self.name))
        return values[0], values[1], values[2], 'production' if self.prod_environment else 'test'

    def _ltl_ups_setting(self, name, default):
        """A setting of Odoo's UPS connector on this shipping method, or the default."""
        self.ensure_one()
        return (self[name] if name in self._fields else False) or default

    def _ltl_ups_token(self, host, client_id, secret, shipper):
        carrier = self.sudo()
        now = fields.Datetime.now()
        if carrier.ltl_parcel_token and carrier.ltl_parcel_token_expiry and carrier.ltl_parcel_token_expiry > now:
            return carrier.ltl_parcel_token
        try:
            response = requests.request(
                'POST', host + '/security/v1/oauth/token', data={'grant_type': 'client_credentials'},
                auth=(client_id, secret), headers={'x-merchant-id': shipper}, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise UserError(_('Could not reach UPS: %s', error)) from error
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code != 200 or not data.get('access_token'):
            raise UserError(_('UPS refused the sign-in (%(status)s): %(text)s',
                              status=response.status_code, text=(response.text or '')[:200]))
        try:
            lifetime = int(float(data.get('expires_in') or 3600))
        except (TypeError, ValueError):
            lifetime = 3600
        carrier.write({'ltl_parcel_token': data['access_token'],
                       'ltl_parcel_token_expiry': now + timedelta(seconds=max(lifetime - 300, 60))})
        return data['access_token']

    @api.model
    def _ltl_ups_errors(self, data):
        errors = ((data or {}).get('response') or {}).get('errors') or []
        return '; '.join(str(e.get('message') or e.get('code') or '') for e in _as_list(errors) if e).strip()

    def _ltl_ups_api(self, method, path, payload=None, extra_headers=None):
        """Call a UPS API (path after /api) with this shipping method's UPS app and return
        the JSON answer. Raise UserError with UPS's own message when it refuses."""
        self.ensure_one()
        client_id, secret, shipper, environment = self._ltl_ups_credentials()
        host = UPS_HOSTS[environment]
        token = self._ltl_ups_token(host, client_id, secret, shipper)
        headers = {'Authorization': 'Bearer %s' % token, 'transId': uuid.uuid4().hex[:32],
                   'transactionSrc': 'selamta_ltl'}
        headers.update(extra_headers or {})
        try:
            response = requests.request(method, host + '/api' + path, json=payload, headers=headers,
                                        timeout=TIMEOUT)
        except requests.RequestException as error:
            raise UserError(_('Could not reach UPS: %s', error)) from error
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code == 401:
            self.sudo().write({'ltl_parcel_token': False, 'ltl_parcel_token_expiry': False})
        if response.status_code != 200:
            raise UserError(_('UPS: %s', self._ltl_ups_errors(data) or (response.text or '')[:300]
                              or response.status_code))
        return data

    # ------------------------------------------------------------------ UPS request parts

    @api.model
    def _ltl_ups_party(self, partner, role):
        """Name, contact, phone and address of a partner for a UPS request."""
        company = partner.commercial_partner_id if partner.parent_id else partner
        missing = [label for label, value in ((_('street'), partner.street), (_('city'), partner.city),
                                              (_('ZIP code'), partner.zip), (_('country'), partner.country_id))
                   if not value]
        if missing:
            raise UserError(_('UPS needs the %(what)s of the %(role)s (%(name)s).',
                              what=', '.join(missing), role=role, name=partner.display_name))
        postal = (partner.zip or '').strip()
        if partner.country_id.code == 'US':
            postal = re.sub(r'\D', '', postal)[:9]
        address = {
            'AddressLine': [line[:35] for line in (partner.street, partner.street2) if line],
            'City': partner.city[:30],
            'StateProvinceCode': partner.state_id.code or '',
            'PostalCode': postal,
            'CountryCode': partner.country_id.code,
        }
        party = {'Name': (company.name or partner.name or '')[:35], 'Address': address}
        if partner.parent_id and partner.name:
            party['AttentionName'] = partner.name[:35]
        phone = re.sub(r'\D', '', partner.phone or partner.mobile or company.phone or company.mobile or '')
        if len(phone) == 11 and phone.startswith('1'):
            phone = phone[1:]
        if phone:
            party['Phone'] = {'Number': phone[:15]}
        return party

    @api.model
    def _ltl_ups_boxes(self, shipment):
        """[(unit line, count, weight of one box in lb)] for the shipment's box lines.
        UserError when a line is a pallet, is not measured, or is too big for UPS."""
        units = shipment.unit_ids.sorted('sequence')
        if not units:
            raise UserError(_('Add the boxes on %s first.', shipment.name))
        if units.filtered(lambda u: u.unit_type != 'box'):
            raise UserError(_('UPS takes boxes only: set the Type of every line to Box (pallets go LTL).'))
        if units.filtered(lambda u: not (u.length and u.width and u.height and u.weight)):
            raise UserError(_('Measure every box for a UPS price: length, width, height (inches) and weight.'))
        boxes, count_all = [], 0
        for unit in units:
            count = max(unit.quantity or 1, 1)
            count_all += count
            each = max(unit.weight / count, 1.0)
            longest, middle, shortest = sorted((unit.length, unit.width, unit.height), reverse=True)
            if each > UPS_MAX_BOX_WEIGHT:
                raise UserError(_(
                    'Each box on the line "%(line)s" weighs %(weight)s lb; UPS takes up to %(max)s lb a box. '
                    'The weight on a line is the total of all its boxes: check the count.',
                    line=unit.description, weight='%.1f' % each, max='%g' % UPS_MAX_BOX_WEIGHT))
            if longest > UPS_MAX_LENGTH or longest + 2 * (middle + shortest) > UPS_MAX_SIZE:
                raise UserError(_(
                    'A box of %(l)s x %(w)s x %(h)s in is too big for UPS (up to 108 in long and 165 in '
                    'length plus girth).', l='%g' % unit.length, w='%g' % unit.width, h='%g' % unit.height))
            boxes.append((unit, count, each))
        if count_all > UPS_MAX_PACKAGES:
            raise UserError(_('UPS takes up to %s boxes on one shipment.', UPS_MAX_PACKAGES))
        return boxes

    def _ltl_ups_packages(self, boxes, ship=False, references=()):
        """One UPS package per box."""
        self.ensure_one()
        dimension_unit = self._ltl_ups_setting('ups_package_dimension_unit', 'IN')
        weight_unit = self._ltl_ups_setting('ups_package_weight_unit', 'LBS')

        def size(inches):
            return '%.1f' % (inches * 2.54 if dimension_unit == 'CM' else inches)

        def weight(pounds):
            value = pounds * 0.45359237 if weight_unit == 'KGS' else pounds
            return '%.1f' % (math.ceil(value * 10) / 10.0)

        packages = []
        for unit, count, each in boxes:
            package_type = unit.package_type_id
            code = UPS_CUSTOMER_PACKAGE
            if package_type and getattr(package_type, 'package_carrier_type', 'none') in ('ups', 'ups_rest'):
                code = package_type.shipper_package_code or UPS_CUSTOMER_PACKAGE
            for _number in range(count):
                package = {
                    'Packaging' if ship else 'PackagingType': {'Code': code},
                    'Dimensions': {
                        'UnitOfMeasurement': {'Code': dimension_unit},
                        'Length': size(unit.length), 'Width': size(unit.width), 'Height': size(unit.height),
                    },
                    'PackageWeight': {'UnitOfMeasurement': {'Code': weight_unit}, 'Weight': weight(each)},
                }
                if ship:
                    package['Description'] = (unit.description or '')[:35]
                    refs = [{'Value': value[:35]} for value in references if value]
                    if refs:
                        package['ReferenceNumber'] = refs[:2]
                packages.append(package)
        return packages

    def _ltl_ups_shipment(self, shipment, boxes, ship=False, service=None):
        """The Shipment block shared by the Rating and Shipping APIs."""
        self.ensure_one()
        account = self._ltl_ups_credentials()[2]
        shipper = self._ltl_ups_party(shipment.company_id.partner_id, _('shipper (our company)'))
        shipper['ShipperNumber'] = account
        ship_to = self._ltl_ups_party(shipment.partner_id, _('consignee'))
        if RESIDENTIAL_CODE in shipment.accessorial_ids.mapped('code'):
            ship_to['Address']['ResidentialAddressIndicator'] = 'Y'
        payment = {'ShipmentCharge': [{'Type': '01', 'BillShipper': {'AccountNumber': account}}]}
        references = (shipment.name, shipment.order_refs or '') if ship else ()
        data = {
            'Shipper': shipper,
            'ShipTo': ship_to,
            'ShipFrom': self._ltl_ups_party(shipment.shipper_id, _('ship-from address')),
            'PaymentInformation' if ship else 'PaymentDetails': payment,
            'Package': self._ltl_ups_packages(boxes, ship=ship, references=references),
            'ShipmentRatingOptions': {'NegotiatedRatesIndicator': 'Y'},
        }
        if service:
            data['Service'] = {'Code': service, 'Description': UPS_SERVICE_NAMES.get(service, service)}
        return data

    @api.model
    def _ltl_ups_pickup_date(self, shipment):
        today = fields.Date.context_today(shipment)
        return max(shipment.ship_date or today, today)

    # ------------------------------------------------------------------ UPS hooks for the shipment

    def ups_rest_ltl_rate(self, shipment):
        """Every UPS service for the boxes on the shipment, cheapest first."""
        self.ensure_one()
        boxes = self._ltl_ups_boxes(shipment)
        data = self._ltl_ups_shipment(shipment, boxes)
        weight_unit = self._ltl_ups_setting('ups_package_weight_unit', 'LBS')
        total_weight = sum(float(p['PackageWeight']['Weight']) for p in data['Package'])
        timed = dict(data)
        timed['ShipmentTotalWeight'] = {'UnitOfMeasurement': {'Code': weight_unit}, 'Weight': '%.1f' % total_weight}
        timed['DeliveryTimeInformation'] = {
            'PackageBillType': '03',
            'Pickup': {'Date': self._ltl_ups_pickup_date(shipment).strftime('%Y%m%d')},
        }
        reference = {'CustomerContext': shipment.name}
        pickup_type = {'Code': UPS_PICKUP_ONE_TIME if shipment.request_pickup else UPS_PICKUP_COUNTER}
        try:
            answer = self._ltl_ups_api('POST', '/rating/%s/Shoptimeintransit' % UPS_API_VERSION, {'RateRequest': {
                'Request': {'RequestOption': 'Shoptimeintransit', 'TransactionReference': reference},
                'PickupType': pickup_type, 'Shipment': timed}})
        except UserError as error:
            # Prices without transit days are better than none.
            _logger.info('UPS rating with transit times failed for %s (%s); asking without.', shipment.name, error)
            answer = self._ltl_ups_api('POST', '/rating/%s/Shop' % UPS_API_VERSION, {'RateRequest': {
                'Request': {'RequestOption': 'Shop', 'TransactionReference': reference},
                'PickupType': pickup_type, 'Shipment': data}})
        rates = []
        for rated in _as_list((answer.get('RateResponse') or {}).get('RatedShipment')):
            code = str((rated.get('Service') or {}).get('Code') or '')
            published = _money(rated.get('TotalCharges'))
            negotiated = _money((rated.get('NegotiatedRateCharges') or {}).get('TotalCharge'))
            total = negotiated or published
            if not code or total <= 0:
                continue
            arrival = (((rated.get('TimeInTransit') or {}).get('ServiceSummary') or {}).get('EstimatedArrival') or {})
            days = arrival.get('BusinessDaysInTransit') or (rated.get('GuaranteedDelivery') or {}).get('BusinessDaysInTransit')
            try:
                days = int(days or 0)
            except (TypeError, ValueError):
                days = 0
            name = UPS_SERVICE_NAMES.get(code, _('UPS service %s', code))
            rates.append({
                'total': total,
                'service': name,
                'transit_days': days,
                'ups_service': code,
                'published': published,
                'charges': [{'code': code, 'name': name, 'amount': total}],
            })
        if not rates:
            raise UserError(_('UPS returned no price for these boxes.'))
        # UPS can answer a service twice (one service code, two prices). Booking sends only
        # the code, so one line per service: the lower price.
        best = {}
        for rate in sorted(rates, key=lambda rate: rate['total']):
            best.setdefault(rate['ups_service'], rate)
        return sorted(best.values(), key=lambda rate: rate['total'])

    def ups_rest_ltl_book(self, shipment, rate):
        """Create the UPS shipment for the boxes: one label per box. Returns the tracking
        numbers, the UPS shipment number, the price UPS charged and the labels."""
        self.ensure_one()
        boxes = self._ltl_ups_boxes(shipment)
        service = rate.get('ups_service') or self._ltl_ups_setting('ups_default_service_type', '03')
        data = self._ltl_ups_shipment(shipment, boxes, ship=True, service=service)
        data['Description'] = (boxes[0][0].description or _('Foodstuff'))[:50]
        pickup = self._ltl_ups_pickup_date(shipment)
        if pickup > fields.Date.context_today(shipment):
            data['ShipmentDate'] = pickup.strftime('%Y%m%d')
        label_type = self._ltl_ups_setting('ups_label_file_type', 'GIF')
        labels_spec = {'LabelImageFormat': {'Code': label_type}, 'LabelStockSize': {'Height': '6', 'Width': '4'}}
        if label_type == 'GIF':
            labels_spec['HTTPUserAgent'] = 'Mozilla/4.5'
        answer = self._ltl_ups_api('POST', '/shipments/%s/ship' % UPS_API_VERSION, {'ShipmentRequest': {
            'Request': {'RequestOption': 'nonvalidate', 'TransactionReference': {'CustomerContext': shipment.name}},
            'Shipment': data,
            'LabelSpecification': labels_spec,
        }})
        results = (answer.get('ShipmentResponse') or {}).get('ShipmentResults') or {}
        packages = _as_list(results.get('PackageResults'))
        numbers = [p['TrackingNumber'] for p in packages if p.get('TrackingNumber')]
        shipment_number = results.get('ShipmentIdentificationNumber') or (numbers[0] if numbers else False)
        if not shipment_number:
            raise UserError(_('UPS answered without a tracking number; nothing was saved. Check ups.com before '
                              'trying again.'))
        total = _money((results.get('NegotiatedRateCharges') or {}).get('TotalCharge')) \
            or _money((results.get('ShipmentCharges') or {}).get('TotalCharges')) or rate.get('total') or 0.0
        images = []
        for package in packages:
            image = ((package.get('ShippingLabel') or {}).get('GraphicImage'))
            if image:
                images.append(base64.b64decode(image))
        result = {
            'tracking_numbers': numbers or [shipment_number],
            'ups_shipment_id': shipment_number,
            'total': total,
            'service': UPS_SERVICE_NAMES.get(service, service),
            'documents': self._ltl_ups_label_documents(shipment, images, label_type),
            'notes': [],
        }
        if shipment.request_pickup:
            # The labels are bought: a pickup UPS refuses must not lose them.
            try:
                number, charge = self._ltl_ups_request_pickup(shipment, boxes, service, numbers)
            except UserError as error:
                result['notes'].append(_(
                    'UPS did not take the pickup request (%s). Schedule the pickup on ups.com, or take the '
                    'boxes to a UPS Store or drop-off location.', error.args[0] if error.args else error))
            else:
                result['pickup_number'] = number
                result['notes'].append(_('UPS pickup %(number)s requested for %(date)s, %(ready)s to %(close)s%(charge)s.',
                                         number=number, date=self._ltl_ups_pickup_date(shipment).strftime('%a %m/%d'),
                                         ready=shipment._format_time(shipment.pickup_ready_time),
                                         close=shipment._format_time(shipment.pickup_close_time),
                                         charge=charge and _('; UPS pickup charge %s', charge) or ''))
        else:
            result['notes'].append(_('No UPS pickup requested: take the boxes to a UPS Store or UPS drop-off '
                                     'location (not a USPS post office).'))
        return result

    @api.model
    def _ltl_ups_hhmm(self, hours):
        minutes = int(round((hours or 0.0) * 60))
        return '%02d%02d' % divmod(min(max(minutes, 0), 23 * 60 + 59), 60)

    def _ltl_ups_request_pickup(self, shipment, boxes, service, numbers):
        """Ask UPS for an on-call pickup of the labelled boxes at the ship-from address.
        Returns (pickup request number, the charge UPS quotes as text or '')."""
        self.ensure_one()
        account = self._ltl_ups_credentials()[2]
        origin = shipment.shipper_id
        party = self._ltl_ups_party(origin, _('ship-from address'))
        phone = (party.get('Phone') or {}).get('Number')
        if not phone:
            raise UserError(_('the ship-from address (%s) has no phone number for the driver', origin.display_name))
        address = party['Address']
        company = origin.commercial_partner_id
        contact = origin.name if origin.parent_id else (self.env.user.name or company.name)
        if shipment.pickup_close_time <= shipment.pickup_ready_time:
            raise UserError(_('the dock closes before the freight is ready'))
        count = sum(count for _unit, count, _each in boxes)
        weight = sum(count * each for _unit, count, each in boxes)
        request = {
            'Request': {'TransactionReference': {'CustomerContext': shipment.name}},
            'RatePickupIndicator': 'Y',
            'Shipper': {'Account': {'AccountNumber': account,
                                    'AccountCountryCode': shipment.company_id.country_id.code or 'US'}},
            'PickupDateInfo': {
                'ReadyTime': self._ltl_ups_hhmm(shipment.pickup_ready_time),
                'CloseTime': self._ltl_ups_hhmm(shipment.pickup_close_time),
                'PickupDate': self._ltl_ups_pickup_date(shipment).strftime('%Y%m%d'),
            },
            'PickupAddress': {
                'CompanyName': (company.name or '')[:27],
                'ContactName': (contact or '')[:22],
                'AddressLine': address['AddressLine'][:1],
                'City': address['City'],
                'StateProvince': address['StateProvinceCode'],
                'PostalCode': address['PostalCode'][:5] if address['CountryCode'] == 'US' else address['PostalCode'][:8],
                'CountryCode': address['CountryCode'],
                'ResidentialIndicator': 'N',
                'Phone': {'Number': phone},
            },
            'AlternateAddressIndicator': 'N' if origin.commercial_partner_id == shipment.company_id.partner_id else 'Y',
            'PickupPiece': [{'ServiceCode': str(service).zfill(3), 'Quantity': str(count),
                             'DestinationCountryCode': shipment.partner_id.country_id.code or 'US',
                             'ContainerCode': '01'}],
            'TotalWeight': {'Weight': '%.1f' % weight, 'UnitOfMeasurement': 'LBS'},
            'OverweightIndicator': 'Y' if any(each > UPS_OVERWEIGHT for _u, _c, each in boxes) else 'N',
            'PaymentMethod': '01',
            'ShippingLabelsAvailable': 'Y',
            'ReferenceNumber': shipment.name[:35],
        }
        if origin.street2:
            request['PickupAddress']['Room'] = origin.street2[:8]
        if numbers:
            request['TrackingData'] = [{'TrackingNumber': number} for number in numbers[:30]]
        instructions = ' '.join((shipment.pickup_instructions or '').split())
        if instructions:
            request['SpecialInstruction'] = instructions[:57]
        answer = self._ltl_ups_api('POST', '/pickupcreation/%s/pickup' % UPS_API_VERSION,
                                   {'PickupCreationRequest': request})
        created = answer.get('PickupCreationResponse') or {}
        number = str(created.get('PRN') or '').strip()
        if not number:
            raise UserError(_('UPS answered without a pickup request number'))
        rated = created.get('RateResult') or {}
        charge = rated.get('GrandTotalOfAllIncentedCharge') or rated.get('GrandTotalOfAllCharge') or ''
        if charge:
            charge = '%s %s' % (charge, rated.get('CurrencyCode') or 'USD')
        return number, charge

    @api.model
    def _ltl_ups_label_documents(self, shipment, images, label_type):
        if not images:
            return []
        if label_type == 'GIF':
            try:
                return [('UPS labels %s.pdf' % shipment.name, self._ltl_ups_labels_pdf(images))]
            except Exception as error:  # the labels are bought: keep them even if the PDF fails
                _logger.warning('Could not turn the UPS labels of %s into a PDF: %s', shipment.name, error)
                return [('UPS label %s-%s.gif' % (shipment.name, i), image) for i, image in enumerate(images, 1)]
        return [('UPS labels %s.%s' % (shipment.name, label_type.lower()), b'\n'.join(images))]

    @api.model
    def _ltl_ups_labels_pdf(self, images):
        """One 4 x 6 in PDF page per label, upright. UPS sends GIF labels lying on their side
        with blank space around them."""
        from PIL import Image, ImageOps
        pages = []
        for raw in images:
            image = Image.open(io.BytesIO(raw)).convert('RGB')
            box = ImageOps.invert(image.convert('L')).getbbox()
            if box:
                image = image.crop(box)
            if image.width > image.height:
                image = image.rotate(-90, expand=True)
            image.thumbnail((LABEL_PAGE[0] - 2 * LABEL_MARGIN, LABEL_PAGE[1] - 2 * LABEL_MARGIN))
            page = Image.new('RGB', LABEL_PAGE, 'white')
            page.paste(image, ((LABEL_PAGE[0] - image.width) // 2, LABEL_MARGIN))
            pages.append(page)
        output = io.BytesIO()
        pages[0].save(output, 'PDF', resolution=LABEL_DPI, save_all=True, append_images=pages[1:])
        return output.getvalue()

    def ups_rest_ltl_cancel(self, shipment):
        """Void the UPS shipment. UPS only voids labels that have not been scanned yet."""
        self.ensure_one()
        number = shipment.parcel_shipment_number
        if not number:
            raise UserError(_('%s has no UPS shipment number: void the labels on ups.com.', shipment.name))
        _client, _secret, account, _env = self._ltl_ups_credentials()
        answer = self._ltl_ups_api('DELETE', '/shipments/%s/void/cancel/%s' % (UPS_API_VERSION, number),
                                   extra_headers={'shipperNumber': account})
        status = ((answer.get('VoidShipmentResponse') or {}).get('SummaryResult') or {}).get('Status') or {}
        if str(status.get('Code')) != '1':
            raise UserError(_('UPS did not void %(number)s: %(status)s', number=number,
                              status=status.get('Description') or _('no answer')))
        shipment._parcel_clear_tracking()
        message = _('UPS shipment %s voided: throw away its labels.', number)
        pickup = (shipment.pickup_number or '').strip()
        if pickup:
            try:
                self._ltl_ups_api('DELETE', '/shipments/%s/pickup/02' % UPS_API_VERSION,
                                  extra_headers={'Prn': pickup})
            except UserError as error:
                message += ' ' + _('UPS did not cancel pickup %(pickup)s (%(error)s): cancel it on ups.com.',
                                   pickup=pickup, error=error.args[0] if error.args else error)
            else:
                message += ' ' + _('UPS pickup %s cancelled.', pickup)
        return message

    def ups_rest_ltl_track(self, shipments):
        """Tracking for shipments shipped by UPS from the LTL shipment."""
        self.ensure_one()
        results = {}
        for shipment in shipments:
            numbers = [n for n in re.split(r'[\s,;+]+', shipment.parcel_tracking_ref or '') if n]
            if not numbers:
                continue
            packages = self._ltl_ups_track_packages(numbers)
            if not packages:
                continue
            info = self._ltl_ups_tracking_info(packages)
            if info.get('delivered_date'):
                info['state'] = 'delivered'
            elif info.pop('moving', False):
                info['state'] = 'in_transit'
            info.pop('moving', None)
            results[shipment.id] = info
        return results

    # ------------------------------------------------------------------ UPS tracking

    def _ltl_ups_track_packages(self, numbers):
        """The package entries of the UPS Track API for these tracking numbers."""
        self.ensure_one()
        client_id, secret, shipper, environment = self._ltl_ups_credentials()
        host = UPS_HOSTS[environment]
        token = self._ltl_ups_token(host, client_id, secret, shipper)
        packages = []
        for number in numbers:
            try:
                response = requests.request(
                    'GET', '%s/api/track/v1/details/%s' % (host, number),
                    params={'locale': 'en_US', 'returnSignature': 'false'},
                    headers={'Authorization': 'Bearer %s' % token, 'transId': uuid.uuid4().hex[:32],
                             'transactionSrc': 'selamta_ltl'},
                    timeout=TIMEOUT)
            except requests.RequestException as error:
                _logger.warning('UPS tracking %s failed: %s', number, error)
                continue
            if response.status_code in (401, 403):
                raise UserError(_('UPS refused tracking (%s). Add the Tracking API to the UPS app on '
                                  'developer.ups.com.', response.status_code))
            try:
                data = response.json()
            except ValueError:
                continue
            for shipment in (data.get('trackResponse') or {}).get('shipment') or []:
                packages.extend(shipment.get('package') or [])
        return packages

    def ups_rest_ltl_parcel_track(self, pickings):
        self.ensure_one()
        results = {}
        for picking in pickings:
            numbers = [n for n in re.split(r'[\s,;+]+', picking.carrier_tracking_ref or '') if n]
            packages = self._ltl_ups_track_packages(numbers) if numbers else []
            if packages:
                info = self._ltl_ups_tracking_info(packages)
                info.pop('moving', None)
                results[picking.id] = info
        return results

    @api.model
    def _ltl_ups_date(self, value):
        value = re.sub(r'\D', '', str(value or ''))[:8]
        try:
            return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        except (ValueError, IndexError):
            return False

    @api.model
    def _ltl_ups_tracking_info(self, packages):
        delivered_dates, texts, all_delivered, moving = [], [], True, False
        for package in packages:
            current = package.get('currentStatus') or {}
            activities = package.get('activity') or []
            latest = activities[0] if activities else {}
            status = latest.get('status') or {}
            delivered = (status.get('type') == 'D') or (current.get('code') == '011')
            all_delivered = all_delivered and delivered
            # M = label made (not handed to UPS yet); anything else means UPS has it.
            moving = moving or bool(status.get('type') and status.get('type') != 'M')
            text = current.get('description') or status.get('description') or ''
            address = ((latest.get('location') or {}).get('address') or {})
            place = ', '.join(filter(None, [address.get('city'), address.get('stateProvince')]))
            texts.append(' - '.join(filter(None, [text.strip().title() if text.isupper() else text.strip(), place])))
            for entry in package.get('deliveryDate') or []:
                if entry.get('type') == 'DEL':
                    delivered_dates.append(self._ltl_ups_date(entry.get('date')))
            if delivered and not package.get('deliveryDate'):
                delivered_dates.append(self._ltl_ups_date(latest.get('date')))
        info = {'status': '; '.join(dict.fromkeys(t for t in texts if t)) or False, 'moving': moving}
        dates = [d for d in delivered_dates if d]
        if all_delivered and dates:
            info['delivered_date'] = max(dates)
        return info


class LtlShipment(models.Model):
    _inherit = 'selamta.ltl.shipment'

    ltl_parcel = fields.Boolean(related='carrier_id.ltl_parcel', string='Parcel')
    parcel_tracking_ref = fields.Char(
        'Tracking numbers', copy=False, tracking=True,
        help='UPS tracking numbers, one per box, from the labels made on this shipment.')
    parcel_shipment_number = fields.Char(
        'UPS shipment number', copy=False, readonly=True,
        help='The number UPS knows the whole shipment by; used to void it.')
    parcel_label_id = fields.Many2one('ir.attachment', 'Parcel labels', copy=False, readonly=True)

    def _apply_parcel_booking(self, result):
        """Save what UPS returned for the labels on the shipment and on its deliveries."""
        self.ensure_one()
        numbers = result.get('tracking_numbers') or []
        vals = {
            'state': 'booked',
            'parcel_tracking_ref': ' '.join(numbers),
            'parcel_shipment_number': result.get('ups_shipment_id') or False,
            'pickup_number': result.get('pickup_number') or False,
        }
        if result.get('total'):
            vals['quoted_amount'] = result['total']
        self.write(vals)
        attachments = self._attach_documents(result.get('documents') or [], _(
            'UPS labels made: %(service)s, %(count)s box(es), tracking %(numbers)s. Print the labels and '
            'stick one on each box.', service=result.get('service') or self.carrier_id.name,
            count=len(numbers), numbers=', '.join(numbers)))
        if attachments:
            self.parcel_label_id = attachments[:1]
            self.message_main_attachment_id = attachments[:1]
        for note in result.get('notes') or []:
            self.message_post(body=note)
        pickings = self.picking_ids.filtered(lambda p: p.state != 'cancel')
        if pickings:
            # With the tracking number on it, validating a delivery does not buy a second label.
            pickings.write({
                'carrier_id': self.carrier_id.id,
                'carrier_tracking_ref': ','.join(numbers),
                'carrier_price': result.get('total') or self.quoted_amount,
            })
            for picking in pickings:
                picking.message_post(body=_(
                    'UPS labels made on %(shipment)s (tracking %(numbers)s). Validate this delivery as '
                    'usual: no second label is bought.', shipment=self.name, numbers=', '.join(numbers)))

    def _parcel_clear_tracking(self):
        """After a void: the boxes have no UPS labels any more."""
        for shipment in self:
            numbers = ','.join((shipment.parcel_tracking_ref or '').split())
            pickings = shipment.picking_ids.filtered(
                lambda p, n=numbers: n and p.carrier_tracking_ref == n)
            pickings.write({'carrier_tracking_ref': False})
            shipment.write({'parcel_tracking_ref': False, 'parcel_shipment_number': False,
                            'parcel_label_id': False})

    def action_parcel_labels(self):
        self.ensure_one()
        if not self.parcel_label_id:
            raise UserError(_('%s has no parcel labels.', self.name))
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': '/web/content/%s' % self.parcel_label_id.id}


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ltl_parcel = fields.Boolean(related='carrier_id.ltl_parcel', string='Parcel')
    parcel_status = fields.Char('Parcel status', copy=False, readonly=True)
    parcel_delivered_date = fields.Date('Parcel delivered on', copy=False, readonly=True)

    def action_parcel_update_tracking(self):
        self._parcel_update_tracking(raise_errors=True)

    def _parcel_update_tracking(self, raise_errors=False):
        by_carrier = {}
        for picking in self.filtered(lambda p: p.carrier_id.ltl_parcel and p.carrier_tracking_ref):
            by_carrier.setdefault(picking.carrier_id, self.browse())
            by_carrier[picking.carrier_id] |= picking
        for carrier, pickings in by_carrier.items():
            try:
                results = carrier.ltl_parcel_track(pickings)
            except Exception as error:  # one carrier failing must not stop the rest
                if raise_errors:
                    raise
                _logger.warning('Parcel tracking failed for %s: %s', carrier.name, error)
                continue
            for picking in pickings:
                info = results.get(picking.id)
                if info:
                    picking.write({'parcel_status': info.get('status') or picking.parcel_status,
                                   'parcel_delivered_date': info.get('delivered_date') or False})

    @api.model
    def _cron_parcel_update_tracking(self):
        since = fields.Datetime.now() - timedelta(days=TRACK_DAYS)
        self.search([
            ('state', '=', 'done'), ('carrier_id.ltl_parcel', '=', True),
            ('carrier_tracking_ref', '!=', False), ('parcel_delivered_date', '=', False),
            ('date_done', '>=', since),
        ])._parcel_update_tracking()


class StockPackageType(models.Model):
    _inherit = 'stock.package.type'

    @api.model
    def _ltl_parcel_box_vals(self):
        """Our standard parcel box: 20 x 12 x 12 in, up to 50 lb, a box on LTL shipments.
        A package type for a carrier connection (UPS) holds its sizes as the connection
        sends them, in inches; without one, sizes are in this database's length unit."""
        template = self.env['product.template']
        weight_uom = template._get_weight_uom_id_from_ir_config_parameter()
        vals = {
            'name': PARCEL_BOX_NAME,
            'ltl_unit_type': 'box',
            'max_weight': round(self.env.ref('uom.product_uom_lb')._compute_quantity(50, weight_uom, round=False), 2),
        }
        carrier_types = dict(self._fields['package_carrier_type'].selection) \
            if 'package_carrier_type' in self._fields else {}
        carrier_type = next((t for t in ('ups_rest', 'ups') if t in carrier_types), False)
        if carrier_type:
            vals.update({'package_carrier_type': carrier_type, 'shipper_package_code': UPS_CUSTOMER_PACKAGE,
                         'packaging_length': 20.0, 'width': 12.0, 'height': 12.0})
        else:
            inch = self.env.ref('uom.product_uom_inch')
            length_uom = template._get_length_uom_id_from_ir_config_parameter()
            vals.update({key: float_round(inch._compute_quantity(value, length_uom, round=False), 4)
                         for key, value in (('packaging_length', 20), ('width', 12), ('height', 12))})
        return vals

    @api.model
    def _ltl_ensure_parcel_box(self):
        """Create our parcel box once; never changed afterwards (staff may edit it)."""
        if self.search_count([('name', '=', PARCEL_BOX_NAME)]):
            return
        self.create(self._ltl_parcel_box_vals())
