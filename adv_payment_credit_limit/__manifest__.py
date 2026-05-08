# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Advance Credit Check Rules",
    "version": "18.0.6.0",
    "summary": "Allows to configure advance credit check rules and apply on customer",
    "sequence": 21,
    "description": """
        Allows to configure advance credit check rules and apply on customer
    """,
    "category": "Sales",
    "author": "Synconics Technologies Pvt. Ltd.",
    "website": "http://www.synconics.com",
    "images": ["static/description/main_screen.png"],
    "depends": [
        "payment_credit_limit",
        "portal",
        "website_sale",
    ],
    "data": [
        "data/credit_code_data.xml",
        "security/ir.model.access.csv",
        "views/partner_view.xml",
        "views/credit_code_view.xml",
        "views/templates.xml",
        "views/res_config_setting_views.xml",
        "views/sale_order_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "adv_payment_credit_limit/static/src/js/website_sale_credit_redirect.js",
            "adv_payment_credit_limit/static/src/js/website_sale_payment_method.js",
            "adv_payment_credit_limit/static/src/scss/website_sale_payment_method.scss",
        ],
    },
    "demo": [],
    "price": 60,
    "currency": "EUR",
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "OPL-1",
}
