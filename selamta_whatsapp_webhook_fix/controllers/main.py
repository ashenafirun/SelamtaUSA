import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.whatsapp.controller.main import Webhook

_logger = logging.getLogger(__name__)


def _standard_phone_number_id(value):
    """Mirror the lookup done by the standard controller."""
    return (value.get('metadata') or {}).get('phone_number_id') or \
        (value.get('whatsapp_business_api_data') or {}).get('phone_number_id')


def _find_payload(node, depth=0):
    """Return the first dict that carries 'messages' or 'statuses' lists."""
    if depth > 6:
        return None
    if isinstance(node, dict):
        if isinstance(node.get('messages'), list) or isinstance(node.get('statuses'), list):
            return node
        for child in node.values():
            found = _find_payload(child, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_payload(child, depth + 1)
            if found:
                return found
    return None


class SelamtaWhatsAppWebhook(Webhook):

    @http.route()
    def webhookpost(self):
        # Standard processing first. It raises Forbidden on a bad signature,
        # so everything below only runs for verified Meta webhooks.
        result = super().webhookpost()
        try:
            self._selamta_process_skipped_changes()
        except Exception:
            _logger.exception("Selamta WhatsApp webhook fallback failed")
        return result

    def _selamta_process_skipped_changes(self):
        data = json.loads(request.httprequest.data)
        for entry in data.get('entry', []):
            account = request.env['whatsapp.account'].sudo().search(
                [('account_uid', '=', entry.get('id'))], limit=1)
            if not account:
                continue
            for change in entry.get('changes', []):
                value = change.get('value') or {}
                if _standard_phone_number_id(value):
                    continue  # handled by the standard controller
                if change.get('field') != 'messages':
                    continue
                payload = _find_payload(value)
                if not payload:
                    _logger.info("Selamta WhatsApp: unhandled 'messages' webhook payload: %s",
                                 json.dumps(change)[:4000])
                    continue
                _logger.info("Selamta WhatsApp: processing webhook without metadata.phone_number_id "
                             "(keys: %s)", sorted(value.keys()))
                if payload.get('statuses'):
                    request.env['whatsapp.message']._process_statuses(payload)
                if payload.get('messages'):
                    account._process_messages(payload)
