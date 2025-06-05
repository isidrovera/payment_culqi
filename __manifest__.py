# -*- coding: utf-8 -*-
{
    'name': 'Payment Provider: Culqi',
    'version': '1.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 351,
    'summary': "Proveedor de pago Culqi para Perú",
    'description': " ",  # No debe estar vacío para evitar cargar README.md
    'depends': ['payment'],
    'data': [
        'views/payment_provider_views.xml',
        'views/payment_culqi_templates.xml',
        'data/payment_provider_data.xml',
    ],
    'post_init_hook': 'post_init_hook',  # 🔁 Aquí se invoca el hook al instalar
    'assets': {
        'web.assets_frontend': [
            'payment_culqi/static/src/**/*',
        ],
    },
    'license': 'LGPL-3',
}
