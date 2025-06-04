# -*- coding: utf-8 -*-
{
    'name': 'Culqi Payment Gateway',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'Integración con la pasarela de pagos Culqi para Perú',
    'description': """
Culqi Payment Gateway para Odoo 18
==================================

Este módulo permite integrar la pasarela de pagos Culqi con Odoo 18, proporcionando
una solución completa de pagos en línea para comercios en Perú.

Características principales:
---------------------------
* Integración con API v2.0 de Culqi
* Soporte para múltiples medios de pago:
  - Tarjetas (Visa, Mastercard, Diners, Amex)
  - Yape
  - PagoEfectivo
  - Cuotéalo
* Modos de integración:
  - Formulario embebido
  - Popup
  - Redirección externa
* Seguridad avanzada:
  - Encriptación RSA
  - Llaves públicas/privadas
  - Cumplimiento PCI DSS
* Gestión de transacciones:
  - Tokens seguros
  - Cargos
  - Reembolsos
  - Webhooks
* Soporte para prueba y producción
* Panel administrativo en Odoo
""",

    'author': 'Tu Empresa',
    'website': 'https://www.tuempresa.com',
    'license': 'LGPL-3',

    'depends': [
        'payment',
        'website_sale',
        'account',
    ],

    'data': [
        'security/ir.model.access.csv',
        'data/payment_provider_data.xml',
        'views/payment_provider_views.xml',
        'views/payment_culqi_templates.xml',
    ],

    'assets': {
        'web.assets_frontend': [
            'payment_culqi/static/src/js/payment_form.js',
            'payment_culqi/static/src/css/payment_form.css',
        ],
        'web.assets_backend': [
            'payment_culqi/static/src/js/payment_form.js',
        ],
    },

    'installable': True,
    'auto_install': False,
    'application': False,

    'images': [
        'static/description/banner.png',
        'static/description/icon.png',
    ],

    'external_dependencies': {
        'python': [
            'requests',
            'cryptography',
        ],
    },

    'support': 'https://www.tuempresa.com/soporte',
    'live_test_url': 'https://demo.culqi.com',
}
