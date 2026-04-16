{
    'name': 'UPC Barcode Generation',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Products',
    'summary': 'Controlled UPC-A barcode generation for products',
    'description': 'Manage UPC-A barcode generation with prefix management, batch allocation, and immutability rules.',
    'depends': ['product', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/upc_prefix_views.xml',
        'views/product_template_views.xml',
        'views/product_product_views.xml',
        'views/upc_generation_wizard_views.xml',
        'data/server_actions.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
