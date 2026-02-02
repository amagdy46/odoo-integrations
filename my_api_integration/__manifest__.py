{
    'name': 'Company API Integration',
    'version': '1.0',
    'depends': ['base', 'contacts'], # We depend on contacts to map to res.partner
    'data': [
        'views/cron_view.xml',
    ],
    'installable': True,
}