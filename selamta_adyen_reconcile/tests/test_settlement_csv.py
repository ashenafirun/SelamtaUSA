from decimal import Decimal

from odoo.tests import BaseCase, tagged

from ..tools import settlement_csv as sc

HEADER = (
    'Company Account,Merchant Account,Psp Reference,Merchant Reference,Payment Method,Creation Date,TimeZone,Type,'
    'Modification Reference,Gross Currency,Gross Debit (GC),Gross Credit (GC),Exchange Rate,Net Currency,'
    'Net Debit (NC),Net Credit (NC),Commission (NC),Markup (NC),Scheme Fees (NC),Interchange (NC),'
    'Payment Method Variant,Modification Merchant Reference,Batch Number\n'
)


def row(psp, ref, rtype, mod, gd='', gc='', nd='', nc='', comm='', batch='900', date='2030-01-02 10:00:00'):
    return '%s\n' % ','.join([
        'TestCo', 'TestCoECOM', psp, ref, 'ach' if psp else '', date, 'EDT', rtype, mod,
        'USD' if psp else '', gd, gc, '1' if psp else '', 'USD', nd, nc, comm, '', '', '', '', '', batch,
    ])


def report(*rows):
    return HEADER + ''.join(rows)


SETTLED_1 = row('PSPAAAA1', 'INV/1', 'Settled', 'M1', gc='100.00', nc='99.73', comm='0.27')
SETTLED_2 = row('PSPAAAA2', 'INV/2', 'Settled', 'M2', gc='50.00', nc='49.73', comm='0.27')
CHARGEBACK_2 = row('PSPAAAA2', 'INV/2', 'Chargeback', 'M2', gd='50.00', nd='68.64', comm='18.64')
FEE = row('', '', 'Fee', 'Transaction Fees January 02 2030', nd='0.24')


def payout(amount, batch='900'):
    return row('', '', 'MerchantPayout', '"TX12345678900XT batch %s, TestCoECOM"' % batch, nd=amount, batch=batch)


@tagged('post_install', '-at_install')
class TestSettlementCsv(BaseCase):

    def test_clean_batch_proves(self):
        s = sc.summarize(sc.parse(report(SETTLED_1, SETTLED_2, FEE, payout('149.22'))))
        self.assertEqual(s['problems'], [])
        self.assertEqual(s['batch_number'], 900)
        self.assertEqual(s['payout'], Decimal('149.22'))
        self.assertEqual(s['payout_reference'], 'TX12345678900XT')
        self.assertEqual(s['sales'], Decimal('150.00'))
        self.assertEqual(s['total_cost'], Decimal('0.78'))

    def test_same_batch_chargeback_proves(self):
        # Settle 50.00 and charge it back in the same batch: payout is 100.00 net of fees and the 18.64 fee.
        s = sc.summarize(sc.parse(report(SETTLED_1, SETTLED_2, CHARGEBACK_2, FEE, payout('80.58'))))
        self.assertEqual(s['problems'], [])
        self.assertEqual(s['chargebacks'], Decimal('50.00'))
        self.assertEqual(s['chargeback_fees'], Decimal('18.64'))
        self.assertEqual(s['total_cost'], Decimal('19.42'))

    def test_payout_mismatch_is_flagged(self):
        s = sc.summarize(sc.parse(report(SETTLED_1, FEE, payout('99.50'))))
        self.assertTrue(any('does not prove' in p for p in s['problems']))

    def test_balance_transfer_and_no_payout_are_flagged(self):
        transfer = row('', '', 'Balancetransfer', 'Balancetransfer', nc='68.64')
        s = sc.summarize(sc.parse(report(CHARGEBACK_2, transfer)))
        self.assertIn('Balancetransfer', s['unsupported_types'])
        self.assertTrue(any('No MerchantPayout' in p for p in s['problems']))

    def test_deposit_correction(self):
        withheld = row('', '', 'DepositCorrection', 'Deposit Correction', nd='40.00')
        s = sc.summarize(sc.parse(report(SETTLED_1, withheld, payout('59.73'))))
        self.assertEqual(s['problems'], [])
        self.assertEqual(s['deposit_withheld'], Decimal('40.00'))

    def test_filename(self):
        self.assertEqual(sc.batch_number_from_filename('settlement_detail_report_batch_532.csv'), 532)
        self.assertIsNone(sc.batch_number_from_filename('payments_accounting_report.csv'))

    def test_hmac(self):
        key = '44782DEF547AAA06C910C43932B1EB0C71FC68D9D0C057550C48EC2ACF6BA056'
        item = {
            'pspReference': 'settlement_detail_report_batch_900.csv', 'merchantAccountCode': 'TestCoECOM',
            'eventCode': 'REPORT_AVAILABLE', 'success': 'true', 'amount': {'value': 0, 'currency': 'EUR'},
        }
        item['additionalData'] = {'hmacSignature': sc.hmac_signature(item, key)}
        self.assertTrue(sc.hmac_is_valid(item, key))
        item['pspReference'] = 'settlement_detail_report_batch_901.csv'
        self.assertFalse(sc.hmac_is_valid(item, key))
        self.assertFalse(sc.hmac_is_valid(item, ''))
