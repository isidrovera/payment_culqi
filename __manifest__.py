# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Payment Provider: Culqi',
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 351,
    'summary': "Culqi Payment Integration for Peru: tarjetas, Yape, PagoEfectivo y más",
    'description': "Integración de Culqi con Odoo 18 para pagos con tarjeta, billeteras, QR y más.",
    'depends': ['payment'],
    'data': [
        'views/payment_form_templates.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'data/payment_provider_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_culqi/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
