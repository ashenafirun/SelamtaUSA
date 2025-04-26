# This software and associated files (the “Software”) can only be used (executed)
# with a valid Numla Enterprise Subscription for the correct number of users.
# It is forbidden to modify, publish, distribute, sublicense,
# or sell copies of the Software or modified copies of the Software.
#
# See LICENSE for full licensing information.
# Copyright (c) 2022 Numla Limited <az@numla.com>
# All rights reserved.
{
    # App information
    'name': "Stock Remove Closet Locaition",
    'version': '18.0.1.0',
    'category': 'Inventory/Inventory',
    'summary': "Stock related customizations",
    'description': "Show users to pick items according to the removal sequence on normal inventory transfer.",

    # Author
    'author': "Numla Ltd.",
    'website': "https://www.numla.com/",
    'maintainer': 'Numla Ltd.',
    'license': "Other proprietary",

    # Dependencies
    'depends': ['stock_barcode','stock','sale'],
    # Views
    'data': [
        'views/stock_location_views.xml',
        'views/stock_picking_type_views.xml',
        'views/stock_move_line_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_remove_closest_location/static/src/**/*.js',
        ]
    },

    # Module Specific
    'application': False,
    'installable': True,
    'auto_install': False,
}
