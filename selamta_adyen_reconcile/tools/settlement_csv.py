"""Parse and prove an Adyen "Settlement details" report (settlement_detail_report_batch_N.csv).

Pure Python on purpose (no Odoo imports) so it can be unit tested on its own.
Amounts are Decimal throughout; the caller converts at the ORM boundary.
"""
import base64
import binascii
import csv
import hashlib
import hmac
import io
import re
from decimal import Decimal

# Row types this module knows how to book. Anything else stops the batch for review.
SUPPORTED_TYPES = {
    'Settled',
    'Refunded',
    'Chargeback',
    'Fee',
    'MerchantPayout',
    'InvoiceDeduction',
    'DepositCorrection',
}

REQUIRED_COLUMNS = (
    'Psp Reference', 'Merchant Reference', 'Type', 'Modification Reference',
    'Gross Debit (GC)', 'Gross Credit (GC)', 'Net Debit (NC)', 'Net Credit (NC)',
    'Batch Number', 'Creation Date',
)

FILENAME_RE = re.compile(r'^settlement_detail_report_batch_(\d+)\.csv$')
PAYOUT_REF_RE = re.compile(r'\b(TX\w+?XT)\b')
ZERO = Decimal('0')


class SettlementFormatError(ValueError):
    """The file is not a settlement details report this module can read."""


def _dec(value):
    value = (value or '').strip()
    return Decimal(value) if value else ZERO


def batch_number_from_filename(filename):
    match = FILENAME_RE.match(filename or '')
    return int(match.group(1)) if match else None


def parse(text):
    """Return the report rows as a list of dicts with Decimal amounts."""
    if isinstance(text, bytes):
        text = text.decode('utf-8-sig')
    text = text.lstrip('﻿')
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SettlementFormatError('Missing columns: %s' % ', '.join(missing))
    rows = []
    for raw in reader:
        if not (raw.get('Type') or '').strip():
            continue
        gross_debit = _dec(raw['Gross Debit (GC)'])
        gross_credit = _dec(raw['Gross Credit (GC)'])
        net_debit = _dec(raw['Net Debit (NC)'])
        net_credit = _dec(raw['Net Credit (NC)'])
        row_type = raw['Type'].strip()
        if row_type == 'Settled':
            cost = gross_credit - net_credit
        elif row_type in ('Refunded', 'Chargeback'):
            cost = net_debit - gross_debit
        else:
            cost = ZERO
        rows.append({
            'type': row_type,
            'psp_reference': (raw['Psp Reference'] or '').strip(),
            'merchant_reference': (raw['Merchant Reference'] or '').strip(),
            'modification_reference': (raw['Modification Reference'] or '').strip(),
            'modification_merchant_reference': (raw.get('Modification Merchant Reference') or '').strip(),
            'payment_method': (raw.get('Payment Method') or '').strip(),
            'creation_date': (raw['Creation Date'] or '').strip(),
            'batch_number': (raw['Batch Number'] or '').strip(),
            'gross_debit': gross_debit,
            'gross_credit': gross_credit,
            'net_debit': net_debit,
            'net_credit': net_credit,
            'cost': cost,
        })
    if not rows:
        raise SettlementFormatError('The report has no rows.')
    return rows


