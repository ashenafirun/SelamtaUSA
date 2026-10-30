# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: TForce Freight',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'TForce Freight API connection for Selamta LTL shipments: rates, booking, pickup, tracking, documents',
    'description': """
Connects TForce Freight to Selamta LTL shipments through TForce's own API (no TMS in between).

* Rate shop: TForce rate with our negotiated pricing, transit days, quote number and every
  charge line, from the pallets' dimensions, weight and calculated class.
* Book: creates TForce's electronic BOL, gets the PRO, schedules the pickup in the same
  call, and attaches TForce's BOL PDF (and labels, if chosen) to the shipment.
* Tracking every two hours (status, delivered date, who signed) and, on delivery, the
  delivery receipt, weight & inspection certificate and invoice images.
* Test and production: "Test (CIE)" uses TForce's test environment so nothing is really
  booked; switch the shipping method to Production when ready.

Setup: Inventory > Configuration > Shipping Methods > TForce Freight. Provider: TForce
Freight; LTL tab: LTL carrier, Bills come from: TForce Freight; TForce tab: client ID and
client secret from the TForce developer portal (Profile > Configure My Client). The token
address and scope are filled in. API keys are kept in the database, never in this code.
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
