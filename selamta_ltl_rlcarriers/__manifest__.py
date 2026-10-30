# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: R+L Carriers',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'R+L Carriers API for Selamta LTL shipments: rate quotes, BOL with pickup, tracking, documents',
    'description': """
Connects R+L Carriers to Selamta LTL shipments through R+L's own REST API
(technology.rlcarriers.com), without a TMS in between.

* Rate shop: R+L rate quote for our account (the API key is tied to it): net charge, quote
  number, transit days and the charge lines, from each pallet's class, weight and dimensions.
  Guaranteed service levels can be listed too.
* Book (optional, off by default): creates the R+L BOL (universal PRO, so the driver does not
  re-sticker) with our BOL number, PO and quote number, schedules the pickup for the
  shipment's pickup date and window, and attaches R+L's BOL PDF as the carrier copy. Our own
  BOL with the PRO barcode stays the one to print.
* Tracking every two hours by PRO: status, estimated delivery, delivered date; on delivery,
  the delivery receipt, weight certificate and invoice images.
* Cancel: cancels the R+L pickup request.

Setup: Inventory > Configuration > Shipping Methods > R+L Carriers. Provider: R+L Carriers;
LTL tab: LTL carrier, Bills come from: R+L Carriers; R+L tab: API key (from
technology.rlcarriers.com, or the key already used by another system). The key is kept in the
database, never in this code.
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
