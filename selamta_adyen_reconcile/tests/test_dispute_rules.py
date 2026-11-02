from datetime import date

from odoo.tests import BaseCase, tagged

from ..tools import dispute_rules as dr


def item(event='CHARGEBACK', **extra):
    values = {
        'eventCode': event,
        'pspReference': 'DISPUTE0000000001',
        'originalReference': 'PAYMENT000000001',
        'merchantReference': 'INV/1',
        'paymentMethod': 'ach',
        'amount': {'currency': 'USD', 'value': 125455},
        'eventDate': '2030-01-02T10:21:00-05:00',
        'reason': 'Insufficient Funds',
        'success': 'true',
        'additionalData': {'chargebackReasonCode': 'R01'},
    }
    values.update(extra)
    return values


@tagged('post_install', '-at_install')
class TestDisputeRules(BaseCase):

    def test_parse_chargeback(self):
        data = dr.parse_item(item())
        self.assertEqual(data['event_code'], 'CHARGEBACK')
        self.assertEqual(data['psp_reference'], 'PAYMENT000000001')  # the payment, not the dispute
        self.assertEqual(data['dispute_reference'], 'DISPUTE0000000001')
        self.assertEqual(data['value_minor'], 125455)
        self.assertEqual(data['currency'], 'USD')
        self.assertEqual(data['event_date'], '2030-01-02')
        self.assertEqual(data['reason_code'], 'R01')

    def test_parse_falls_back_to_psp_reference(self):
        data = dr.parse_item(item(originalReference=''))
        self.assertEqual(data['psp_reference'], 'DISPUTE0000000001')

    def test_parse_ignores_other_events_and_adyen_tests(self):
        self.assertIsNone(dr.parse_item(item('AUTHORISATION')))
        self.assertIsNone(dr.parse_item(item('REPORT_AVAILABLE')))
        self.assertIsNone(dr.parse_item(item(merchantReference='testMerchantRef1')))
        self.assertIsNotNone(dr.parse_item(item(dr.NOTICE)))

    def test_reason_label(self):
        self.assertEqual(dr.reason_label('R01'), 'insufficient funds (R01)')
        self.assertEqual(dr.reason_label('r08'), 'payment stopped by the account holder (R08)')
        self.assertEqual(dr.reason_label('10.4', 'Other Fraud-Card Absent Environment'),
                         'other Fraud-Card Absent Environment (10.4)')
        self.assertEqual(dr.reason_label('R99'), 'return code R99')
        self.assertEqual(dr.reason_label('', ''), '')

    def test_first_chargeback_is_waived(self):
        number, same = dr.incident_position([], date(2030, 6, 1))
        self.assertEqual((number, same), (1, False))
        self.assertEqual(dr.fee_decision(number, same, 'R01'), 'waived_first')
        self.assertFalse(dr.turn_off_ach(number))

    def test_second_incident_is_charged(self):
        number, same = dr.incident_position([date(2030, 3, 1)], date(2030, 6, 1))
        self.assertEqual((number, same), (2, False))
        self.assertEqual(dr.fee_decision(number, same, 'R01'), 'charged')
        self.assertFalse(dr.turn_off_ach(number))

    def test_third_incident_turns_off_ach(self):
        number, same = dr.incident_position([date(2030, 1, 5), date(2030, 3, 1)], date(2030, 6, 1))
        self.assertEqual(number, 3)
        self.assertEqual(dr.fee_decision(number, same, 'R01'), 'charged')
        self.assertTrue(dr.turn_off_ach(number))

    def test_same_incident_counts_once(self):
        # Three payments bouncing over two days are one incident: only one fee, and it is the first.
        first, same = dr.incident_position([], date(2030, 6, 16))
        self.assertEqual((first, same), (1, False))
        second, same = dr.incident_position([date(2030, 6, 16)], date(2030, 6, 17))
        self.assertEqual((second, same), (1, True))
        self.assertEqual(dr.fee_decision(second, same, 'R01'), 'same_incident')
        third, same = dr.incident_position([date(2030, 6, 16), date(2030, 6, 17)], date(2030, 6, 17))
        self.assertEqual((third, same), (1, True))

    def test_only_last_twelve_months_count(self):
        number, same = dr.incident_position([date(2029, 5, 1), date(2029, 5, 31)], date(2030, 6, 1))
        self.assertEqual((number, same), (1, False))

    def test_processing_error_never_charged(self):
        number, same = dr.incident_position([date(2030, 3, 1)], date(2030, 6, 1))
        self.assertEqual(dr.fee_decision(number, same, 'R24'), 'processing_error')
