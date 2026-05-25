{
    'name': 'Split Packaging',
    'version': '18.0.14.0.0',
    'summary': 'Auto-split delivery moves by product packaging on reservation',
    'description': """
        Automatically splits stock moves based on product packaging when
        a delivery is reserved (Check Availability / action_assign).
        Example: Order 100 kg, packaging Box = 10 kg → 10 moves of 10 kg each.
        Uses Odoo native _split() method for full compatibility.
        Workers see pre-split lines in Barcode app ready to scan and pack.
    """,
    'author': 'Your Company',
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_stock'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
