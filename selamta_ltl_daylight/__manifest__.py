# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: Daylight Transport',
    'version': '18.0.1.0.2',
    'category': 'Inventory/Delivery',
    'summary': 'Daylight Transport API connection for Selamta LTL shipments: rates, pickup booking, tracking, delivery receipts',
    'description': """
Connects Daylight Transport to Selamta LTL shipments through Daylight's ship-daylight API
(api.dylt.com), without a TMS in between.

* Rate shop: Daylight rate for our account (negotiated discount, fuel, accessorials) with
  the quote number, estimated delivery and every charge line. Daylight rates take no
  dimensions, so each pallet's class calculated from its own size and weight is sent as
  the declared class.
* Book (optional, off by default): schedules the Daylight pickup for the shipment's pickup
  date and window and attaches Daylight's populated BOL as the carrier copy. Daylight offers
  no test system, so a booking is a real pickup. While booking is off, choosing Daylight in
  the rate shop saves the quote and staff book the pickup on MyDaylight.
* Daylight returns a booking number, not a PRO. Tracking (every two hours) looks the
  shipment up by booking number until Daylight assigns the PRO at pickup, then by PRO;
  on delivery it attaches the delivery receipt and weight & inspection certificate.
* Accessorial codes: our standard services get Daylight's codes from the Accessorial Matrix
  on Daylight's API portal ("Lift Gate Delivery", "Residential Delivery"...); see and change
  them under Inventory > Configuration > LTL services (Daylight code column).
* Pickup references: our BOL number, the Daylight quote number, PO and sales order.

Setup: Inventory > Configuration > Shipping Methods > Daylight. Provider: Daylight
Transport; LTL tab: LTL carrier, Bills come from: Daylight Transport; Daylight tab: client
ID and secret (dylt-portalapi.apigee.io, app with the ship-daylight product), account
number and MyDaylight username and password. Sign-ins are kept in the database, never in
this code.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['selamta_ltl'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'data/ltl_accessorial_data.xml',
        'views/delivery_carrier_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
