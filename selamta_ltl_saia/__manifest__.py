# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL: Saia',
    'version': '18.0.1.1.0',
    'category': 'Inventory/Delivery',
    'summary': 'Saia LTL Freight API for Selamta LTL shipments: rate quotes, tracking, delivery documents',
    'description': """
Connects Saia LTL Freight to Selamta LTL shipments through Saia's own REST APIs
(developer portal saiaprodapi.developer.azure-api.net, docs api.saia.com/rate-quote).

* Rate shop: Saia rate quote at our pricing (Saia Secure login): total, quote number, transit
  days and the charge lines (linehaul per class, deficit weight, discount, fuel and
  accessorials). Saia's guaranteed services (GSS) can be listed too.
* Tracking every two hours by PRO, and on delivery the delivery receipt, weight certificate
  and invoice images.
* Booking (switch "Book through the API" on the Saia tab): choosing Saia in the rate shop
  requests the pickup (Saia pickup number) and files the BOL with Saia (PRO number and
  Saia's BOL PDF), through Saia's SOAP services on saiasecure.com with the Saia Secure login
  and account number. Test mode checks a booking without filing it. With the switch off, the
  quote is saved and the load is booked on saia.com.

Setup: Inventory > Configuration > Shipping Methods > Saia. Provider: Saia; LTL tab: LTL
carrier, Bills come from: Saia; Saia tab: the saia.com (Saia Secure) user ID and password and
the developer portal keys for Rate Quote, Tracking and Imaging; the account number for
booking. They are kept in the
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
