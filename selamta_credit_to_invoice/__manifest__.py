{
    'name': 'Selamta - Credit Check Ignores Invoiced Orders',
    'version': '18.0.1.0.0',
    'summary': 'Leave already-invoiced sales orders out of the credit limit "amount due"',
    'description': """
Selamta ships each order once and invoices what was shipped: there are no
backorders. When an order ships short, the invoice is lower than the sales
order, and standard Odoo keeps the difference as "amount to invoice" on the
order forever. That leftover is added to the customer's credit_to_invoice, so
the credit limit banner on quotations and draft invoices shows money the
customer does not owe.

This module treats any confirmed order that already has a posted customer
invoice as closed: its leftover amount is no longer counted toward the
customer's credit. Orders that have not been invoiced yet still count in full,
and the customer's receivable balance is unchanged.
    """,
    'author': 'Selamta L.L.C',
    'category': 'Sales',
    'depends': ['sale'],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
