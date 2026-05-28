{
    'name': 'Split Packaging',
    'version': '18.0.30.0.0',
    'summary': 'Auto-split delivery moves by product packaging + Mark Lot Picked in Barcode',
    'description': """
        1. Automatically splits stock move lines based on product packaging on reservation.
        2. Adds a toggle on the delivery form to mark lot-tracked products as Picked.
        3. Adds a "Mark Lot Picked" button directly inside the Barcode app.
    """,
    'author': 'Your Company',
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_stock', 'stock_barcode'],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'assets': {
        'stock_barcode.assets': [
            'split_packaging/static/src/barcode_picked_button.xml',
            'split_packaging/static/src/barcode_picked_button.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
