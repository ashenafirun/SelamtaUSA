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
        measured = shipment._units_complete()
        for carrier in (carriers if measured else carriers.browse()):
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
        lines += self._parcel_lines(shipment)
        self.line_ids = [(5, 0, 0)] + [(0, 0, vals) for vals in lines]
        if not measured:
            self.message = _(
                'Only parcel quotes: measure every pallet or box (length, width, height, weight) to '
                'get LTL quotes too.')
        elif not carriers:
            self.message = _(
                'No carrier is connected yet. Get quotes on the carrier websites or by phone '
                'and add them below to compare.')
        else:
            self.message = False
        return True

    def _parcel_lines(self, shipment):
        """Parcel quotes (UPS...) for loads light enough to go by parcel. A carrier with a
        rate hook (UPS) is priced from the boxes on the shipment, one line per service;
        others through the sales orders of the shipment's deliveries."""
        limit = float(self.env['ir.config_parameter'].sudo().get_param(
            'selamta_ltl.parcel_max_weight', 300) or 0)
        if not limit or shipment.total_weight > limit:
            return []
        lines = []
        carriers = self.env['delivery.carrier'].search([
            ('ltl_parcel', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', shipment.company_id.id),
        ])
        for carrier in carriers:
            vals = {'carrier_id': carrier.id, 'source': 'api', 'parcel': True,
                    'service': _('%s (parcel)', carrier.name)}
            if carrier.ltl_can('rate'):
                try:
                    rates = carrier.ltl_rate(shipment) or []
                except Exception as error:  # a parcel quote failing must not hide the LTL quotes
                    _logger.warning('Parcel rate failed for %s: %s', carrier.name, error)
                    lines.append(dict(vals, error=str(error)[:250]))
                    continue
                for rate in rates:
                    lines.append(dict(
                        vals,
                        service=rate.get('service') or vals['service'],
                        total=rate.get('total') or 0.0,
                        transit_days=rate.get('transit_days') or 0,
                        rate_json=json.dumps(rate, default=str),
                    ))
                continue
            try:
                total, note = carrier.ltl_parcel_rate(shipment)
            except Exception as error:  # a parcel quote failing must not hide the LTL quotes
                _logger.warning('Parcel rate failed for %s: %s', carrier.name, error)
                vals['error'] = str(error)[:250]
            else:
                vals.update({'total': total, 'rate_json': json.dumps({'total': total, 'note': note})})
            lines.append(vals)
        return lines

    def _save_rate_shop(self, chosen):
        """Keep every quote of this rate shop on the shipment, the chosen one marked, so the
        choice can be reviewed later. Lines added by hand with no price yet are left out."""
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l == chosen or l.error or l.total > 0)
        self.shipment_id.write({
            'rate_ids': [(5, 0, 0)] + [(0, 0, line._saved_rate_vals(chosen)) for line in lines],
            'rates_shopped_on': fields.Datetime.now(),
            'rates_shopped_by': self.env.uid,
        })

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
    parcel = fields.Boolean(readonly=True, help='Parcel quote (UPS...): the boxes go by parcel instead of LTL.')

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

    def _saved_rate_vals(self, chosen):
        self.ensure_one()
        return {
            'chosen': self == chosen,
            'carrier_id': self.carrier_id.id,
            'source': self.source,
            'service': self.service or False,
            'total': 0.0 if self.error else self.total,
            'difference': 0.0 if self.error else self.total - chosen.total,
            'transit_days': self.transit_days,
            'quote_number': self.quote_number or False,
            'expires': self.expires or False,
            'parcel': self.parcel,
            'error': self.error or False,
        }

    def action_choose(self):
        """Save this rate as the shipment's quote; book it when the carrier is connected."""
        self.ensure_one()
        if self.error:
            raise UserError(_('This carrier did not return a rate.'))
        if self.total <= 0:
            raise UserError(_('Enter the quoted total first.'))
        shipment = self.wizard_id.shipment_id
        if shipment.state == 'booked' and shipment.parcel_shipment_number:
            raise UserError(_(
                '%s already has UPS labels. Cancel it first (that voids the labels with UPS), then '
                'reset it to not booked and choose again.', shipment.name))
        self.wizard_id._save_rate_shop(self)
        if self.parcel:
            return self._choose_parcel(shipment)
        rate = self._rate()
        shipment._apply_quote(rate, self.carrier_id, self.source)
        if self.source == 'api' and self.carrier_id.ltl_can('book'):
            shipment._check_pickup()
            result = self.carrier_id.ltl_book(shipment, rate) or {}
            shipment._apply_booking(result)
        else:
            shipment.message_post(body=_(
                'Quote saved: %(carrier)s %(total)s. Book it with the carrier, then enter the '
                'PRO and click Confirm booking.',
                carrier=self.carrier_id.name, total=self.total))
        return {'type': 'ir.actions.act_window_close'}

    def _choose_parcel(self, shipment):
        """Ship the boxes by parcel.

        With a carrier that books from the shipment (UPS), the labels are made right here:
        the carrier is asked first, and only what it returned is saved, so a refusal changes
        nothing. Otherwise the deliveries get the parcel shipping method and the LTL shipment
        is cancelled; labels are then made the standard way (put in packs, validate)."""
        self.ensure_one()
        carrier = self.carrier_id
        if carrier.ltl_can('book'):
            rate = self._rate()
            result = carrier.ltl_book(shipment, rate) or {}
            shipment._apply_quote(rate, carrier, self.source)
            shipment._apply_parcel_booking(result)
            return {'type': 'ir.actions.act_window_close'}
        pickings = shipment.picking_ids
        pickings.write({'carrier_id': self.carrier_id.id})
        shipment.message_post(body=_(
            'Going by parcel with %(carrier)s (quoted %(total)s) instead of LTL. Put the boxes in packs '
            'and validate the delivery to print the labels.', carrier=self.carrier_id.name, total=self.total))
        shipment.write({'state': 'cancel'})
        if len(pickings) == 1:
            return {'type': 'ir.actions.act_window', 'res_model': 'stock.picking', 'res_id': pickings.id,
                    'view_mode': 'form', 'target': 'current'}
        return {'type': 'ir.actions.act_window_close'}
