# -*- coding: utf-8 -*-
{
    'name': 'Selamta Homepage',
    'version': '18.0.1.5.1',
    'category': 'Website/Website',
    'summary': 'Wholesale homepage and footer for selamtausa.com',
    'description': """
Replaces the website homepage body and footer with the Selamta wholesale design.
The homepage is made of ordinary website-builder blocks (hero, why Selamta, shop by
category, how ordering works, best sellers, new arrivals, brands, call to action) that
can be edited, moved, duplicated or deleted with Edit on the website. Best sellers and
new arrivals are Odoo Products blocks reading the hand-picked homepage lists; brands are
a Dynamic Content block reading Product Brands. Also a darker, accessible footer with a
corrected copyright line.
    """,
    'author': 'Selamta LLC',
    'license': 'LGPL-3',
    'depends': ['website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/homepage.xml',
        'views/footer.xml',
        'views/homepage_item_views.xml',
        'data/snippet_filter_data.xml',
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
