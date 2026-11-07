# -*- coding: utf-8 -*-
import io
import logging
import re

from odoo import _, api, fields, models
from odoo.tools import format_amount
from odoo.tools.pdf import PdfFileReader

from .ltl_common import MIN_REF_DIGITS, digits_only, match_strategies

_logger = logging.getLogger(__name__)

BILL_TYPES = ('in_invoice', 'in_refund')

# "PRO 624464699", "BOL# 60115773611", "Pro Number: 476-594871", "PRO WD6073938"
INVOICE_NUMBER_RE = re.compile(
    r'(?<![A-Za-z])(PRO|BOL)(?![A-Za-z])[\s#:.]*(?:(?:number|num|no)\b\.?[\s#:.]*)?'
    r'([A-Z]{0,3}\d[\d\-]*\d)', re.IGNORECASE)
MAX_PDF_PAGES = 5


def invoice_pdf_numbers(pdf_bytes):
    """PRO and BOL numbers printed on a carrier invoice PDF, as [(kind, digits)], PROs first,
    each once. Reads the text layer of the first pages (a scanned invoice gives nothing)."""
    reader = PdfFileReader(io.BytesIO(pdf_bytes), strict=False)
    text = '\n'.join(
        (getattr(page, 'extract_text', None) or page.extractText)() or ''
        for page in list(reader.pages)[:MAX_PDF_PAGES])
    found = []
    for kind, number in INVOICE_NUMBER_RE.findall(text):
        digits = digits_only(number)
        entry = (kind.upper(), digits)
        if len(digits) >= MIN_REF_DIGITS and entry not in found:
            found.append(entry)
    return sorted(found, key=lambda entry: entry[0] != 'PRO')


