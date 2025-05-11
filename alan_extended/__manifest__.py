{
    'name': 'Alan Theme Extended',
    'category': 'Website/Website',
    'sequence': 50,
    'version': '1.8',
    'description': "",
    'depends': ['theme_alan','website_sale','website_sale_comparison','product'],
    'data': [
        'views/theme_inherit.xml',
        'views/product_detail_inherit.xml',
        'views/product_popup_inherit.xml',
        'views/product_template_view.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'alan_extended/static/src/scss/shop.scss',
        ],
    },
    'license': 'LGPL-3',
}
