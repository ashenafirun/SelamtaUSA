{
    'name': 'Selamta Report Fixes',
    'version': '18.0.1.0.0',
    'summary': 'Removes redundant tax display on Invoice/SO/PO reports since Selamta does not charge sales tax (B2B wholesale).',
    'description': """
        Selamta LLC is a B2B wholesale business that does not charge sales tax.
        Since no tax is ever applied, the standard Odoo report templates show
        a redundant "Untaxed Amount" row (identical to Total) and an empty
        "Taxes" column on Invoices, Sales Orders, and Purchase Orders.

        This module removes that redundant display:
        - Hides the "Untaxed Amount" subtotal row when there are no tax groups
          (applies automatically to Invoice, SO, and PO since they share the
          same base totals template).
        - Removes the "Taxes" column header and cell from the line items table
          on Invoice, Sales Order, and Purchase Order printed/portal documents.
    """,
    'author': 'Selamta L.L.C',
    'category': 'Accounting',
    'depends': ['account', 'sale', 'purchase'],
    'data': [
        'views/report_tax_display.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
