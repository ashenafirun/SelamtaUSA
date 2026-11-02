{
    'name': 'Selamta - Adyen Payout Reconciliation',
    'version': '18.0.1.1.0',
    'summary': 'Batch each Adyen settlement report, book its payout, and handle ACH chargebacks automatically',
    'description': """
Adyen pays Selamta in batches. Each batch has a "Settlement details" report
(settlement_detail_report_batch_<n>.csv) listing every settled payment, refund,
chargeback, fee, invoice deduction and deposit correction, and one payout.

This module does the reconciliation that used to be done by hand:

1. Adyen's "Report available" webhook tells Odoo a report exists; Odoo downloads
   it with a Report user API key (or a report is uploaded by hand).
2. The report must prove: every row nets to exactly the payout.
3. Every settled payment, refund and chargeback is matched to its Odoo payment by
   PSP reference; the settled payments become a validated batch payment with the
   report attached.
4. When the Chase line for that payout (same TX...XT id and amount) arrives, the
   bank line's suspense line is replaced with Adyen fees, invoice deductions,
   deposit corrections, chargebacks, refunds and one line per payment, each
   matched to its payment. The entry is left in To Check.

Chargebacks (ACH returns) are handled as they happen, from Adyen's chargeback
webhook events, or from the settlement report if an event never arrived:

- the "Charge Back-<PSP>" payment is created, the bounced payment is taken off its
  invoices and the invoices are due again;
- the chargeback fee is invoiced from the second chargeback incident in 12 months
  (the first is waived, chargebacks a few days apart count once, processing
  errors are never charged); ACH is turned off for the customer from the third;
- the customer is emailed from the chargeback payment, and the office channel gets
  a post mentioning every member, with the customer's phone numbers.

Anything unusual stops and assigns a review activity instead of guessing: a report
that does not prove, an unknown row type, a payment missing or already matched, a
partial or card chargeback, or an amount that differs from Adyen's.
    """,
    'author': 'Selamta L.L.C',
    'category': 'Accounting/Accounting',
    'depends': ['account_accountant', 'account_batch_payment', 'payment', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/mail_template.xml',
        'views/adyen_settlement_views.xml',
        'views/adyen_dispute_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
