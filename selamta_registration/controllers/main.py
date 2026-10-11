# -*- coding: utf-8 -*-
import gzip
import json
import logging
import re
import threading
import time
from collections import defaultdict, deque

import requests

from odoo import http
from odoo.http import request
from odoo.tools.misc import file_path

from odoo.addons.website.controllers.form import WebsiteForm

_logger = logging.getLogger(__name__)

PLACES_AUTOCOMPLETE_URL = 'https://places.googleapis.com/v1/places:autocomplete'
PLACES_DETAILS_URL = 'https://places.googleapis.com/v1/places/%s'
GOOGLE_TIMEOUT = 4
# Bias suggestions toward metro Atlanta (most customers), without excluding the rest of the U.S.
LOCATION_BIAS = {'circle': {'center': {'latitude': 33.749, 'longitude': -84.388}, 'radius': 50000.0}}
ADDRESS_TYPES = ['street_address', 'premise', 'subpremise']
PLACE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{10,300}$')

# Simple per-IP limit for the address endpoints (each call can cost a Google request).
RATE_LIMIT = 80          # requests ...
RATE_WINDOW = 600        # ... per 10 minutes per visitor IP
_rate_lock = threading.Lock()
_rate_hits = defaultdict(deque)

_zip_lock = threading.Lock()
_zip_data = None


def _zip_table():
    global _zip_data
    if _zip_data is None:
        with _zip_lock:
            if _zip_data is None:
                path = file_path('selamta_registration/data/us_zip_cities.json.gz')
                with gzip.open(path, 'rt', encoding='utf-8') as f:
                    _zip_data = json.load(f)
    return _zip_data


def _rate_limited():
    ip = request.httprequest.remote_addr or '?'
    now = time.monotonic()
    with _rate_lock:
        hits = _rate_hits[ip]
        while hits and now - hits[0] > RATE_WINDOW:
            hits.popleft()
        if len(hits) >= RATE_LIMIT:
            return True
        hits.append(now)
        if len(_rate_hits) > 5000:  # keep memory bounded
            for key in [k for k, v in _rate_hits.items() if not v]:
                del _rate_hits[key]
    return False


