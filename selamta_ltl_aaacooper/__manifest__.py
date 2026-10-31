# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: AAA Cooper',
    'version': '18.0.1.0.1',
    'category': 'Inventory/Delivery',
    'summary': 'AAA Cooper web services for Selamta LTL shipments: rate estimates, pickup requests, tracking, documents',
    'description': """
Connects AAA Cooper Transportation to Selamta LTL shipments through AAA Cooper's own web
services (aaacooper.com > Web Services), without a TMS in between.

* Rate shop: AAA Cooper rate estimate for our customer number (negotiated pricing, fuel,
  accessorials), estimate number, transit days and every charge line, from each pallet's
  calculated class, weight and dimensions.
* Book (optional, off by default): sends a pickup request for the shipment's pickup date,
  ready and close times with our BOL number and the estimate number, and saves the pickup
  confirmation and the AAA Cooper terminal. AAA Cooper has no BOL API: our BOL is the BOL.
  A pickup request is a real pickup, so booking stays off until it is switched on.
* Tracking every two hours by our BOL number until AAA Cooper assigns the PRO at pickup,
  then by PRO: status, delivered date, who signed; on delivery, the delivery receipt and
  inspection certificate (Imaging REST API).
* Cancel: AAA Cooper has no cancel service; Cancel tells staff to call AAA Cooper.

Setup: Inventory > Configuration > Shipping Methods > AAA Cooper. Provider: AAA Cooper; LTL
tab: LTL carrier, Bills come from: AAA Cooper; AAA Cooper tab: security API token
(aaacooper.com, Workspace > Admin Tools > Web Services) and customer number. The token is
kept in the database, never in this code.
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
