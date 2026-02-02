{
    'name': "prepithelp",

    'summary': "Integration helper for Prepit Webhooks and POS customizations",

    'description': """
        Handles POS menu exports to Prepit, stock level monitoring during 
        orders, and automated status webhooks.
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    'category': 'Sales/Point of Sale',
    'version': '19.0.1.0.0', # Updated for Odoo 19 compatibility
    'license': 'LGPL-3',     # Added to remove the log warning

    # FIXED: Added 'stock' because you are querying stock.quant
    'depends': ['base', 'point_of_sale', 'stock'],

    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
    ],
    'installable': True,
    'application': False,
}
