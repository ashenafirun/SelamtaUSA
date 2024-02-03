# -*- coding: utf-8 -*-
{
    'name': 'Package Wise Delivery',
    'version': '1.6',
    'category': 'Inventory/Inventory',
    'sequence': 85,
    'summary': 'This module allows us deliver product package wise',
    'description': """
""",
    'depends': ['stock','sale'],
    'data': [
        'views/stock_picking.xml'
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
