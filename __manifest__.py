# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

{
    'name': 'Culqi Payment Gateway',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 1450,
    'summary': 'Integración completa con Culqi para pagos, suscripciones y más',
    'description': """
Culqi Payment Gateway para Odoo 18
==================================

Integración completa con la pasarela de pagos Culqi que incluye:

Funcionalidades principales:
---------------------------
* Pagos de facturas y órdenes de venta
* Pagos en tienda virtual (eCommerce)
* Gestión de suscripciones y cobros recurrentes
* Tokenización y almacenamiento seguro de tarjetas
* Devoluciones parciales y totales
* Portal del cliente para gestionar métodos de pago
* Webhooks para sincronización automática
* Encriptación RSA para mayor seguridad

Características técnicas:
------------------------
* Cumplimiento PCI DSS
* Ambiente de pruebas y producción
* Logs detallados de transacciones
* Reportes y analíticas
* API REST completa
* Soporte para múltiples monedas

Países soportados:
-----------------
* Perú (PEN)
* Chile (CLP) 
* México (MXN)
* Colombia (COP)

Compatibilidad:
--------------
* Odoo 18.0+
* Python 3.8+
* Culqi API v2

Para más información visita: https://docs.culqi.com
    """,
    'author': 'Tu Empresa',
    'website': 'https://tuempresa.com',
    'license': 'LGPL-3',
    'depends': [
        # Core Odoo modules
        'base',
        'account',
        'payment',
        'sale',
        'website',
        'website_sale',
        'portal',
        
        # Optional but recommended
        'account_payment',
        'sale_management',
        'website_payment',
    ],
    'external_dependencies': {
        'python': [
            'culqi',
            'pycryptodome',
            'jsonschema',
            'python-dotenv',
        ],
    },
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        
        # Data files
        'data/payment_provider_data.xml',
        'data/culqi_data.xml',
        
        # Views - Provider and Transaction
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        
        # Views - Culqi Models
        'views/culqi_customer_views.xml',
        'views/culqi_card_views.xml',
        'views/culqi_plan_views.xml',
        'views/culqi_subscription_views.xml',
        'views/culqi_refund_views.xml',
        
        # Views - Extended Models
        'views/account_move_views.xml',
        
        # Templates
        'templates/culqi_form.xml',
        'templates/culqi_checkout.xml',
        'templates/culqi_portal.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_culqi/static/src/css/culqi_style.css',
            'payment_culqi/static/src/js/culqi_form.js',
            'payment_culqi/static/src/js/culqi_checkout.js',
        ],
        'web.assets_backend': [
            'payment_culqi/static/src/css/culqi_style.css',
        ],
        'portal.assets_frontend': [
            'payment_culqi/static/src/js/culqi_portal.js',
            'payment_culqi/static/src/css/culqi_style.css',
        ],
    },
    'demo': [
        'demo/payment_demo.xml',
        'demo/culqi_demo.xml',
    ],
    'images': [
        'static/description/banner.png',
        'static/description/icon.png',
        'static/description/culqi_logo.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'price': 299.00,
    'currency': 'USD',
    'support': 'support@tuempresa.com',
    'maintainers': ['tu_usuario'],
    'development_status': 'Production/Stable',
    'contributors': [
        'Tu Nombre <tu@email.com>',
    ],
}