# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Payment Ayden Charge",
    "version": "18.0.1.2",
    "summary": "Payment Ayden Charge",
    "sequence": 21,
    "description": """
    Payment Ayden Charge
    """,
    "category": "Accounting/Payment Providers",
    "author": "Synconics Technologies Pvt. Ltd.",
    "website": "https://www.synconics.com",
    "depends": ["payment_adyen", "website_sale"],
    "data": [
        "data/data.xml",
        "views/payment_provider_views.xml",
        "views/payment_template.xml",
        "views/payment_transaction_views.xml",
        "views/website_template.xml",
        "wizard/account_payment_register.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "sync_payment_adyen_charge/static/src/js/payment_form.js",
            "sync_payment_adyen_charge/static/src/js/payment_form_update.js",
        ],
    },
    "demo": [],
    "images": [],
    "price": 0.0,
    "currency": "USD",
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "OPL-1",
}