class AccountMove(models.Model):
    _inherit = 'account.move'

    ltl_shipment_ids = fields.Many2many(
        'selamta.ltl.shipment', 'selamta_ltl_shipment_move_rel', 'move_id', 'shipment_id',
        'LTL shipments', copy=False)
    ltl_vendor = fields.Boolean(compute='_compute_ltl_vendor')
    ltl_quoted_amount = fields.Monetary('Quoted (LTL)', compute='_compute_ltl_variance')
    ltl_variance = fields.Monetary(
        'Over / under quote', compute='_compute_ltl_variance',
        help='This bill\'s total minus the quoted total of the LTL shipments it pays for.')
    ltl_match_note = fields.Char('LTL match', copy=False, readonly=True)
    ltl_invoice_refs = fields.Char(
        'PRO / BOL on the invoice', copy=False, readonly=True,
        help='PRO and BOL numbers read from the bill\'s PDF, used to find the shipment when the '
             'bill reference is not one of our numbers (Priority1 invoices).')
    ltl_invoice_refs_attachment_id = fields.Many2one(
        'ir.attachment', copy=False, readonly=True, ondelete='set null')

    @api.depends('move_type', 'commercial_partner_id')
    def _compute_ltl_vendor(self):
        vendors = self._ltl_vendors()
        for move in self:
            move.ltl_vendor = move.move_type in BILL_TYPES and move.commercial_partner_id in vendors

    @api.depends('amount_total', 'move_type', 'ltl_shipment_ids.quoted_amount')
    def _compute_ltl_variance(self):
        for move in self:
            quoted = sum(move.ltl_shipment_ids.mapped('quoted_amount'))
            move.ltl_quoted_amount = quoted
            sign = -1.0 if move.move_type == 'in_refund' else 1.0
            move.ltl_variance = sign * move.amount_total - quoted if move.ltl_shipment_ids and quoted else 0.0

    @api.model
    def _ltl_vendors(self):
        carriers = self.env['delivery.carrier'].sudo().search(
            [('ltl_enabled', '=', True), ('ltl_vendor_id', '!=', False)])
        return carriers.mapped('ltl_vendor_id.commercial_partner_id')

    # ------------------------------------------------------------------ matching

    def _ltl_match_fields(self):
        """Shipment fields to compare this bill's reference with, in order, based on how
        this vendor's carriers bill ('pro' -> PRO, 'bol' -> our BOL number)."""
        self.ensure_one()
        modes = self._ltl_vendor_modes()
        fields_to_try = []
        if 'pro' in modes:
            fields_to_try.append('pro_digits')
        if 'bol' in modes:
            fields_to_try.append('bol_digits')
        return fields_to_try

    def _ltl_search_number(self, field_name, digits, where):
        """Try one number against one shipment field with the matching rules.

        Returns (shipments, note): one shipment when a rule finds exactly one; none with a
        note when a rule finds several (left for a person) or nothing matches (note False)."""
        Shipment = self.env['selamta.ltl.shipment']
        label_field = _('PRO') if field_name == 'pro_digits' else _('BOL number')
        base = [('vendor_id', '=', self.commercial_partner_id.id), ('state', '!=', 'cancel')]
        for label, operator, value in match_strategies(digits):
            found = Shipment.search(base + [(field_name, operator, value)], order='id')
            if len(found) == 1:
                return found, _('Matched on %(field)s%(where)s (%(rule)s).',
                                field=label_field, where=where, rule=label)
            if len(found) > 1:
                return Shipment, _(
                    'Several shipments match on %(field)s%(where)s (%(rule)s): %(names)s. Link the right one by hand.',
                    field=label_field, where=where, rule=label, names=', '.join(found.mapped('name')))
        return Shipment, False

    def _ltl_find_shipments(self):
        """Find the shipment this bill pays for. Returns (shipments, note).

        First the bill reference (for vendors that bill on our PRO or BOL number), then the
        PRO and BOL printed on the bill's PDF (Priority1 bills on its own invoice number but
        prints both). Numbers are reduced to digits, then tried in strict order: exact, a
        check digit on either side, a leading 1 on either side. The first rule that finds
        exactly one shipment wins; if a rule finds several, it stops there and leaves the
        bill for a person. Never matched on amount: the amount is what is being checked.
        """
        self.ensure_one()
        Shipment = self.env['selamta.ltl.shipment']
        note = False
        ref_fields = self._ltl_match_fields()
        if ref_fields:
            ref = digits_only(self.ref)
            if not match_strategies(ref):
                note = _('No usable number in the bill reference.')
            else:
                for field_name in ref_fields:
                    found, found_note = self._ltl_search_number(field_name, ref, '')
                    if found or found_note:
                        return found, found_note
                note = _('No shipment from this vendor with a matching number.')
        numbers = self._ltl_invoice_numbers()
        for kind, digits in numbers:
            field_name = 'pro_digits' if kind == 'PRO' else 'bol_digits'
            found, found_note = self._ltl_search_number(field_name, digits, _(' printed on the invoice'))
            if found or found_note:
                return found, found_note
        if numbers:
            return Shipment, _('No shipment from this vendor with the %s printed on the invoice.',
                               ', '.join('%s %s' % number for number in numbers))
        if not ref_fields:
            return Shipment, _('No PRO or BOL number found on the invoice PDF.')
        return Shipment, note

    def _ltl_invoice_numbers(self):
        """[('PRO', digits), ('BOL', digits)...] printed on the bill's PDF, PRO first.

        Read once per PDF and kept on the bill (the daily run would otherwise read every
        unmatched bill again)."""
        self.ensure_one()
        attachment = self.message_main_attachment_id
        if not attachment or attachment.mimetype != 'application/pdf':
            return []
        if self.ltl_invoice_refs_attachment_id != attachment:
            numbers = []
            try:
                numbers = invoice_pdf_numbers(attachment.raw)
            except Exception as error:  # an unreadable PDF must not stop matching or posting
                _logger.info('Could not read PRO/BOL numbers from %s: %s', attachment.name, error)
            self.write({
                'ltl_invoice_refs': ', '.join('%s %s' % number for number in numbers) or '-',
                'ltl_invoice_refs_attachment_id': attachment.id,
            })
        return [tuple(part.split(' ', 1)) for part in (self.ltl_invoice_refs or '').split(', ')
                if ' ' in part]

    def _ltl_auto_match(self):
        """Match LTL carrier bills that are not linked yet. Returns the bills matched."""
        matched = self.browse()
        for move in self.filtered(lambda m: m.move_type in BILL_TYPES and m.state != 'cancel'
                                  and not m.ltl_shipment_ids and m.ltl_vendor):
            if all(mode == 'manual' for mode in move._ltl_vendor_modes()):
                move.ltl_match_note = _('This vendor\'s bills are linked by hand.')
                continue
            shipments, note = move._ltl_find_shipments()
            move.ltl_match_note = note
            if shipments:
                move.ltl_shipment_ids = [(4, shipment.id) for shipment in shipments]
                move._ltl_post_match_message(shipments, note)
                matched |= move
        return matched

    def _ltl_vendor_modes(self):
        self.ensure_one()
        carriers = self.env['delivery.carrier'].sudo().search([
            ('ltl_enabled', '=', True),
            ('ltl_vendor_id.commercial_partner_id', '=', self.commercial_partner_id.id),
        ])
        return carriers.mapped('ltl_match_on') or ['pro']

    def _ltl_post_match_message(self, shipments, note):
        self.ensure_one()
        for shipment in shipments:
            body = _(
                '%(note)s Bill %(bill)s, shipment %(shipment)s (PRO %(pro)s): quoted %(quoted)s, '
                'billed %(billed)s, difference %(variance)s.',
                note=note, bill=self.ref or self.name, shipment=shipment.name,
                pro=shipment.pro_number or '-',
                quoted=format_amount(self.env, shipment.quoted_amount, shipment.currency_id),
                billed=format_amount(self.env, shipment.billed_amount, shipment.currency_id),
                variance=format_amount(self.env, shipment.variance, shipment.currency_id))
            shipment.message_post(body=body)
            self.message_post(body=body)

    def action_ltl_match(self):
        """Button: try to match the selected carrier bills now."""
        matched = self._ltl_auto_match()
        unmatched = self - matched
        message = _('%(n)s bill(s) matched.', n=len(matched))
        if len(self) == 1 and unmatched:
            message = self.ltl_match_note or _('No shipment found.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'success' if matched else 'warning',
                'sticky': False,
            },
        }

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        bills = posted.filtered(lambda m: m.move_type in BILL_TYPES)
        if bills:
            try:
                with self.env.cr.savepoint():
                    bills._ltl_auto_match()
            except Exception:  # matching must never block posting a bill
                _logger.exception('LTL bill matching failed')
        return posted

    @api.model
    def _cron_ltl_match_bills(self):
        since = fields.Date.subtract(fields.Date.context_today(self), days=180)
        vendors = self._ltl_vendors()
        if not vendors:
            return
        bills = self.search([
            ('move_type', 'in', BILL_TYPES),
            ('state', '!=', 'cancel'),
            ('commercial_partner_id', 'in', vendors.ids),
            ('ltl_shipment_ids', '=', False),
            '|', ('ref', '!=', False), ('message_main_attachment_id', '!=', False),
            ('invoice_date', '>=', since),
        ])
        bills._ltl_auto_match()
