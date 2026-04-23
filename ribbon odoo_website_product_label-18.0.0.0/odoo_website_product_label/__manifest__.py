# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

{
    "name" : "Odoo Website Product Labels & Stickers on Shop",
    "version" : "18.0.0.0",
    "category" : "eCommerce",
    "depends" : ['website','website_sale','sale_management'],
    "author": "BROWSEINFO",
    "summary": 'App website different stickers for product website product Ribbon Website Product Labels website product pin website labels eCommerce Product Ribbons webshop label pin webshop Product tag website label pin Website product item Ribbon Stickers tags pins',
    "description": """
    Assign & Customize Product Labels on website Product tag on website Prodoct Stickers on website 
    Website product Label Website product Stickers Website product Ribbon Stickers as ribbon Product Label as Ribbon website
    Website eCommerce Product Ribbons
    website labels
    wesite sitckers website Stickers
    webshop product labels
    webshop product stckers
    Website Product Stickers
    Website Product Labels & Stickers
    website product ribben
    website label pin
    website product pin

    Assign and Customize Product Labels on webshop Product tag on webshop Prodoct Stickers on webshop 
    webshop product Label webshop product Stickers webshop product Ribbon Stickers as ribbon Product Label as Ribbon webshop
    webssite eCommerce Product Ribbons webshop
    webshop labels shop
    webshop sitckers webshop Stickers
    webstore product labels
    webstore product stckers
    webstore Product Stickers
    webshop Product Stickers webshop product labels
    webshop product ribben
    webshop label pin
    webshop product pin
This Odoo apps will allow you to pin ribben 
Now you can do this with help of this plugin, we have added few labels and sticker already on our apps which you can use
labels or stickers for product page or image on item If you want to add some Stickers/Tags/Label on your product which shows on website i.e Special offers, Sale , 50% off, Special price.
Also you can add other label and stickers too (its configurable ) you can link that with product and it will be visible on Shop in odoo ecommerce page.

    """,
    'website':"https://www.browseinfo.com/demo-request?app=odoo_website_product_label&version=18&edition=Community",
    "price": 9.99,
    'currency': "EUR",
    "data": [
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/product_label.xml',
        'views/template.xml',
    ],
    'assets':{
        'web.assets_frontend':[
        '/odoo_website_product_label/static/src/css/custom.css',
        ]
    },
    'license':'OPL-1',
    "auto_install": False,
    "application": True,
    "installable": True,
    'live_test_url':'https://www.browseinfo.com/demo-request?app=odoo_website_product_label&version=18&edition=Community',
    "images":['static/description/Banner.gif']
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
