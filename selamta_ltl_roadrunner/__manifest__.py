# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: Roadrunner Freight',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Roadrunner Freight API connection for Selamta LTL shipments: rates, BOL, pickup, tracking, delivery receipts',
    'description': """
Connects Roadrunner Freight to Selamta LTL shipments through Roadrunner's own web services
(no TMS in between).

* Rate shop: Roadrunner rate for our account (negotiated discount, fuel, accessorials),
  transit days, quote number and every charge line, from the pallets' calculated class
  and weight.
* Book: one call to Roadrunner's BOL API creates the BOL, gets the PRO, schedules the
  pickup for the shipment's pickup date and window (QuickPickup), and returns Roadrunner's
  BOL PDF, attached as the carrier copy. Our own BOL stays the one to print.
* Tracking every two hours by PRO (or by pickup number until the PRO is known): status,
  delivered date; on delivery, the delivery receipt (POD) image. With the tracking
  Application ID and API key filled in, also the signed BOL, weight & inspection and
  invoice images.
* Test and production: "Test" sends BOLs to Roadrunner's test system, so nothing is
  picked up. Rates and tracking always come from production (they book nothing).

Setup: Inventory > Configuration > Shipping Methods > Roadrunner. Provider: Roadrunner
Freight; LTL tab: LTL carrier, Bills come from: Roadrunner; Roadrunner tab: account
number (Bill To on Roadrunner invoices) and the freight.rrts.com username and password.
Optional: tracking Application ID and API key from freight.rrts.com (Tools > Tracking).
Sign-ins are kept in the database, never in this code.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['selamta_ltl'],
    'external_dependencies': {'python': ['requests', 'lxml']},
    'data': [
        'views/delivery_carrier_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
