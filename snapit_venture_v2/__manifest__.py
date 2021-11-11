# -*- coding: utf-8 -*-
{
    'name': "Snapit Venture",

    'summary': """Snapit Venture""",

    'description': """
        
    """,

    'author': "Ali Akbar",
    'category': "Customization",
    'website': "http://www.yourcompany.com",
    'version': '0.1',
    'application': True,
    'installable': True,
    'auto_install': False,

    'depends': ['base','sale_management','account_accountant','stock','ks_shopify'],
    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/menus.xml',
        'data/ir_cron_data.xml'
        
    ],
    # only loaded in demonstrat,ion mode
    'demo': [

    ],
    'qweb': [
#         'static/src/xml/activity.xml',
    ],
}