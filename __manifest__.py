# -*- coding: utf-8 -*-
{
    'name': 'Culqi Payment Gateway - Integración Completa',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'Integración completa con la pasarela de pagos Culqi para Perú',
    'description': """
Culqi Payment Gateway - Integración Completa para Odoo 18
========================================================

Este módulo proporciona una integración completa con la pasarela de pagos Culqi,
el procesador de pagos líder en Perú, ofreciendo una solución robusta y segura
para comercios electrónicos y empresas.

Características Principales:
----------------------------

🚀 **Integración API Completa**
• API v2.0 de Culqi con soporte completo  
• Manejo de tokens seguros  
• Webhooks para notificaciones automáticas  
• Verificación de firmas para seguridad  

💳 **Múltiples Medios de Pago**
• Tarjetas de crédito/débito (Visa, Mastercard, Diners, Amex)  
• Yape - Billetera digital del BCP  
• PagoEfectivo - Red de agentes en efectivo  
• Cuotéalo - Financiamiento sin tarjeta  

🎨 **Modos de Integración Flexibles**
• Formulario embebido en su sitio  
• Popup/Modal para una experiencia fluida  
• Redirección externa cuando sea necesario  

🔒 **Seguridad Avanzada**
• Encriptación RSA para datos sensibles  
• Cumplimiento PCI DSS nivel 1  
• Tokenización de tarjetas  
• Validación de webhooks con firmas  

💰 **Gestión Financiera Completa**
• Procesamiento automático de pagos  
• Reembolsos parciales y totales  
• Reconciliación automática con facturas  
• Integración con journals contables de Odoo  
• Manejo de comisiones y montos netos  

📊 **Panel Administrativo Avanzado**
• Dashboard con métricas de pagos  
• Filtros y búsquedas especializadas  
• Reportes detallados por método de pago  
• Trazabilidad completa de transacciones  

🌐 **Experiencia de Usuario Optimizada**
• Interfaz responsive para móviles  
• Formateo automático de campos  
• Validación en tiempo real  
• Mensajes de estado claros  
• Soporte para múltiples idiomas  

⚙️ **Características Técnicas**
• Compatible con Odoo 18.0+  
• Soporte para ambientes de prueba y producción  
• Logging detallado para debugging  
• Manejo robusto de errores  
• Tests automatizados incluidos  

📱 **Casos de Uso**
• E-commerce (Website Sale)  
• Facturación electrónica  
• Suscripciones y pagos recurrentes  
• Point of Sale (POS)  
• Marketplace y multi-vendor  

🇵🇪 **Específico para Perú**
• Integración con SUNAT  
• Soporte para moneda PEN y USD  
• Cumplimiento normativo local  
• Documentación en español  

Instalación y Configuración:
----------------------------
1. Instalar el módulo desde Apps  
2. Configurar credenciales de Culqi (llaves pública y secreta)  
3. Activar métodos de pago deseados  
4. Configurar webhooks en panel Culqi  
5. ¡Listo para procesar pagos!  

Soporte y Documentación:
------------------------
• Documentación completa incluida  
• Ejemplos de integración  
• Guías de troubleshooting  
• Soporte técnico disponible  

Este módulo está diseñado para empresas que buscan una solución de pagos
robusta, segura y completamente integrada con Odoo.
""",

    'author': 'Tu Empresa',
    'website': 'https://www.tuempresa.com',
    'license': 'LGPL-3',
    'support': 'soporte@tuempresa.com',

    'depends': [
        'payment',
        'account',
        'website_sale',
        'base_automation',
    ],

    'data': [
        # Seguridad
        'security/ir.model.access.csv',

        # Datos iniciales
        'data/payment_provider_data.xml',

        # Vistas principales
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        

        # Vistas contables
        'views/account_move_views.xml',
        'views/account_payment_register_views.xml',

        # Templates web
        'views/payment_culqi_templates.xml',

        
    ],

    'assets': {
        'web.assets_frontend': [
            'payment_culqi/static/src/js/payment_form_complete.js',
            'payment_culqi/static/src/css/payment_form.css',
        ],
        'web.assets_backend': [
            'payment_culqi/static/src/js/payment_form_complete.js',
            'payment_culqi/static/src/css/payment_form.css',
        ],
    },

    'demo': [
        'demo/payment_demo_data.xml',
    ],

    'installable': True,
    'auto_install': False,
    'application': True,
    'post_init_hook': 'post_init_hook',
    

    'images': [
        'static/description/banner.png',
        'static/description/icon.png',
        'static/description/screenshot_1.png',
        'static/description/screenshot_2.png',
        'static/description/screenshot_3.png',
    ],

    'external_dependencies': {
        'python': [
            'requests',
            'cryptography',
        ],
    },

    # Información del módulo
    'price': 299.0,
    'currency': 'USD',
    'live_test_url': 'https://demo.culqi.com',

    # Clasificación
    'sequence': 10,
    'maintainers': ['tu_usuario_github'],

    # Compatibilidad
    'odoo_version': '18.0',
    'python_requires': '>=3.8',

    # Enlaces útiles
    'documentation_url': 'https://docs.culqi.com',
    'repository_url': 'https://github.com/tu_usuario/payment_culqi',
    'issues_url': 'https://github.com/tu_usuario/payment_culqi/issues',
}