class SelamtaRegistration(http.Controller):

    def _places_key(self):
        return request.env['ir.config_parameter'].sudo().get_param(
            'selamta_registration.google_places_api_key') or ''

    def _us_state(self, code):
        if not code:
            return request.env['res.country.state']
        return request.env['res.country.state'].sudo().search([
            ('country_id.code', '=', 'US'), ('code', '=', code.upper()),
        ], limit=1)

    @http.route('/selamta/registration/config', type='json', auth='public', website=True, sitemap=False)
    def registration_config(self, **kwargs):
        return {'address_enabled': bool(self._places_key())}

    @http.route('/selamta/registration/zip', type='json', auth='public', website=True, sitemap=False)
    def registration_zip(self, zip_code=None, **kwargs):
        digits = re.sub(r'\D', '', zip_code or '')[:5]
        if len(digits) != 5:
            return {}
        entry = _zip_table().get(digits)
        if not entry:
            return {}
        city, state_code = entry.split('|', 1)
        state = self._us_state(state_code)
        return {
            'zip': digits,
            'city': city,
            'state_code': state_code,
            'state_id': state.id or False,
        }

    @http.route('/selamta/registration/address', type='json', auth='public', website=True, sitemap=False)
    def registration_address(self, query=None, session_token=None, **kwargs):
        key = self._places_key()
        if not key:
            return {'enabled': False, 'suggestions': []}
        query = (query or '').strip()[:200]
        if len(query) < 4 or _rate_limited():
            return {'enabled': True, 'suggestions': []}
        body = {
            'input': query,
            'includedRegionCodes': ['us'],
            'regionCode': 'us',
            'languageCode': 'en',
            'includedPrimaryTypes': ADDRESS_TYPES,
            'locationBias': LOCATION_BIAS,
        }
        if session_token:
            body['sessionToken'] = str(session_token)[:100]
        data = self._google_autocomplete(key, body)
        if data is None:
            # e.g. a type filter Google no longer accepts: try once without it
            body.pop('includedPrimaryTypes', None)
            data = self._google_autocomplete(key, body) or {}
        suggestions = []
        for item in data.get('suggestions') or []:
            prediction = item.get('placePrediction') or {}
            place_id = prediction.get('placeId')
            if not place_id:
                continue
            structured = prediction.get('structuredFormat') or {}
            main = (structured.get('mainText') or {}).get('text') or (prediction.get('text') or {}).get('text') or ''
            secondary = (structured.get('secondaryText') or {}).get('text') or ''
            secondary = re.sub(r',?\s*USA$', '', secondary)
            suggestions.append({'place_id': place_id, 'main': main, 'secondary': secondary})
            if len(suggestions) >= 5:
                break
        return {'enabled': True, 'suggestions': suggestions}

    def _google_autocomplete(self, key, body):
        """Return the JSON answer, or None when Google rejected the request."""
        try:
            response = requests.post(
                PLACES_AUTOCOMPLETE_URL, json=body, timeout=GOOGLE_TIMEOUT,
                headers={'X-Goog-Api-Key': key},
            )
        except requests.RequestException as e:
            _logger.warning('Google Places autocomplete failed: %s', e)
            return {}
        if response.status_code != 200:
            _logger.warning('Google Places autocomplete error %s: %s',
                            response.status_code, response.text[:500])
            return None if response.status_code == 400 else {}
        try:
            return response.json()
        except ValueError:
            return {}

    @http.route('/selamta/registration/address/details', type='json', auth='public', website=True, sitemap=False)
    def registration_address_details(self, place_id=None, session_token=None, query=None, **kwargs):
        key = self._places_key()
        if not key or not place_id or not PLACE_ID_RE.match(place_id) or _rate_limited():
            return {}
        params = {'languageCode': 'en', 'regionCode': 'us'}
        if session_token:
            params['sessionToken'] = str(session_token)[:100]
        try:
            response = requests.get(
                PLACES_DETAILS_URL % place_id, params=params, timeout=GOOGLE_TIMEOUT,
                headers={'X-Goog-Api-Key': key, 'X-Goog-FieldMask': 'addressComponents,formattedAddress'},
            )
        except requests.RequestException as e:
            _logger.warning('Google Places details failed: %s', e)
            return {}
        if response.status_code != 200:
            _logger.warning('Google Places details error %s: %s',
                            response.status_code, response.text[:500])
            return {}
        try:
            data = response.json()
        except ValueError:
            return {}
        return self._address_from_components(data.get('addressComponents') or [], query or '')

    def _address_from_components(self, components, query=''):
        def find(*types, short=False):
            for wanted in types:
                for comp in components:
                    if wanted in (comp.get('types') or []):
                        return (comp.get('shortText') if short else comp.get('longText')) or ''
            return ''

        country = find('country', short=True)
        if country and country.upper() != 'US':
            return {}
        number = find('street_number')
        route = find('route', short=True)
        if not number:
            # Google sometimes drops the house number it doesn't know: keep what was typed.
            match = re.match(r'\s*(\d+[A-Za-z]?)\b', query)
            number = match.group(1) if match else ''
        unit = find('subpremise')
        if unit and not re.match(r'^(#|apt|unit|ste|suite|bldg)', unit, re.I):
            unit = '#' + unit
        state = self._us_state(find('administrative_area_level_1', short=True))
        return {
            'street': ' '.join(filter(None, [number, route])),
            'street2': unit,
            'city': find('locality', 'postal_town', 'sublocality_level_1', 'sublocality',
                         'neighborhood', 'administrative_area_level_3'),
            'zip': find('postal_code'),
            'state_id': state.id or False,
            'state_code': state.code or '',
        }


class SelamtaWebsiteForm(WebsiteForm):

    def _handle_website_form(self, model_name, **kwargs):
        result = super()._handle_website_form(model_name, **kwargs)
        if model_name != 'res.partner':
            return result
        try:
            record_id = json.loads(result).get('id')
        except (TypeError, ValueError, AttributeError):
            record_id = None
        if record_id:
            partner = request.env['res.partner'].sudo().browse(record_id)
            if partner.exists() and partner.selamta_application_state == 'new':
                try:
                    with request.env.cr.savepoint():
                        partner._selamta_notify_new_application()
                except Exception:
                    # never lose the application because the notification failed
                    _logger.exception('Could not send the wholesale application notification for %s', record_id)
        return result