def summarize(rows):
    """Totals, the proof and anything that needs a person, for one report."""
    batches = {r['batch_number'] for r in rows if r['batch_number']}
    payouts = [r for r in rows if r['type'] == 'MerchantPayout']
    summary = {
        'batch_number': int(batches.pop()) if len(batches) == 1 else None,
        'mixed_batches': len(batches) > 0,
        'payout': None,
        'payout_reference': '',
        'payout_date': '',
        'sales': ZERO,
        'settled_count': 0,
        'settled_cost': ZERO,
        'refunds': ZERO,
        'refund_count': 0,
        'refund_cost': ZERO,
        'chargebacks': ZERO,
        'chargeback_count': 0,
        'chargeback_fees': ZERO,
        'daily_fees': ZERO,
        'invoice_deductions': ZERO,
        'invoice_deduction_refs': [],
        'deposit_withheld': ZERO,
        'deposit_returned': ZERO,
        'unsupported_types': sorted({r['type'] for r in rows if r['type'] not in SUPPORTED_TYPES}),
        'problems': [],
    }
    if len(payouts) == 1:
        payout = payouts[0]
        summary['payout'] = payout['net_debit'] - payout['net_credit']
        match = PAYOUT_REF_RE.search(payout['modification_reference'])
        summary['payout_reference'] = match.group(1) if match else ''
        summary['payout_date'] = payout['creation_date'][:10]
    elif not payouts:
        summary['problems'].append(
            'No MerchantPayout row: Adyen paid nothing out for this batch '
            '(the balance was carried to another batch).')
    else:
        summary['problems'].append('More than one MerchantPayout row.')

    net_total = ZERO
    for r in rows:
        if r['type'] == 'MerchantPayout':
            continue
        net_total += r['net_credit'] - r['net_debit']
        if r['type'] == 'Settled':
            summary['sales'] += r['gross_credit']
            summary['settled_count'] += 1
            summary['settled_cost'] += r['cost']
        elif r['type'] == 'Refunded':
            summary['refunds'] += r['gross_debit']
            summary['refund_count'] += 1
            summary['refund_cost'] += r['cost']
        elif r['type'] == 'Chargeback':
            summary['chargebacks'] += r['gross_debit']
            summary['chargeback_count'] += 1
            summary['chargeback_fees'] += r['cost']
        elif r['type'] == 'Fee':
            summary['daily_fees'] += r['net_debit'] - r['net_credit']
        elif r['type'] == 'InvoiceDeduction':
            summary['invoice_deductions'] += r['net_debit'] - r['net_credit']
            ref = re.search(r'Invoice (\S+)', r['modification_reference'])
            summary['invoice_deduction_refs'].append(ref.group(1) if ref else r['modification_reference'])
        elif r['type'] == 'DepositCorrection':
            summary['deposit_withheld'] += r['net_debit']
            summary['deposit_returned'] += r['net_credit']

    summary['total_cost'] = (summary['settled_cost'] + summary['refund_cost']
                             + summary['chargeback_fees'] + summary['daily_fees'])
    summary['net_total'] = net_total
    if summary['payout'] is not None:
        summary['proof_difference'] = net_total - summary['payout']
        if summary['proof_difference'] != ZERO:
            summary['problems'].append(
                'The report does not prove: rows net to %s but the payout is %s.'
                % (net_total, summary['payout']))
    else:
        summary['proof_difference'] = None
    if summary['unsupported_types']:
        summary['problems'].append(
            'Row types this module does not book automatically: %s.'
            % ', '.join(summary['unsupported_types']))
    if summary['batch_number'] is None:
        summary['problems'].append('The report does not belong to exactly one batch.')
    return summary


def hmac_signature(item, hex_key):
    """Adyen standard-webhook HMAC (SHA-256, base64) for one NotificationRequestItem."""
    amount = item.get('amount') or {}
    payload = ':'.join([
        str(item.get('pspReference') or ''),
        str(item.get('originalReference') or ''),
        str(item.get('merchantAccountCode') or ''),
        str(item.get('merchantReference') or ''),
        str(amount.get('value', '')),
        str(amount.get('currency') or ''),
        str(item.get('eventCode') or ''),
        str(item.get('success') or ''),
    ])
    digest = hmac.new(binascii.a2b_hex(hex_key.strip()), payload.encode('utf-8'), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def hmac_is_valid(item, hex_key):
    received = ((item.get('additionalData') or {}).get('hmacSignature') or '').strip()
    if not received or not hex_key:
        return False
    try:
        expected = hmac_signature(item, hex_key)
    except (binascii.Error, ValueError):
        return False
    return hmac.compare_digest(expected, received)
