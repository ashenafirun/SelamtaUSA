# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    'name': ' Advance All in One Merge Orders - Picking,Sales,Purchase,Invoice,POS Category,Product Category',
    'version': '18.0.0.0',
    'category': 'Sales',
    'summary': 'Merge picking merge delivery merge receipt merge stock picking merge invoice merge sales order merge purchase merge order line merge order merge sale order Sync Product Category with POS Category Sync Product Category with Ecommerce Category merge category',
    'description': """ This odoo app helps user to merge all orders like sale order, purchase order, delivery order, receipt, customer invoice and vendor bill. User have different option to merge order like new order and cancel selected, new order and delete selected, merge order on existing selected and cancel other, merge order on existing selected and delete others, and sync pos and ecommerce product category. """,
    'author': 'BROWSEINFO',
    'website': 'https://www.browseinfo.com/demo-request?app=bi_advance_all_in_one_merge_orders&version=18&edition=Community',
    "price": 75,
    "currency": 'EUR',
    'depends': ['sale_management', 'purchase','product','stock','sale_stock' , 'point_of_sale', 'website', 'website_sale'],
    'data': [
        'security/cateogory_security.xml',
        'security/ir.model.access.csv',
        'wizard/invoice_merge_view.xml',
        'wizard/so_po_merge_view.xml',
        'wizard/merge_picking_view.xml',
        'wizard/merge_internal_picking_view.xml',
        'wizard/ecommerce_convert.xml',
        'wizard/merge_category_wizard_views.xml',
        'views/buttons.xml',
        'views/product_category_views.xml',
        'views/res_config_settings.xml',

    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    "live_test_url":'https://www.browseinfo.com/demo-request?app=bi_advance_all_in_one_merge_orders&version=18&edition=Community',
    "images":['static/description/Banner.gif'],
    'license': 'OPL-1',

}