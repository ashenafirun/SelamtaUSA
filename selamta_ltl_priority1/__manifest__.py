# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: Priority1',
    'version': '18.0.1.0.1',
    'category': 'Inventory/Delivery',
    'summary': 'Priority1 API connection for Selamta LTL shipments: multi-carrier quotes, dispatch, tracking, documents',
    'description': """
Connects Priority1 (freight broker) to Selamta LTL shipments through Priority1's v2 API
(api.priority1.com), without a TMS in between.

* Rate shop: one Priority1 request returns quotes from many carriers; each shows as its own
  line ("Saia via Priority1"...) with the Priority1 quote, transit days, estimated delivery,
  quote expiry and every charge line, next to the carriers we connect directly.
* Book (optional, off by default): dispatches the chosen Priority1 quote with the shipment's
  pickup window, addresses, contacts and pallets; saves Priority1's BOL and pickup numbers,
  attaches the carrier's BOL, and prints the carrier that picks up on our BOL and labels.
  A dispatch is a real pickup, so booking stays off until it is switched on.
* Tracking every two hours by Priority1 BOL number: status, PRO once the carrier assigns
  it, delivered date; on delivery the delivery receipt.
* Cancel: the shipment's Cancel button cancels the dispatched load with Priority1 first.
* Bills: Priority1 bills under its own invoice numbers; link them to shipments by hand (or
  by our BOL number when Priority1 shows it).

Setup: Inventory > Configuration > Shipping Methods > Priority1. Provider: Priority1; LTL
tab: LTL carrier, Bills come from: Priority1; Priority1 tab: API key (from Priority1). The
key is kept in the database, never in this code.
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
