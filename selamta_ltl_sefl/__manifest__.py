# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: Southeastern Freight Lines',
    'version': '18.0.1.0.1',
    'category': 'Inventory/Delivery',
    'summary': 'Southeastern Freight Lines (SEFL) Web Connect for Selamta LTL shipments: rate quotes, tracking, documents',
    'description': """
Connects Southeastern Freight Lines to Selamta LTL shipments through SEFL's Web Connect services
(sefl.com/seflWebsite/webconnect.jsp), with the MySEFL login.

* Rate shop: MySEFL rate quote for our account: total, quote number, transit days and the
  charge lines (linehaul per class, discount, fuel and accessorials).
* Tracking every two hours by PRO (SEFL's public tracing; no password in the address), and on
  delivery the delivery receipt, W&I certificate and freight invoice through Document Retrieval.
* Booking stays on sefl.com for now: choosing Southeastern in the rate shop saves the quote;
  type the PRO.

Setup: Inventory > Configuration > Shipping Methods > Southeastern Freight Lines. Provider:
Southeastern Freight Lines; LTL tab: LTL carrier, Bills come from: Southeastern; Southeastern
tab: MySEFL username, password and account number. They are kept in the database, never in
this code.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['selamta_ltl'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'views/delivery_carrier_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
