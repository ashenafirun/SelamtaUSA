# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: XPO',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'XPO LTL API for Selamta LTL shipments: rate quotes, BOL with pickup, tracking, documents',
    'description': """
Connects XPO to Selamta LTL shipments through XPO's own LTL APIs (xpo.com/help-center/api),
without a TMS in between.

* Rate shop: XPO rate quote for our account: total, quote (confirmation) number, transit
  days and the charge lines (linehaul, discount, fuel and accessorials), from each line's
  class, weight and dimensions. The XPO guaranteed (G!) price can be listed too.
* Book (optional, off by default): creates the XPO BOL with our BOL number, has XPO assign
  the PRO, schedules the pickup for the shipment's pickup date and window, and attaches
  XPO's BOL PDF as the carrier copy. Our own BOL with the PRO barcode stays the one to print.
  A test mode sends BOLs and pickups to XPO's test system instead.
* Tracking every two hours by PRO: status, estimated delivery, delivered date and who
  signed; on delivery, the delivery receipt and weight certificate images.
* Cancel: cancels the XPO BOL and its pickup request.

Setup: Inventory > Configuration > Shipping Methods > XPO. Provider: XPO; LTL tab: LTL
carrier, Bills come from: XPO; XPO tab: the key XPO emailed ("Basic ..."), the ltl.xpo.com
user ID and password, and our XPO account numbers. They are kept in the database, never in
this code.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['selamta_ltl'],
    'external_dependencies': {'python': ['requests', 'pytz']},
    'data': [
        'views/delivery_carrier_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
