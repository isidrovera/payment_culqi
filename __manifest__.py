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
* Integración completa con API v2.0 de Culqi
* Soporte para múltiples medios de pago:
  - Tarjetas de crédito y débito (Visa, Mastercard, Diners, Amex)
  - Yape (billetera digital)
  - PagoEfectivo (pagos en efectivo)
  - Cuotéalo (pagos fraccionados)
  - Billeteras móviles
* Modos de integración flexibles:
  - Formulario embebido (Culqi Checkout)
  - Popup modal
  - Redirección externa
* Seguridad avanzada:
  - Encriptación RSA de payload
  - Autenticación con llaves públicas y privadas
  - Cumplimiento PCI DSS
* Gestión completa de transacciones:
  - Creación de tokens seguros
  - Procesamiento de cargos
  - Devoluciones automáticas
  - Notificaciones webhook
* Panel de administración integrado
* Soporte para ambientes de prueba y producción
* Logs detallados de transacciones

Requisitos:
-----------
* Cuenta activa en Culqi (https://culqi.com)
* Credenciales API (llave pública y privada)
* Certificado SSL en el sitio web

Configuración:
--------------
1. Instalar el módulo
2. Ir a Contabilidad > Configuración > Proveedores de Pago
3. Configurar Culqi con sus credenciales
4. Activar los métodos de pago deseados
5. Configurar webhooks en el panel de Culqi

Soporte:
--------
* Documentación: https://docs.culqi.com
* API Reference: https://apidocs.culqi.com
* Soporte Culqi: soporte@culqi.com
    """,
    
    'author': 'Tu Empresa',
    'website': 'https://www.tuempresa.com',
    'license': 'LGPL-3',
    
    # Dependencias
    'depends': [
        'payment',
        'website_sale',  # Para eCommerce
        'account',       # Para facturación
    ],
    
    # Datos del módulo
    'data': [
        # Seguridad
        'security/ir.model.access.csv',
        
        # Datos base
        'data/payment_provider_data.xml',
        
        # Vistas
        'views/payment_provider_views.xml',
        'views/payment_culqi_templates.xml',
    ],
    
    # Recursos web
    'assets': {
        'web.assets_frontend': [
            'payment_culqi/static/src/js/payment_form.js',
            'payment_culqi/static/src/css/payment_form.css',
        ],
        'web.assets_backend': [
            'payment_culqi/static/src/js/payment_form.js',
        ],
    },
    
    # Configuración del módulo
    'installable': True,
    'auto_install': False,
    'application': False,
    
    # Compatibilidad
    'odoo_version': '18.0',
    
    # Metadatos adicionales
    'images': [
        'static/description/banner.png',
        'static/description/icon.png',
    ],
    
    'external_dependencies': {
        'python': [
            'requests',     # Para llamadas HTTP a la API
            'cryptography', # Para encriptación RSA
        ],
    },
    
    # URLs importantes
    'support': 'https://www.tuempresa.com/soporte',
    'live_test_url': 'https://demo.culqi.com',
    
    # Configuración de precios (si es un módulo comercial)
    'price': 0.00,
    'currency': 'USD',
    
    # Post-install
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    
    # Configuración de logs
    'logging': {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'file': {
                'level': 'INFO',
                'class': 'logging.FileHandler',
                'filename': '/var/log/odoo/payment_culqi.log',
                'formatter': 'verbose',
            },
        },
        'loggers': {
            'payment_culqi': {
                'handlers': ['file'],
                'level': 'INFO',
                'propagate': True,
            },
        },
    },
}