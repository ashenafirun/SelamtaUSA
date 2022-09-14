{
    "name": "Quantity Quick Cart Selamta",
    "category": "Website",
    "version": "15.0.1",
    "depends": ['theme_alan', 'stock', 'website_sale_stock', 'website_sale_wishlist'],
    "data": [
        'views/sh_shop_template.xml',
    ],
    "assets": {
        "web.assets_frontend": [
            "/quantity_quick_cart_selamta/static/src/js/shop.js",
            "/quantity_quick_cart_selamta/static/src/scss/shop.scss",
        ],
    },
    'licence': 'LGPL-3',
    "auto_install": True,
    "application": True,
    "installable": True,
}
