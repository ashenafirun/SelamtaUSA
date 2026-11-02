import logging
from urllib.parse import urlparse

import requests

from odoo import _, api, fields, models
from odoo.fields import Command
from odoo.tools import float_compare, float_is_zero

from ..tools import settlement_csv

_logger = logging.getLogger(__name__)

PARAM_PREFIX = 'selamta_adyen_reconcile.'


class AdyenSettlementException(Exception):
    """Something a person has to look at; the batch stops where it is."""


class AdyenSettlement(models.Model):
    _name = 'selamta.adyen.settlement'
    _description = 'Adyen Settlement Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'batch_number desc, id desc'

    name = fields.Char('Report', required=True, readonly=True, tracking=True)
    batch_number = fields.Integer(readonly=True, index=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection([
        ('new', 'New'),
        ('checked', 'Checked'),
        ('batched', 'Batch created, waiting for payout'),
        ('done', 'Reconciled'),
        ('exception', 'Needs review'),
    ], default='new', required=True, readonly=True, tracking=True, index=True)
    exception_reason = fields.Text(readonly=True)
    download_url = fields.Char(readonly=True)
    attachment_id = fields.Many2one('ir.attachment', readonly=True)

    payout_amount = fields.Monetary(readonly=True)
    payout_reference = fields.Char(readonly=True, help='Adyen payout id (TX...XT), also in the Chase line text.')
    payout_date = fields.Date(readonly=True)
    sales_amount = fields.Monetary(readonly=True)
    refund_amount = fields.Monetary(readonly=True)
    chargeback_amount = fields.Monetary(readonly=True)
    cost_amount = fields.Monetary('Adyen fees', readonly=True)
    invoice_deduction_amount = fields.Monetary(readonly=True)
    deposit_withheld_amount = fields.Monetary(readonly=True)
    deposit_returned_amount = fields.Monetary(readonly=True)

    line_ids = fields.One2many('selamta.adyen.settlement.line', 'settlement_id', readonly=True)
    batch_payment_id = fields.Many2one('account.batch.payment', readonly=True)
    statement_line_id = fields.Many2one('account.bank.statement.line', readonly=True)
    payout_move_id = fields.Many2one(related='statement_line_id.move_id')

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'This Adyen report is already loaded.'),
    ]

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _param(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(PARAM_PREFIX + key, default)

    def _config(self):
        company = self.company_id or self.env.company
        config = {
            'journal': company.adyen_rec_journal_id,
            'fee_account': company.adyen_rec_fee_account_id,
            'deposit_account': company.adyen_rec_deposit_account_id,
            'review_user': company.adyen_rec_review_user_id,
        }
        missing = [label for key, label in (
            ('journal', _('bank journal')),
            ('fee_account', _('Adyen fees account')),
            ('deposit_account', _('Adyen deposit account')),
        ) if not config[key]]
        if missing:
            raise AdyenSettlementException(
                _('Adyen settlement settings are incomplete (Accounting settings): %s.', ', '.join(missing)))
        if not config['journal'].suspense_account_id:
            raise AdyenSettlementException(_('The bank journal has no suspense account.'))
        return config

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------
    @api.model
    def _create_from_csv(self, filename, content, download_url=False):
        """Create (or return) the settlement for one report file."""
        existing = self.search([('name', '=', filename), ('company_id', '=', self.env.company.id)], limit=1)
        if existing:
            return existing
        settlement = self.create({
            'name': filename,
            'batch_number': settlement_csv.batch_number_from_filename(filename) or 0,
            'download_url': download_url,
        })
        if content:
            settlement._store_csv(content)
        return settlement

    @api.model
    def _register_report(self, filename, download_url):
        """Called by the webhook: remember the report and let the cron fetch and process it."""
        if not settlement_csv.batch_number_from_filename(filename):
            return self.browse()
        settlement = self._create_from_csv(filename, False, download_url=download_url)
        self.env.ref('selamta_adyen_reconcile.ir_cron_adyen_settlement')._trigger()
        return settlement

    def _store_csv(self, content):
        self.ensure_one()
        attachment = self.env['ir.attachment'].create({
            'name': self.name,
            'raw': content,
            'mimetype': 'text/csv',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.attachment_id = attachment

    def action_download(self):
        for settlement in self:
            if settlement.attachment_id:
                continue
            settlement._download()
        return True

    def _download(self):
        self.ensure_one()
        api_key = self._param('api_key')
        if not api_key:
            raise AdyenSettlementException(_('No Adyen report API key is set in Accounting settings.'))
        url = self.download_url or ''
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or not (host == 'adyen.com' or host.endswith('.adyen.com')):
            raise AdyenSettlementException(_('Refusing to download the report from %s: not an Adyen address.', url))
        response = requests.get(url, headers={'X-API-Key': api_key}, timeout=60)
        if response.status_code != 200:
            raise AdyenSettlementException(
                _('Adyen refused the report download (HTTP %s).', response.status_code))
        self._store_csv(response.content)

    def action_process(self):
        """Run every step the settlement is ready for. Safe to run again."""
        for settlement in self:
            settlement._run()
        return True

    def action_retry(self):
        self.filtered(lambda s: s.state == 'exception').write({'state': 'new', 'exception_reason': False})
        return self.action_process()

    @api.model
    def _cron_process(self):
        if self._param('auto_process') != 'True':  # unticking the setting removes the parameter
            return
        pending = self.search([('state', 'in', ('new', 'checked', 'batched'))], order='batch_number, id')
        for settlement in pending:
            settlement._run()
            self.env.cr.commit()

    # ------------------------------------------------------------------
    # The pipeline: check -> batch -> book. Each step stops on anything unusual.
    # ------------------------------------------------------------------
    def _run(self):
        self.ensure_one()
        if self.state in ('done', 'exception'):
            return
        try:
            if not self.attachment_id:
                if not self.download_url:
                    return
                self._download()
            if self.state == 'new':
                self._load_rows()  # only touches this record, so the rows stay visible on a failure
                self._handle_report_chargebacks()  # each one commits or flags on its own
                with self.env.cr.savepoint():
                    self._check()
            if self.state == 'checked':
                with self.env.cr.savepoint():
                    self._create_batch()
            if self.state == 'batched':
                with self.env.cr.savepoint():
                    self._book_payout()
        except AdyenSettlementException as error:
            self._flag(str(error))
        except Exception as error:  # noqa: BLE001 - surface anything unexpected for review
            _logger.exception('Adyen settlement %s failed', self.name)
            self._flag(_('Unexpected error: %s', error))

    def _flag(self, reason):
        self.write({'state': 'exception', 'exception_reason': reason})
        self.message_post(body=_('Stopped for review: %s', reason))
        user = self.company_id.adyen_rec_review_user_id
        if user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_('Adyen batch %s needs review', self.batch_number),
                note=reason,
            )

    # Step 1 -----------------------------------------------------------
    def _load_rows(self):
        try:
            rows = settlement_csv.parse(self.attachment_id.raw)
        except settlement_csv.SettlementFormatError as error:
            raise AdyenSettlementException(_('Not a settlement details report this module can read: %s', error))
        summary = settlement_csv.summarize(rows)
        self.line_ids.unlink()
        self.write({
            'batch_number': summary['batch_number'] or self.batch_number,
            'payout_amount': float(summary['payout'] or 0),
            'payout_reference': summary['payout_reference'],
            'payout_date': summary['payout_date'] or False,
            'sales_amount': float(summary['sales']),
            'refund_amount': float(summary['refunds']),
            'chargeback_amount': float(summary['chargebacks']),
            'cost_amount': float(summary['total_cost']),
            'invoice_deduction_amount': float(summary['invoice_deductions']),
            'deposit_withheld_amount': float(summary['deposit_withheld']),
            'deposit_returned_amount': float(summary['deposit_returned']),
            'line_ids': [Command.create(self._line_vals(row)) for row in rows],
        })
        if summary['problems']:
            raise AdyenSettlementException(' '.join(summary['problems']))
        if float_is_zero(self.payout_amount, precision_rounding=self.currency_id.rounding):
            raise AdyenSettlementException(_('The payout is zero.'))

    def _handle_report_chargebacks(self):
        """Book chargebacks that reach Odoo only through the report (the webhook missed them).

        Runs before the batch check so the chargeback payment exists when the rows are matched.
        """
        journal = self.company_id.adyen_rec_journal_id
        if not journal:
            return
        Payment = self.env['account.payment']
        Dispute = self.env['selamta.adyen.dispute']
        for line in self.line_ids.filtered(lambda l: l.row_type == 'Chargeback' and l.psp_reference):
            if Payment.search_count([('journal_id', '=', journal.id), ('payment_type', '=', 'outbound'),
                                     ('state', '!=', 'canceled'), ('memo', 'ilike', line.psp_reference)]):
                continue
            dispute = Dispute._register_report_chargeback(line)
            if dispute.state == 'new':
                dispute._run()

    def _check(self):
        self._match_lines()
        self.state = 'checked'
        self.message_post(body=_(
            'Report proves to the payout: sales %(sales)s - refunds %(ref)s - Adyen fees %(cost)s '
            '- chargebacks %(cb)s - invoices %(inv)s +/- deposit = payout %(payout)s.',
            sales=self.sales_amount, ref=self.refund_amount, cost=self.cost_amount,
            cb=self.chargeback_amount, inv=self.invoice_deduction_amount, payout=self.payout_amount))

    @staticmethod
    def _line_vals(row):
        return {
            'row_type': row['type'],
            'psp_reference': row['psp_reference'],
            'merchant_reference': row['merchant_reference'],
            'modification_reference': row['modification_reference'],
            'payment_method': row['payment_method'],
            'creation_date': row['creation_date'],
            'gross_amount': float(row['gross_credit'] or row['gross_debit']),
            'net_amount': float(row['net_credit'] - row['net_debit']),
            'cost_amount': float(row['cost']),
        }

    def _match_lines(self):
        """Find the Odoo payment behind every Settled, Refunded and Chargeback row."""
        config = self._config()
        problems = []
        used = self.env['account.payment']
        for line in self.line_ids:
            if line.row_type == 'Settled':
                payment = line._find_settled_payment(config['journal'], used)
            elif line.row_type == 'Refunded':
                payment = line._find_refund_payment(config['journal'], used)
            elif line.row_type == 'Chargeback':
                payment = line._find_chargeback_payment(config['journal'], used)
            else:
                continue
            if isinstance(payment, str):
                problems.append(payment)
                continue
            line.payment_id = payment
            used |= payment
        if problems:
            raise AdyenSettlementException('\n'.join(problems))

    # Step 2 -----------------------------------------------------------
    def _create_batch(self):
        config = self._config()
        settled = self.line_ids.filtered(lambda l: l.row_type == 'Settled')
        payments = settled.payment_id
        if not payments:
            self.state = 'batched'
            return
        cur = self.currency_id
        batches = payments.batch_payment_id
        if batches:
            # Already batched by hand (or a re-run): adopt it only if it holds exactly these payments.
            if len(batches) > 1 or set(batches.payment_ids.ids) != set(payments.ids) \
                    or any(not p.batch_payment_id for p in payments):
                raise AdyenSettlementException(_(
                    'Some of these payments are already in another batch payment (%s).',
                    ', '.join(batches.mapped('name'))))
            batch = batches
        else:
            methods = payments.payment_method_line_id.payment_method_id
            if len(methods) != 1:
                raise AdyenSettlementException(_('The payments use more than one payment method.'))
            batch = self.env['account.batch.payment'].create({
                'journal_id': config['journal'].id,
                'batch_type': 'inbound',
                'payment_method_id': methods.id,
                'date': self.payout_date or fields.Date.context_today(self),
                'payment_ids': [Command.set(payments.ids)],
            })
            batch.name = '%s Batch %s' % (batch.name, self.batch_number)
        if float_compare(batch.amount, self.sales_amount, precision_rounding=cur.rounding):
            raise AdyenSettlementException(_(
                'Batch %(batch)s totals %(amount)s but Adyen settled %(sales)s.',
                batch=batch.name, amount=batch.amount, sales=self.sales_amount))
        if self.attachment_id and not self.env['ir.attachment'].search_count([
                ('res_model', '=', 'account.batch.payment'), ('res_id', '=', batch.id),
                ('name', '=', self.name)]):
            self.attachment_id.copy({'res_model': 'account.batch.payment', 'res_id': batch.id})
        if batch.state == 'draft':
            batch.validate_batch_button()
        self.write({'batch_payment_id': batch.id, 'state': 'batched'})
        self.message_post(body=_('Batch payment %s created and validated (%s payments).',
                                 batch.name, len(payments)))

    # Step 3 -----------------------------------------------------------
    def _find_statement_line(self, journal):
        cur = self.currency_id
        candidates = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', journal.id),
            ('is_reconciled', '=', False),
            ('payment_ref', 'ilike', self.payout_reference),
        ])
        candidates = candidates.filtered(
            lambda l: not float_compare(l.amount, self.payout_amount, precision_rounding=cur.rounding))
        if len(candidates) > 1:
            raise AdyenSettlementException(_('More than one bank line matches payout %s.', self.payout_reference))
        return candidates

    def _book_payout(self):
        config = self._config()
        journal = config['journal']
        if not self.payout_reference:
            raise AdyenSettlementException(_('No payout reference in the report.'))
        st_line = self._find_statement_line(journal)
        if not st_line:
            return  # The payout has not reached the bank feed yet; the cron tries again.
        cur = self.currency_id
        move = st_line.move_id
        suspense = move.line_ids.filtered(lambda l: l.account_id == journal.suspense_account_id)
        if len(suspense) != 1 or float_compare(suspense.credit, self.payout_amount, precision_rounding=cur.rounding):
            raise AdyenSettlementException(_(
                'Bank line %s is not in its untouched state (one suspense line for the full payout).', move.name))

        new_lines, pairs = self._payout_line_plan(config)
        debit = sum(v['debit'] for v in new_lines) + self.payout_amount
        credit = sum(v['credit'] for v in new_lines)
        if float_compare(debit, credit, precision_rounding=cur.rounding):
            raise AdyenSettlementException(_(
                'The payout entry would not balance (%(debit)s / %(credit)s).', debit=debit, credit=credit))

        existing = move.line_ids
        move.button_draft()
        move.write({'line_ids': [Command.delete(suspense.id)] + [Command.create(v) for v in new_lines]})
        move.action_post()
        created = (move.line_ids - existing).sorted('id')
        if len(created) != len(new_lines):
            raise AdyenSettlementException(_('The payout entry lines could not be created as planned.'))
        for index, counterpart in pairs:
            line = created[index]
            if line.account_id != counterpart.account_id or float_compare(
                    line.balance, -counterpart.amount_residual, precision_rounding=cur.rounding):
                raise AdyenSettlementException(_(
                    'Line "%s" does not mirror its payment; nothing was matched.', line.name))
            (line | counterpart).reconcile()
        unmatched = created.filtered(lambda l: l.account_id.reconcile and not l.reconciled)
        if unmatched:
            raise AdyenSettlementException(_(
                'Some payout lines did not fully match: %s.', ', '.join(unmatched.mapped('name'))))
        move.checked = False  # leave it in To Check
        self.write({'statement_line_id': st_line.id, 'state': 'done'})
        self.message_post(body=_('Payout %(amount)s booked on %(move)s and matched; left in To Check.',
                                 amount=self.payout_amount, move=move.name))

    def _payout_line_plan(self, config):
        """Lines that replace the suspense line, plus (line index, payment line to match)."""
        cur = self.currency_id
        tx = self.payout_reference
        batch = self.batch_number
        vals, pairs = [], []
        lines = self.line_ids

        def add(values, counterpart=None):
            values.setdefault('debit', 0.0)
            values.setdefault('credit', 0.0)
            vals.append(values)
            if counterpart:
                pairs.append((len(vals) - 1, counterpart))

        settled_cost = sum(lines.filtered(lambda l: l.row_type == 'Settled').mapped('cost_amount'))
        refund_cost = sum(lines.filtered(lambda l: l.row_type == 'Refunded').mapped('cost_amount'))
        cb_lines = lines.filtered(lambda l: l.row_type == 'Chargeback')
        cb_cost = sum(cb_lines.mapped('cost_amount'))
        daily = -sum(lines.filtered(lambda l: l.row_type == 'Fee').mapped('net_amount'))
        parts = ['%s settled' % cur.round(settled_cost)]
        if refund_cost:
            parts.append('%s refund comm' % cur.round(refund_cost))
        if cb_lines:
            parts.append('%s chargeback fee%s %s' % (len(cb_lines), 's' if len(cb_lines) > 1 else '', cur.round(cb_cost)))
        if daily:
            parts.append('%s daily' % cur.round(daily))
        if not cur.is_zero(self.cost_amount):
            add({'account_id': config['fee_account'].id, 'debit': cur.round(self.cost_amount),
                 'name': 'Adyen cost of transactions batch %s (%s) - %s' % (batch, ' + '.join(parts), tx)})

        inv_lines = lines.filtered(lambda l: l.row_type == 'InvoiceDeduction')
        if inv_lines:
            add({'account_id': config['fee_account'].id, 'debit': cur.round(self.invoice_deduction_amount),
                 'name': 'Adyen invoices deducted batch %s (%s) - %s' % (
                     batch, ', '.join(inv_lines.mapped('modification_reference')), tx)})

        for line in lines.filtered(lambda l: l.row_type == 'DepositCorrection'):
            amount = cur.round(abs(line.net_amount))
            if line.net_amount < 0:
                add({'account_id': config['deposit_account'].id, 'debit': amount,
                     'name': 'Adyen adjustments batch %s - Deposit Correction %s - %s' % (batch, amount, tx)})
            else:
                add({'account_id': config['deposit_account'].id, 'credit': amount,
                     'name': 'Adyen adjustments batch %s - Deposit Correction returned %s - %s' % (batch, amount, tx)})

        for line in lines.filtered(lambda l: l.row_type in ('Chargeback', 'Refunded')):
            counterpart = line.payment_id._selamta_outstanding_line()
            add({'account_id': counterpart.account_id.id, 'partner_id': line.payment_id.partner_id.id,
                 'name': counterpart.name, 'debit': cur.round(line.gross_amount)}, counterpart)

        for line in lines.filtered(lambda l: l.row_type == 'Settled'):
            counterpart = line.payment_id._selamta_outstanding_line()
            add({'account_id': counterpart.account_id.id, 'partner_id': line.payment_id.partner_id.id,
                 'name': counterpart.name, 'credit': cur.round(line.gross_amount)}, counterpart)
        return vals, pairs


