
{
    'name': 'Product Availability Notifications',
    'category': 'Website/Website',
    'summary': 'Notify the user when a product is back in stock',
    'description': """
Allow the user to select if he wants to receive email notifications when a product  gets back in stock.
    """,
    'depends': [
        'website_sale_stock',
        'website_sale_wishlist',
        'website_sale_stock_wishlist',
    ],
    'data': [
        'security/ir.model.access.csv',
        # 'views/templates.xml',
        'data/template_email.xml',
        'data/ir_cron_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'out_of_stock_notification/static/src/**/*',
        ],
    },
    'auto_install': True,
    'license': 'LGPL-3',
}
