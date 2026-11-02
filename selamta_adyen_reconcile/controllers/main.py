import json
import logging

from odoo import http
from odoo.http import request

from ..tools import settlement_csv

_logger = logging.getLogger(__name__)


class AdyenReportWebhook(http.Controller):

    @http.route('/selamta_adyen/report_webhook', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def report_webhook(self, **kwargs):
        """Adyen "Report available" webhook. Records the report; the cron downloads and books it."""
        params = request.env['ir.config_parameter'].sudo()
        hmac_key = params.get_param('selamta_adyen_reconcile.hmac_key')
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return request.make_response('invalid payload', status=400)
        if not hmac_key:
            _logger.warning('Adyen report webhook received but no HMAC key is configured; ignored.')
            return request.make_response('not configured', status=403)

        Settlement = request.env['selamta.adyen.settlement'].sudo()
        for wrapper in payload.get('notificationItems') or []:
            item = wrapper.get('NotificationRequestItem') or {}
            if not settlement_csv.hmac_is_valid(item, hmac_key):
                _logger.warning('Adyen report webhook with an invalid HMAC signature; rejected.')
                return request.make_response('invalid signature', status=401)
            if item.get('eventCode') != 'REPORT_AVAILABLE':
                continue
            filename = item.get('pspReference') or ''
            if settlement_csv.batch_number_from_filename(filename):
                Settlement._register_report(filename, item.get('reason') or '')
        return request.make_response('[accepted]')
