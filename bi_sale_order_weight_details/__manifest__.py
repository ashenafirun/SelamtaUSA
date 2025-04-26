# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Sale Order Weight Details',
    'version': '18.0.0.0',
    'category': 'Sales',
    'summary': 'All in One Total Weight on Sale Order Weight on purchase order weight on delivery Total Weight on Sales Total Weight on purchase Total weight on delivery Calculate weight on sales calculate weight on delivery weight product weight all in one product weight',
    'description': """
        
          Sale Order Weight Details in odoo,
          Sale Order Volume Details in odoo,
          Product Weight in odoo,
          Calculate Product Weight into Sale Order in odoo,
          Total product Weight in odoo,
          Total product Volume in odoo,
          Product Weight Details on Tree view in odoo,

    """,
    'author': 'BROWSEINFO',
    "price": 8,
    "currency": 'EUR',
    'website': "https://www.browseinfo.com/demo-request?app=bi_sale_order_weight_details&version=18&edition=Community",
    'depends': ['sale_management', 'stock'],
    'data': [
        'report/sale_order_report.xml',
        'views/sale_weight_views.xml',
    ],
    'demo': [],
    'test': [],
    'license': 'OPL-1',
    'installable': True,
    'auto_install': False,
    'live_test_url':'https://www.browseinfo.com/demo-request?app=bi_sale_order_weight_details&version=18&edition=Community',
    "images":['static/description/Banner.gif'],
}
