# -*- coding: utf-8 -*-
{
    'name': 'Selamta Homepage',
    'version': '18.0.1.4.0',
    'category': 'Website/Website',
    'summary': 'Wholesale homepage and footer for selamtausa.com',
    'description': """
Replaces the website homepage body and footer with the Selamta wholesale design:
hero with account call-to-action, shop-by-category tiles, how ordering works,
best sellers and new arrivals (automatic or hand-picked), brands we carry, and a darker,
accessible footer with a corrected copyright line.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/homepage.xml',
        'views/footer.xml',
        'views/homepage_item_views.xml',
        'data/brand_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'selamta_homepage/static/src/scss/selamta_home.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
