# -*- coding: utf-8 -*-
{
    'name': 'Selamta LTL Freight',
    'version': '18.0.1.2.0',
    'category': 'Inventory/Delivery',
    'summary': 'Book LTL freight from delivery orders, print the BOL, and check every carrier bill against its quote',
    'description': """
Foundation for booking LTL freight directly with each carrier, replacing FreightPOP.

* LTL shipment record on every delivery order (Inventory > Operations > LTL Shipments):
  consignee, carrier, who bills us, quote number and itemized quoted charges, PRO, BOL
  and pickup numbers, handling units with dimensions, weight, NMFC item and class.
* Several delivery orders on one shipment (one BOL, one PRO, one carrier bill): orders for
  the same customer, and orders for different customers dropped at one place (customers
  next to each other, or one receiving for another). When the addresses differ, staff
  choose where the truck delivers and the BOL shows which pallets are for which customer.
  A delivery that is ready later can be added to a shipment until it is picked up.
* Freight class per pallet or box, calculated from its own dimensions and weight
  (density, pounds per cubic foot) with the NMFC density scale (13-tier scale effective
  19 Jul 2025; editable, and an NMFC item can have its own subs). Not taken from the
  product. Staff can override a unit's class; the shipment then shows the calculated one
  next to it.
* Handling units: a package whose package type is marked as an LTL pallet or box
  (Inventory > Configuration > Package Types) becomes its own line, with the type's length
  and width. Everything else (cases packed by product packaging, loose products) goes on
  one pallet line per delivery order with its total weight; staff set how many pallets it
  is and measure them. Pallet height is always measured and typed.
* Accessorials ordered are filled in from the customer's delivery services (Liftgate,
  Residential, Limited Access...) and printed on the BOL, with NO INSIDE DELIVERY when
  inside delivery was not ordered and the customer's receiving hours.
* Rate shop: asks every carrier that has an API connection for a rate, and lets staff add
  quotes they got by phone or on a carrier website, side by side. Picking a rate saves the
  quote; for an API carrier it books the shipment.
* Straight bill of lading (US Letter) printed from the shipment.
* 4x6 shipping labels: two per pallet (one for each side) and one per box, numbered
  1 of N over the shipment, with consignee, carrier, PRO barcode (BOL number until there
  is a PRO), order references and, on shared drops, whose orders are on that pallet.
* Carrier bill check: a vendor bill from an LTL carrier is matched to its shipment by PRO
  (or BOL number for carriers that bill on the BOL), using the rules from the 2026 freight
  audit: digits only, exact first, then a check digit on either side, then a leading 1.
  Never by amount. Shows quoted vs billed and the variance on the bill and the shipment.
  Matching runs when a bill is confirmed, from the "Match LTL shipment" button, and daily.

Carrier connections (TForce, XPO, Daylight, Roadrunner, Priority1, AAA Cooper) are added
as separate small modules that implement the methods described in
models/delivery_carrier.py. Until a carrier has one, shipments with it are booked on the
carrier's website and the PRO is typed in.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['stock_delivery', 'account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ltl_accessorial_data.xml',
        'data/ltl_density_scale_data.xml',
        'data/ir_cron_data.xml',
        'report/ltl_bol_report.xml',
        'report/ltl_label_report.xml',
        'wizard/ltl_rate_wizard_views.xml',
        'wizard/ltl_drop_wizard_views.xml',
        'views/ltl_shipment_views.xml',
        'views/ltl_config_views.xml',
        'views/stock_package_type_views.xml',
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'views/ltl_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
