import json
import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.fields import Command
from odoo.tools.misc import format_amount

from ..tools import dispute_rules

_logger = logging.getLogger(__name__)

# A chargeback found only in a settlement report (no webhook) older than this is not booked
# automatically: re-uploading an old report must never email customers about old returns.
REPORT_MAX_AGE_DAYS = 45


class AdyenDisputeException(Exception):
    """Something a person has to look at; nothing is booked."""


EVENT_SELECTION = [
    (dispute_rules.NOTICE, 'Return started'),
    (dispute_rules.CHARGEBACK, 'Chargeback (money taken)'),
    ('SECOND_CHARGEBACK', 'Second chargeback'),
    ('CHARGEBACK_REVERSED', 'Chargeback reversed'),
    ('PREARBITRATION_WON', 'Pre-arbitration won'),
    ('PREARBITRATION_LOST', 'Pre-arbitration lost'),
]

FEE_SELECTION = [
    ('waived_first', 'Waived: first in 12 months'),
    ('charged', 'Charged'),
    ('same_incident', 'Not charged: same incident as an earlier chargeback'),
    ('processing_error', 'Not charged: processing error'),
    ('no_product', 'Not charged: no fee product in settings'),
]


def _ordinal(number):
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return '%s%s' % (number, suffix)


class AdyenDispute(models.Model):
    _name = 'selamta.adyen.dispute'
    _description = 'Adyen Chargeback'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'event_date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True,
                                  default=lambda self: self.env.company.currency_id)
    event_code = fields.Selection(EVENT_SELECTION, string='Event', required=True, readonly=True)
    source = fields.Selection([('webhook', 'Adyen webhook'), ('report', 'Settlement report')],
                              default='webhook', required=True, readonly=True)
    state = fields.Selection([
        ('new', 'New'),
        ('done', 'Done'),
        ('exception', 'Needs review'),
    ], default='new', required=True, readonly=True, tracking=True, index=True)
    exception_reason = fields.Text(readonly=True)

    psp_reference = fields.Char('Payment reference', readonly=True, index=True,
                                help='Adyen PSP reference of the payment that came back.')
    dispute_reference = fields.Char(readonly=True)
    merchant_reference = fields.Char(readonly=True)
    payment_method = fields.Char(readonly=True)
    event_date = fields.Date(readonly=True)
    amount = fields.Monetary(readonly=True)
    reason_code = fields.Char(readonly=True)
    reason = fields.Char(readonly=True)

    partner_id = fields.Many2one('res.partner', 'Customer', readonly=True, index=True)
    original_payment_id = fields.Many2one('account.payment', 'Returned payment', readonly=True)
    chargeback_payment_id = fields.Many2one('account.payment', 'Chargeback payment', readonly=True)
    invoice_ids = fields.Many2many('account.move', 'selamta_adyen_dispute_invoice_rel', 'dispute_id', 'move_id',
                                   string='Invoices reopened', readonly=True)
    invoice_names = fields.Char(compute='_compute_invoice_names')
    reopened_amount = fields.Monetary('Due again on those invoices', readonly=True)
    incident_number = fields.Integer('Chargeback incident in 12 months', readonly=True,
                                     help='1 = first chargeback incident in the last 12 months.')
    fee_status = fields.Selection(FEE_SELECTION, string='Chargeback fee', readonly=True)
    fee_amount = fields.Monetary(readonly=True)
    fee_invoice_id = fields.Many2one('account.move', 'Fee invoice', readonly=True)
    ach_turned_off = fields.Boolean('ACH turned off', readonly=True)
    ach_kept_on = fields.Boolean('ACH kept on (customer exempt)', readonly=True,
                                 help='The rule would have turned ACH off, but the customer is set to keep it.')
    customer_emailed = fields.Boolean(readonly=True)
    payload = fields.Text('Adyen message', readonly=True)

    @api.depends('event_code', 'psp_reference')
    def _compute_name(self):
        labels = dict(EVENT_SELECTION)
        for dispute in self:
            dispute.name = '%s %s' % (labels.get(dispute.event_code, ''), dispute.psp_reference or '')

    @api.depends('invoice_ids')
    def _compute_invoice_names(self):
        for dispute in self:
            dispute.invoice_names = ', '.join(dispute.invoice_ids.sorted('name').mapped('name'))

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------
    @api.model
    def _register_event(self, item):
        """Called by the webhook for each dispute event: store it; the cron books it within minutes."""
        data = dispute_rules.parse_item(item)
        if not data or not data['psp_reference']:
            return self.browse()
        company = self.env.company
        domain = [('company_id', '=', company.id), ('event_code', '=', data['event_code']),
                  ('psp_reference', '=', data['psp_reference'])]
        if data['event_code'] != dispute_rules.CHARGEBACK:
            domain.append(('dispute_reference', '=', data['dispute_reference']))
        existing = self.search(domain, limit=1)
        reason = dispute_rules.reason_label(data['reason_code'], data['reason_text'])
        if existing:
            # Adyen resends events; a chargeback first seen in a report gets the reason from the webhook.
            if not existing.reason and reason:
                existing.write({'reason': reason, 'reason_code': data['reason_code']})
            return existing
        currency = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', data['currency'])], limit=1) or company.currency_id
        stored = dict(item)
        stored['additionalData'] = {k: v for k, v in (item.get('additionalData') or {}).items()
                                    if k != 'hmacSignature'}
        dispute = self.create({
            'company_id': company.id,
            'currency_id': currency.id,
            'event_code': data['event_code'],
            'source': 'webhook',
            'psp_reference': data['psp_reference'],
            'dispute_reference': data['dispute_reference'],
            'merchant_reference': data['merchant_reference'],
            'payment_method': data['payment_method'],
            'event_date': data['event_date'] or fields.Date.context_today(self),
            'amount': currency.round(data['value_minor'] / (10 ** currency.decimal_places)),
            'reason_code': data['reason_code'],
            'reason': reason,
            'payload': json.dumps(stored, indent=1)[:20000],
        })
        self.env.ref('selamta_adyen_reconcile.ir_cron_adyen_dispute')._trigger()
        return dispute

    @api.model
    def _register_report_chargeback(self, line):
        """A Chargeback row of a settlement report with no chargeback payment in Odoo yet."""
        company = line.settlement_id.company_id
        existing = self.search([('company_id', '=', company.id), ('event_code', '=', dispute_rules.CHARGEBACK),
                                ('psp_reference', '=', line.psp_reference)], limit=1)
        if existing:
            return existing
        return self.create({
            'company_id': company.id,
            'currency_id': line.currency_id.id or company.currency_id.id,
            'event_code': dispute_rules.CHARGEBACK,
            'source': 'report',
            'psp_reference': line.psp_reference,
            'dispute_reference': line.modification_reference,
            'merchant_reference': line.merchant_reference,
            'payment_method': line.payment_method,
            'event_date': (line.creation_date or '')[:10] or fields.Date.context_today(self),
            'amount': line.gross_amount,
        })

    def action_process(self):
        for dispute in self:
            dispute._run()
        return True

    def action_retry(self):
        self.filtered(lambda d: d.state == 'exception').write({'state': 'new', 'exception_reason': False})
        return self.action_process()

    @api.model
    def _cron_process(self):
        params = self.env['ir.config_parameter'].sudo()
        if params.get_param('selamta_adyen_reconcile.auto_process') != 'True':
            return
        for dispute in self.search([('state', '=', 'new')], order='event_date, id'):
            dispute._run()
            self.env.cr.commit()

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def _run(self):
        self.ensure_one()
        if self.state != 'new':
            return
        try:
            config = self._config()
            with self.env.cr.savepoint():
                if self.event_code == dispute_rules.CHARGEBACK:
                    self._handle_chargeback(config)
                elif self.event_code == dispute_rules.NOTICE:
                    self._handle_notice(config)
                else:
                    self._handle_review_event(config)
        except AdyenDisputeException as error:
            self._flag(str(error))
        except Exception as error:  # noqa: BLE001 - surface anything unexpected for review
            _logger.exception('Adyen chargeback %s failed', self.name)
            self._flag(_('Unexpected error: %s', error))

    def _config(self):
        company = self.company_id
        journal = company.adyen_rec_journal_id
        if not journal:
            raise AdyenDisputeException(_('No Adyen bank journal in Accounting settings.'))
        manual = journal.outbound_payment_method_line_ids.filtered(lambda l: l.code == 'manual')
        line = manual.filtered(lambda l: l.name == l.payment_method_id.name)[:1] or manual[:1]
        if not line:
            raise AdyenDisputeException(_('Journal %s has no manual outgoing payment method.', journal.name))
        return {
            'journal': journal,
            'method_line': line,
            'fee_product': company.adyen_rec_cb_fee_product_id,
        }

    def _flag(self, reason):
        self.write({'state': 'exception', 'exception_reason': reason})
        self.message_post(body=_('Needs review: %s', reason))
        user = self.company_id.adyen_rec_review_user_id
        if user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_('Adyen chargeback needs review'),
                note=reason,
            )
        self._notify_office('review')

    # Finding things -----------------------------------------------------
    def _find_original_payment(self, journal, required=True):
        Payment = self.env['account.payment']
        psp = self.psp_reference
        if not psp:
            if required:
                raise AdyenDisputeException(_('Adyen sent no payment reference.'))
            return Payment
        domain = [('journal_id', '=', journal.id), ('payment_type', '=', 'inbound'),
                  ('state', 'not in', ('draft', 'canceled'))]
        payments = Payment.search(domain + [('payment_transaction_id.provider_reference', '=', psp)])
        if not payments:
            payments = Payment.search(domain + [('memo', 'ilike', psp)])
        if len(payments) > 1:
            if required:
                raise AdyenDisputeException(_('More than one Odoo payment has Adyen reference %(psp)s: %(pays)s.',
                                              psp=psp, pays=', '.join(payments.mapped('name'))))
            return Payment
        if not payments and required:
            raise AdyenDisputeException(_(
                'No Odoo payment found for Adyen reference %(psp)s (%(ref)s, %(amount)s).',
                psp=psp, ref=self.merchant_reference or '-',
                amount=format_amount(self.env, self.amount, self.currency_id)))
        return payments

    def _existing_chargeback_payment(self, journal):
        if not self.psp_reference:
            return self.env['account.payment']
        return self.env['account.payment'].search([
            ('journal_id', '=', journal.id),
            ('payment_type', '=', 'outbound'),
            ('state', '!=', 'canceled'),
            ('memo', 'ilike', self.psp_reference),
        ], limit=1)

    def _guess_customer(self):
        """Best-effort customer for a notification when the booking stopped early."""
        if self.partner_id:
            return self.partner_id
        journal = self.company_id.adyen_rec_journal_id
        if not journal:
            return self.env['res.partner']
        return self._find_original_payment(journal, required=False).partner_id.commercial_partner_id

    @staticmethod
    def _is_ach(payment, adyen_method):
        method = payment.payment_transaction_id.payment_method_id
        codes = {method.code, method.primary_payment_method_id.code}
        return 'ach_direct_debit' in codes or (not method and (adyen_method or '').lower() == 'ach')

    # Event handlers -------------------------------------------------------
    def _handle_notice(self, config):
        payment = self._find_original_payment(config['journal'], required=False)
        if payment:
            self.write({
                'original_payment_id': payment.id,
                'partner_id': payment.partner_id.commercial_partner_id.id,
                'invoice_ids': [Command.set(payment.reconciled_invoice_ids.ids)],
            })
        already = self.search_count([('company_id', '=', self.company_id.id), ('id', '!=', self.id),
                                     ('event_code', '=', dispute_rules.CHARGEBACK),
                                     ('psp_reference', '=', self.psp_reference)])
        self.state = 'done'
        if already:
            self.message_post(body=_('The chargeback itself already arrived; no separate heads-up sent.'))
            return
        self._notify_office('notice')

    def _handle_review_event(self, config):
        payment = self._find_original_payment(config['journal'], required=False)
        if payment:
            self.write({'original_payment_id': payment.id,
                        'partner_id': payment.partner_id.commercial_partner_id.id})
        amount = format_amount(self.env, self.amount, self.currency_id)
        messages = {
            'CHARGEBACK_REVERSED': _('Adyen reversed the chargeback on payment %(psp)s (%(amount)s): the money comes '
                                     'back in a payout. Reverse the chargeback booking by hand.'),
            'PREARBITRATION_WON': _('Pre-arbitration won on payment %(psp)s (%(amount)s): the money comes back in a '
                                    'payout. Reverse the chargeback booking by hand.'),
            'SECOND_CHARGEBACK': _('Second chargeback on payment %(psp)s (%(amount)s). Book it by hand.'),
            'PREARBITRATION_LOST': _('Pre-arbitration lost on payment %(psp)s (%(amount)s). Check the booking by hand.'),
        }
        message = messages.get(self.event_code, _('Adyen dispute event on payment %(psp)s (%(amount)s).'))
        raise AdyenDisputeException(message % {'psp': self.psp_reference, 'amount': amount})

    def _handle_chargeback(self, config):
        journal = config['journal']
        existing = self._existing_chargeback_payment(journal)
        if existing:
            self.write({
                'chargeback_payment_id': existing.id,
                'partner_id': existing.partner_id.commercial_partner_id.id,
                'state': 'done',
            })
            self.message_post(body=_('Chargeback payment %s already exists (booked by hand); nothing else done.',
                                     existing.name))
            return
        if self.source == 'report' and self.event_date and \
                self.event_date < fields.Date.context_today(self) - timedelta(days=REPORT_MAX_AGE_DAYS):
            raise AdyenDisputeException(_(
                'Chargeback of %s found in an old settlement report; old chargebacks are not booked or emailed '
                'automatically.', self.event_date))
        if self.currency_id.is_zero(self.amount):
            raise AdyenDisputeException(_('Adyen sent a chargeback without an amount.'))

        payment = self._find_original_payment(journal)
        self.write({'original_payment_id': payment.id, 'partner_id': payment.partner_id.commercial_partner_id.id})
        if not self._is_ach(payment, self.payment_method):
            raise AdyenDisputeException(_(
                'Payment %s was not an ACH payment. Card chargebacks are not booked automatically.', payment.name))

        self._book_chargeback(payment, config)
        self._apply_fee_rule(config)
        try:
            with self.env.cr.savepoint():
                emailed = self._email_customer()
        except Exception as error:  # noqa: BLE001 - the booking stands; the office is told the email failed
            _logger.exception('Chargeback email for %s failed', self.name)
            self.message_post(body=_('The customer email could not be sent: %s', error))
            emailed = False
        self.write({'customer_emailed': emailed, 'state': 'done'})
        self._notify_office('chargeback')

    # Booking --------------------------------------------------------------
    def _book_chargeback(self, payment, config):
        """Selamta's standing rule: an outbound 'Charge Back-<PSP>' payment, the bounced payment taken off
        its invoices, and the two matched on the receivable so the invoices show as due again."""
        cur = payment.currency_id
        if cur != self.currency_id:
            raise AdyenDisputeException(_('The chargeback currency differs from payment %s.', payment.name))
        if cur.compare_amounts(payment.amount, self.amount):
            raise AdyenDisputeException(_(
                'Adyen took back %(cb)s but payment %(pay)s is %(amount)s (a partial chargeback). Book it by hand.',
                cb=format_amount(self.env, self.amount, cur), pay=payment.name,
                amount=format_amount(self.env, payment.amount, cur)))
        _liquidity, counterpart, write_offs = payment._seek_for_lines()
        if write_offs:
            raise AdyenDisputeException(_('Payment %s has fee or write-off lines. Book it by hand.', payment.name))
        if len(counterpart) != 1 or counterpart.account_id.account_type != 'asset_receivable' \
                or cur.compare_amounts(-counterpart.amount_currency, self.amount):
            raise AdyenDisputeException(_(
                'Payment %s does not have one receivable line for the full amount. Book it by hand.', payment.name))
        matched = counterpart.matched_debit_ids.debit_move_id | counterpart.matched_credit_ids.credit_move_id
        not_invoices = matched.move_id.filtered(lambda m: not m.is_invoice(include_receipts=True))
        if not_invoices:
            raise AdyenDisputeException(_(
                'Payment %(pay)s is matched with %(what)s, not only invoices (already reversed?). Check it by hand.',
                pay=payment.name, what=', '.join(not_invoices.mapped('name'))))
        invoices = matched.move_id

        chargeback = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'customer',
            'partner_id': payment.partner_id.id,
            'amount': self.amount,
            'currency_id': cur.id,
            'journal_id': config['journal'].id,
            'payment_method_line_id': config['method_line'].id,
            'destination_account_id': counterpart.account_id.id,
            'date': self.event_date or fields.Date.context_today(self),
            'memo': 'Charge Back-%s' % self.psp_reference,
            'selamta_dispute_id': self.id,
        })
        chargeback.action_post()
        if matched:
            counterpart.remove_move_reconcile()
        cb_line = chargeback.move_id.line_ids.filtered(lambda l: l.account_id == counterpart.account_id)
        (cb_line | counterpart).reconcile()
        if not (cb_line.reconciled and counterpart.reconciled):
            raise AdyenDisputeException(_('The chargeback could not be matched with payment %s.', payment.name))
        self.write({
            'chargeback_payment_id': chargeback.id,
            'invoice_ids': [Command.set(invoices.ids)],
            'reopened_amount': sum(invoices.mapped('amount_residual')),
        })
        self.message_post(body=_(
            'Chargeback payment %(cb)s booked; payment %(pay)s taken off %(inv)s, which are due again.',
            cb=chargeback.name, pay=payment.name, inv=self.invoice_names or _('no invoice')))

    def _apply_fee_rule(self, config):
        customer = self.partner_id
        others = self.env['account.payment'].search([
            ('partner_id', 'child_of', customer.id),
            ('payment_type', '=', 'outbound'),
            ('partner_type', '=', 'customer'),
            ('state', 'not in', ('draft', 'canceled')),
            ('id', '!=', self.chargeback_payment_id.id),
            '|', ('memo', 'ilike', 'charge back'), ('memo', 'ilike', 'chargeback'),
        ])
        when = self.event_date or fields.Date.context_today(self)
        number, same = dispute_rules.incident_position(others.mapped('date'), when)
        status = dispute_rules.fee_decision(number, same, self.reason_code)
        product = config['fee_product']
        vals = {'incident_number': number, 'fee_status': status,
                'fee_amount': product.lst_price if product else 0.0}
        if status in ('charged', 'waived_first') and not product:
            vals['fee_status'] = 'no_product'
        elif status == 'charged':
            vals['fee_invoice_id'] = self._create_fee_invoice(product).id
        if dispute_rules.turn_off_ach(number) and not customer.selamta_ach_blocked \
                and not customer.selamta_ach_auto_off:
            vals['ach_kept_on'] = True
        elif dispute_rules.turn_off_ach(number) and not customer.selamta_ach_blocked:
            customer.write({
                'selamta_ach_blocked': True,
                'selamta_ach_blocked_note': _('Turned off automatically on %(day)s: %(nth)s chargeback incident '
                                              'in 12 months (Adyen %(psp)s).',
                                              day=fields.Date.context_today(self), nth=_ordinal(number),
                                              psp=self.psp_reference),
            })
            vals['ach_turned_off'] = True
        self.write(vals)

    def _create_fee_invoice(self, product):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_line_ids': [
                Command.create({'product_id': product.id, 'quantity': 1, 'price_unit': product.lst_price}),
                Command.create({'display_type': 'line_note',
                                'name': _('Chargeback payment fee for reference %s', self.psp_reference)}),
            ],
        })
        invoice.action_post()
        return invoice

    # Telling people -------------------------------------------------------
    def _email_customer(self):
        """Send the returned-payment email from the chargeback payment, where the office sends it today."""
        chargeback = self.chargeback_payment_id
        customer = self.partner_id
        template = self.env.ref('selamta_adyen_reconcile.mail_template_chargeback_notice', raise_if_not_found=False)
        if not (template and customer.email and chargeback):
            return False
        template = template.with_context(lang=customer.lang or self.env.lang)
        subject = template._render_field('subject', chargeback.ids)[chargeback.id]
        # body_html is rendered with QWeb and post-processed (links) by its field definition.
        body = template._render_field('body_html', chargeback.ids)[chargeback.id]
        company = self.company_id
        chargeback.with_context(mail_post_autofollow=False).message_post(
            body=body,
            subject=subject,
            partner_ids=customer.ids,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=company.partner_id.id,
            email_from=company.email_formatted or None,
            email_layout_xmlid='mail.mail_notification_light',
        )
        return True

    def _customer_phones(self, customer):
        phones = []
        for number in (customer.phone, customer.mobile):
            if number and number not in phones:
                phones.append(number)
        for contact in customer.child_ids.filtered(lambda c: c.type == 'contact' and (c.phone or c.mobile))[:3]:
            number = contact.phone or contact.mobile
            if number not in phones:
                phones.append('%s %s' % (contact.name, number))
        return phones

    @staticmethod
    def _link(record, label=None):
        return Markup('<a href="/web#model=%s&amp;id=%s&amp;view_type=form">%s</a>') % (
            record._name, record.id, label or record.display_name)

    def _office_body(self, kind, members):
        cur = self.currency_id
        customer = self.partner_id or self._guess_customer()
        amount = format_amount(self.env, self.amount, cur)
        who = customer.name if customer else (self.merchant_reference or _('unknown customer'))
        lines = []
        if kind == 'chargeback':
            lines.append(Markup('<b>%s</b>') % _('Chargeback: %(who)s, %(amount)s ACH payment returned',
                                                   who=who, amount=amount))
        elif kind == 'notice':
            lines.append(Markup('<b>%s</b>') % _('Return started: %(who)s, %(amount)s', who=who, amount=amount))
            lines.append(_('Adyen has not taken the money back yet; Odoo books it automatically when it does.'))
        else:
            lines.append(Markup('<b>%s</b>') % _('Chargeback needs review: %(who)s, %(amount)s',
                                                   who=who, amount=amount))
            lines.append(self.exception_reason or '')
            lines.append(_('Nothing was booked and the customer was not emailed.'))
        if self.reason:
            lines.append(_('Reason: %s', self.reason))
        phones = self._customer_phones(customer) if customer else []
        if phones:
            lines.append(Markup('%s <b>%s</b>') % (_('Call:'), ' / '.join(phones)))
        elif customer:
            lines.append(_('No phone number on file for this customer.'))
        if self.invoice_ids:
            links = Markup(', ').join(
                Markup('%s (%s)') % (self._link(inv, inv.name), format_amount(self.env, inv.amount_residual, cur))
                if kind == 'chargeback' else self._link(inv, inv.name)
                for inv in self.invoice_ids)
            label = _('Due again:') if kind == 'chargeback' else _('Invoices:')
            lines.append(Markup('%s %s') % (label, links))
        if kind == 'chargeback':
            nth = _ordinal(self.incident_number or 1)
            fee = format_amount(self.env, self.fee_amount, cur)
            fee_lines = {
                'waived_first': _('%(nth)s chargeback in 12 months: %(fee)s fee waived; the email says the next one '
                                  'carries it.', nth=nth, fee=fee),
                'charged': _('%(nth)s chargeback in 12 months: %(fee)s fee charged.', nth=nth, fee=fee),
                'same_incident': _('Same incident as a chargeback in the last few days: no extra fee.'),
                'processing_error': _('Looks like a processing error: no fee charged.'),
                'no_product': _('%(nth)s chargeback in 12 months. No fee product is set in settings, so no fee.',
                                nth=nth),
            }
            if self.fee_status in fee_lines:
                lines.append(fee_lines[self.fee_status])
            if self.fee_invoice_id:
                lines.append(Markup('%s %s. %s') % (_('Fee invoice:'), self._link(self.fee_invoice_id, self.fee_invoice_id.name),
                                                    _('Cancel it if this was our or the bank\'s mistake.')))
            if self.ach_turned_off:
                lines.append(Markup('<b>%s</b>') % _('ACH is now turned off for this customer. Turn it back on in '
                                                       'the customer\'s Chargebacks tab.'))
            elif self.ach_kept_on:
                lines.append(Markup('<b>%s</b>') % _('ACH left on: this customer is set not to lose ACH '
                                                       'automatically (Chargebacks tab).'))
            if self.customer_emailed:
                lines.append(_('Customer emailed at %s.', customer.email))
            else:
                lines.append(Markup('<b>%s</b>') % _('Customer NOT emailed (no email address on file, or the email '
                                                       'failed).'))
            if self.chargeback_payment_id:
                lines.append(Markup('%s %s') % (_('Booked:'), self._link(self.chargeback_payment_id,
                                                                         self.chargeback_payment_id.name)))
        else:
            lines.append(Markup('%s %s') % (_('Adyen reference:'), self._link(self, self.psp_reference or self.name)))
        mentions = Markup(' ').join(
            Markup('<a href="/web#model=res.partner&amp;id=%s" class="o_mail_redirect" data-oe-id="%s" '
                   'data-oe-model="res.partner" target="_blank">@%s</a>') % (p.id, p.id, p.name)
            for p in members)
        if mentions:
            lines.append(mentions)
        return Markup('<br/>').join(line for line in lines if line)

    def _notify_office(self, kind):
        """Post in the office channel and mention every member, so it lands in each person's inbox."""
        try:
            channel = self.company_id.adyen_rec_dispute_channel_id.sudo()
            if not channel:
                self.message_post(body=_('No office channel is set in Accounting settings; nobody was notified.'))
                return
            members = channel.channel_member_ids.partner_id.filtered('user_ids')
            channel.message_post(
                body=self._office_body(kind, members),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=members.ids,
            )
        except Exception:  # noqa: BLE001 - never lose the booking because a notification failed
            _logger.exception('Office notification for %s failed', self.name)
            self.message_post(body=_('The office channel notification failed; check the server log.'))
