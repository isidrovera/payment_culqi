Culqi Payment Provider for Odoo 18
==================================

Este módulo permite integrar la pasarela de pagos Culqi con Odoo 18, permitiendo cobrar:

- 🧾 Facturas desde el portal del cliente
- 🛍️ Pedidos desde la tienda virtual (eCommerce)
- 🔁 Suscripciones y cargos recurrentes
- 💳 Tarjetas, Yape, PagoEfectivo y otros métodos de Culqi

Instalación
-----------

1. Instala el módulo desde Apps: `payment_culqi`
2. Ve a **Contabilidad > Configuración > Proveedores de Pago**
3. Habilita Culqi y configura tus llaves públicas/privadas
4. Activa los métodos de pago que desees usar

Configuración
-------------

Debes tener una cuenta activa en Culqi y registrar tus credenciales:

- Llave Pública (pk_…)
- Llave Secreta (sk_…)
- RSA ID y Llave RSA pública si vas a encriptar el payload

Para más información: https://docs.culqi.com/

Características Técnicas
-------------------------

- Uso del SDK oficial de Culqi JS (v4)
- Envío de token desde el frontend al backend de Odoo
- Confirmación del cargo vía REST API (`/charges`)
- Webhook para notificaciones automáticas (`/payment/culqi/webhook`)
- Códigos limpios y estructurados según estándar Odoo

Monedas Soportadas
------------------

Actualmente Culqi opera con:

- PEN (Soles)
- USD (Dólares)

Estado del módulo
-----------------

✅ Estable para producción

Compatibilidad
--------------

- Odoo 18 (Community o Enterprise)
- Culqi API v2

Licencia
--------

LGPL-3 (Licencia Pública General Reducida de GNU)
