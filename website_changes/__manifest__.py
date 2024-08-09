# -*- coding: utf-8 -*-
{
    'name': 'Website Changes',
    'version': '15.0.2',
    'category': 'Accounting',
    'sequence': 23,
    'summary': '',
    'license': 'LGPL-3',
    'description': """

    """,
    'author': "Yumna Sahar",
    'website': "",

    'depends': ['base','website_sale'],
    'data': [
        'views/webcs.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'website_changes/static/src/js/webcs.js',
        ],
    },

    'installable': True,
    'application': True,
    'auto_install': False,
}
