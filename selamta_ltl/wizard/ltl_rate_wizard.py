# -*- coding: utf-8 -*-
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LtlRateWizard(models.TransientModel):
    """Rate shop: rates from every carrier with a connection, plus any quote staff got by
    phone or on a carrier website, side by side."""
    _name = 'selamta.ltl.rate.wizard'
    _description = 'LTL rate shop'

    shipment_id = fields.Many2one('selamta.ltl.shipment', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='shipment_id.currency_id')
    line_ids = fields.One2many('selamta.ltl.rate.wizard.line', 'wizard_id', 'Rates')
    message = fields.Text(readonly=True)

    def _fetch_rates(self):
        self.ensure_one()
        shipment = self.shipment_id
        carriers = self.env['delivery.carrier'].search([
            ('ltl_enabled', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', shipment.company_id.id),
        ]).filtered(lambda c: c.ltl_can('rate'))
        lines = []
        for carrier in carriers:
            try:
                rates = carrier.ltl_rate(shipment) or []
            except Exception as error:  # one carrier failing must not hide the others
                _logger.warning('LTL rate failed for %s: %s', carrier.name, error)
                lines.append({'carrier_id': carrier.id, 'source': 'api', 'error': str(error)[:250]})
                continue
            for rate in rates:
                lines.append({
                    'carrier_id': carrier.id,
                    'source': 'api',
                    'service': rate.get('service') or False,
                    'total': rate.get('total') or 0.0,
                    'transit_days': rate.get('transit_days') or 0,
                    'quote_number': rate.get('quote_number') or False,
                    'expires': rate.get('expires') or False,
                    'rate_json': json.dumps(rate, default=str),
                })
        self.line_ids = [(5, 0, 0)] + [(0, 0, vals) for vals in lines]
        if not carriers:
            self.message = _(
                'No carrier is connected yet. Get quotes on the carrier websites or by phone '
                'and add them below to compare.')
        else:
            self.message = False
        return True

    def action_refresh(self):
        self._fetch_rates()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class LtlRateWizardLine(models.TransientModel):
    _name = 'selamta.ltl.rate.wizard.line'
    _description = 'LTL rate'
    _order = 'error desc, total, transit_days'

    wizard_id = fields.Many2one('selamta.ltl.rate.wizard', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    carrier_id = fields.Many2one(
        'delivery.carrier', 'Carrier', required=True, domain=[('ltl_enabled', '=', True)])
    source = fields.Selection(
        [('api', 'Carrier connection'), ('website', 'Carrier website'), ('phone', 'Phone / email')],
        'From', required=True, default='website')
    service = fields.Char()
    total = fields.Monetary()
    transit_days = fields.Integer('Transit days')
    quote_number = fields.Char('Quote number')
    expires = fields.Date('Quote expires')
    error = fields.Char(readonly=True)
    rate_json = fields.Text(readonly=True)

    def _rate(self):
        self.ensure_one()
        rate = json.loads(self.rate_json) if self.rate_json else {}
        rate.update({
            'total': self.total,
            'service': self.service or rate.get('service'),
            'transit_days': self.transit_days,
            'quote_number': self.quote_number or False,
            'expires': self.expires or False,
        })
        return rate

    def action_choose(self):
        """Save this rate as the shipment's quote; book it when the carrier is connected."""
        self.ensure_one()
        if self.error:
            raise UserError(_('This carrier did not return a rate.'))
        if self.total <= 0:
            raise UserError(_('Enter the quoted total first.'))
        shipment = self.wizard_id.shipment_id
        rate = self._rate()
        shipment._apply_quote(rate, self.carrier_id, self.source)
        if self.source == 'api' and self.carrier_id.ltl_can('book'):
            result = self.carrier_id.ltl_book(shipment, rate) or {}
            shipment._apply_booking(result)
        else:
            shipment.message_post(body=_(
                'Quote saved: %(carrier)s %(total)s. Book it with the carrier, then enter the '
                'PRO and click Confirm booking.',
                carrier=self.carrier_id.name, total=self.total))
        return {'type': 'ir.actions.act_window_close'}
