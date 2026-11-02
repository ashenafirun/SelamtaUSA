{
    'name': 'Selamta - Adyen Payout Reconciliation',
    'version': '18.0.1.0.0',
    'summary': 'Batch each Adyen settlement report and book its payout against the Chase line automatically',
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

Anything unusual stops that batch and assigns a review activity instead of
guessing: a report that does not prove, an unknown row type (balance transfers,
reversed chargebacks), a payment missing or already matched, a missing chargeback
payment, or an amount that differs from Adyen's.
    """,
    'author': 'Selamta L.L.C',
    'category': 'Accounting/Accounting',
    'depends': ['account_accountant', 'account_batch_payment', 'payment', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/adyen_settlement_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