class AdyenSettlementLine(models.Model):
    _name = 'selamta.adyen.settlement.line'
    _description = 'Adyen Settlement Report Row'
    _order = 'id'

    settlement_id = fields.Many2one('selamta.adyen.settlement', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='settlement_id.currency_id')
    row_type = fields.Char('Type')
    psp_reference = fields.Char('PSP reference', index=True)
    merchant_reference = fields.Char()
    modification_reference = fields.Char()
    payment_method = fields.Char()
    creation_date = fields.Char()
    gross_amount = fields.Monetary('Gross')
    net_amount = fields.Monetary('Net', help='Positive: Adyen pays you. Negative: Adyen keeps it.')
    cost_amount = fields.Monetary('Adyen fee')
    payment_id = fields.Many2one('account.payment', readonly=True)

    def _payment_domain(self, journal, payment_type):
        return [
            ('journal_id', '=', journal.id),
            ('payment_type', '=', payment_type),
            ('state', 'not in', ('draft', 'canceled')),
        ]

    def _check_candidate(self, payment, used):
        cur = self.currency_id
        if payment in used:
            return _('Row %s: payment %s is already used by another row.', self.psp_reference, payment.name)
        if float_compare(payment.amount, self.gross_amount, precision_rounding=cur.rounding):
            return _('Row %(psp)s (%(ref)s): Adyen shows %(gross)s but payment %(pay)s is %(amount)s.',
                     psp=self.psp_reference, ref=self.merchant_reference, gross=self.gross_amount,
                     pay=payment.name, amount=payment.amount)
        line = payment._selamta_outstanding_line()
        if not line:
            return _('Row %s: payment %s has no open outstanding line (already matched elsewhere?).',
                     self.psp_reference, payment.name)
        return payment

    def _pick(self, candidates, used, what):
        candidates = candidates - used
        if not candidates:
            return False
        if len(candidates) > 1:
            # Same reference and amount twice (e.g. a customer paid an invoice twice): take the oldest one
            # dated on or before the Adyen row; anything still tied goes to review.
            row_day = (self.creation_date or '')[:10]
            dated = candidates.filtered(lambda p: not row_day or str(p.date) <= row_day).sorted(lambda p: (p.date, p.id))
            pool = dated or candidates.sorted(lambda p: (p.date, p.id))
            if len(pool) > 1 and pool[0].date == pool[1].date:
                return _('Row %s (%s): more than one %s payment fits (%s).', self.psp_reference,
                         self.merchant_reference, what, ', '.join(pool.mapped('name')))
            return pool[0]
        return candidates

    def _find_settled_payment(self, journal, used):
        Payment = self.env['account.payment']
        domain = self._payment_domain(journal, 'inbound')
        payment = Payment.search(domain + [('payment_transaction_id.provider_reference', '=', self.psp_reference)])
        if not payment:
            payment = Payment.search(domain + [('memo', 'ilike', self.psp_reference)])
        if not payment and self.merchant_reference:
            payment = Payment.search(domain + [
                '|', ('memo', '=', self.merchant_reference),
                ('memo', '=like', self.merchant_reference + ' - %'),
                ('amount', '=', self.gross_amount),
                ('is_matched', '=', False),
            ])
        picked = self._pick(payment, used, 'Adyen')
        if not picked:
            return _('Row %s (%s, %s): no Adyen payment found in Odoo.',
                     self.psp_reference, self.merchant_reference, self.gross_amount)
        if isinstance(picked, str):
            return picked
        return self._check_candidate(picked, used)

    def _find_refund_payment(self, journal, used):
        Payment = self.env['account.payment']
        domain = self._payment_domain(journal, 'outbound')
        ref = self.modification_reference
        payment = Payment.search(domain + [('payment_transaction_id.provider_reference', '=', ref)]) if ref else Payment
        if not payment and ref:
            payment = Payment.search(domain + [('memo', 'ilike', ref)])
        picked = self._pick(payment, used, 'refund')
        if not picked:
            return _('Refund %s (%s, %s): no refund payment found in Odoo.', ref, self.merchant_reference,
                     self.gross_amount)
        if isinstance(picked, str):
            return picked
        return self._check_candidate(picked, used)

    def _find_chargeback_payment(self, journal, used):
        Payment = self.env['account.payment']
        payment = Payment.search(self._payment_domain(journal, 'outbound') + [
            ('memo', 'ilike', self.psp_reference),
            ('payment_transaction_id', '=', False),
        ])
        picked = self._pick(payment, used, 'chargeback')
        if not picked:
            return _('Chargeback %s (%s, %s): no chargeback payment in Odoo. Create it (memo "Charge Back-%s") '
                     'and reverse the bounced payment off the invoice, then retry.',
                     self.psp_reference, self.merchant_reference, self.gross_amount, self.psp_reference)
        if isinstance(picked, str):
            return picked
        return self._check_candidate(picked, used)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    selamta_dispute_id = fields.Many2one('selamta.adyen.dispute', 'Adyen chargeback', readonly=True, copy=False,
                                         index='btree_not_null')

    def _selamta_outstanding_line(self):
        """The payment's open line on its outstanding receipts/payments account."""
        self.ensure_one()
        return self.move_id.line_ids.filtered(
            lambda l: l.account_id == self.outstanding_account_id and not l.reconciled
            and not l.currency_id.is_zero(l.amount_residual))[:1]
