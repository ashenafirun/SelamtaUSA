"""Adyen chargeback (dispute) webhook parsing and Selamta's chargeback-fee rule.

Pure Python (no Odoo imports) so it can be unit tested on its own.

The fee rule, as Selamta decided it on 2026-11-02:
1. First chargeback in 12 months: no fee; the customer is told the next one carries it.
2. Second and later within 12 months: the chargeback fee every time.
3. No fee when the return looks like a processing error (duplicate entry and the like).
4. One fee per incident: chargebacks for the same customer within a few days of each other
   (one bank-account problem bouncing several payments) count as one.
5. From the third incident in 12 months, ACH is turned off for the customer.
"""
from datetime import date, timedelta

# Events this module acts on. Everything else on the webhook is ignored.
NOTICE = 'NOTIFICATION_OF_CHARGEBACK'   # the return has started; no money moved yet
CHARGEBACK = 'CHARGEBACK'               # Adyen took the money back
REVIEW_EVENTS = (
    'SECOND_CHARGEBACK',
    'CHARGEBACK_REVERSED',
    'PREARBITRATION_WON',
    'PREARBITRATION_LOST',
)
DISPUTE_EVENTS = (NOTICE, CHARGEBACK) + REVIEW_EVENTS

WINDOW_DAYS = 365       # "in the last 12 months"
INCIDENT_GAP_DAYS = 3   # chargebacks this close together are one incident
ACH_OFF_FROM = 3        # incident number from which ACH is turned off
FEE_FROM = 2            # incident number from which the fee is charged

# NACHA return codes, in the words a customer understands.
ACH_REASONS = {
    'R01': 'insufficient funds',
    'R02': 'account closed',
    'R03': 'no account / unable to locate the account',
    'R04': 'invalid account number',
    'R05': 'unauthorized debit to a consumer account',
    'R06': 'returned at the request of our bank',
    'R07': 'authorization revoked by the account holder',
    'R08': 'payment stopped by the account holder',
    'R09': 'uncollected funds',
    'R10': 'the account holder says the payment was not authorized',
    'R11': 'the account holder says the debit does not match what was authorized',
    'R12': 'account sold to another bank',
    'R13': 'invalid bank routing number',
    'R14': 'account holder deceased',
    'R15': 'beneficiary deceased',
    'R16': 'account frozen',
    'R17': 'file record edit criteria',
    'R20': 'account does not allow debits',
    'R23': 'credit refused by the receiver',
    'R24': 'duplicate entry',
    'R29': 'the company says the payment was not authorized',
}
# Returns that point at a processing mistake rather than at the customer: never charge a fee.
PROCESSING_ERROR_CODES = {'R24', '12.5', '12.6', '12.6.1', '12.6.2', '12.7', '4834'}


def _text(value):
    return value.strip() if isinstance(value, str) else ''


def is_test_item(item):
    """Adyen's "Test configuration" button sends sample events with merchantReference testMerchantRef1."""
    return _text(item.get('merchantReference')).lower().startswith('testmerchantref')


def parse_item(item):
    """Read one NotificationRequestItem of a dispute event.

    :return: dict, or None when the event is not a dispute event.
    Amount is returned in minor units (Adyen sends 125455 for 1,254.55 USD); the caller divides by the
    currency's decimals.
    """
    event = _text(item.get('eventCode'))
    if event not in DISPUTE_EVENTS or is_test_item(item):
        return None
    extra = item.get('additionalData') or {}
    amount = item.get('amount') or {}
    try:
        value = int(amount.get('value') or 0)
    except (TypeError, ValueError):
        value = 0
    dispute_ref = _text(item.get('pspReference'))
    # For dispute events, originalReference is the payment that was disputed; pspReference is the
    # dispute itself. Fall back to pspReference when Adyen leaves originalReference out.
    original_ref = _text(item.get('originalReference')) or dispute_ref
    event_date = _text(item.get('eventDate'))[:10]
    return {
        'event_code': event,
        'dispute_reference': dispute_ref,
        'psp_reference': original_ref,
        'merchant_reference': _text(item.get('merchantReference')),
        'payment_method': _text(item.get('paymentMethod')),
        'currency': _text(amount.get('currency')).upper(),
        'value_minor': value,
        'event_date': event_date if len(event_date) == 10 else '',
        'reason_code': _text(extra.get('chargebackReasonCode')),
        'reason_text': _text(item.get('reason')),
        'success': _text(item.get('success')).lower() != 'false',
    }


def reason_label(code, text=''):
    """Plain-language reason, e.g. 'insufficient funds (R01)'."""
    code = (code or '').strip().upper()
    words = ACH_REASONS.get(code)
    if not words:
        text = (text or '').strip().rstrip('.')
        # Adyen's reason field is sometimes just the code again; ignore that.
        if text and text.upper() != code and '://' not in text:
            words = text if text[:2].isupper() else text[:1].lower() + text[1:]
    if words and code:
        return '%s (%s)' % (words, code)
    return words or (code and 'return code %s' % code) or ''


def is_processing_error(code):
    return (code or '').strip().upper() in PROCESSING_ERROR_CODES


def _to_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def incident_position(earlier_dates, this_date):
    """Where this chargeback falls among the customer's chargeback incidents of the last 12 months.

    :param earlier_dates: dates of the customer's *other* chargebacks (any order, any age).
    :param this_date: date of this chargeback.
    :return: (incident_number, same_incident) — incident_number counts this one's incident
             (1 = first incident in 12 months); same_incident is True when another chargeback
             within INCIDENT_GAP_DAYS already started this incident.
    """
    this_date = _to_date(this_date)
    start = this_date - timedelta(days=WINDOW_DAYS)
    gap = timedelta(days=INCIDENT_GAP_DAYS)
    dates = sorted(d for d in map(_to_date, earlier_dates) if start < d <= this_date)
    same_incident = any(this_date - d <= gap for d in dates)
    # Group the earlier ones into incidents: a new incident starts after a quiet gap.
    incidents = 0
    last = None
    for d in dates:
        if last is None or d - last > gap:
            incidents += 1
        last = d
    number = incidents if same_incident else incidents + 1
    return max(number, 1), same_incident


def fee_decision(incident_number, same_incident, reason_code=''):
    """Return one of: 'charged', 'waived_first', 'same_incident', 'processing_error'."""
    if is_processing_error(reason_code):
        return 'processing_error'
    if same_incident:
        return 'same_incident'
    if incident_number >= FEE_FROM:
        return 'charged'
    return 'waived_first'


def turn_off_ach(incident_number):
    return incident_number >= ACH_OFF_FROM
