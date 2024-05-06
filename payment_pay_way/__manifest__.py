{
    'name': "Payway payment Provider",
    'summary': """
        Payway payment Provider
        (formely Decidir 2.0)
    """,
    'description': """
        Payway payment Provider
        (formely Decidir 2.0)
    """,
    
    'author': 'Plugberry ',
    'website': 'https://www.plugberry.com/',
    'category': 'Accounting/Payment Providers',
    'version': "16.0.2.0.0",
    'images':  ['static/description/thumb.png'],
    'depends': ['payment', 'card_installment', 'account_debit_note'],
    'assets': {
        'web.assets_frontend': [
            'payment_pay_way/static/src/js/payway.js',
            'https://live.decidir.com/static/v2.5/decidir.js'
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/payment_provider.xml',
        'views/templates.xml',
        'views/account_card.xml',
        'views/payment_transaction.xml',
        'data/payment_provider_data.xml',
    ],
    'demo': [
        'demo/demo.xml',
    ],
    'application': False,
    'installable': True,
    'license': 'LGPL-3',
}
