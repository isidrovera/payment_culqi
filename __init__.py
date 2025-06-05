# ============================================================================
# __init__.py (Raíz del módulo)
# ============================================================================

from . import models
from . import controllers
from . import wizards
from . import hooks

def post_init_hook(cr, registry):
    """
    Hook ejecutado después de la instalación del módulo.
    Configura datos iniciales y validaciones.
    """
    from odoo import api, SUPERUSER_ID
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Crear el proveedor de pago Culqi si no existe
    provider = env['payment.provider'].search([('code', '=', 'culqi')])
    if not provider:
        env['payment.provider'].create({
            'name': 'Culqi',
            'code': 'culqi',
            'state': 'disabled',
            'is_published': True,
            'payment_icon_ids': [(6, 0, [])],
        })
    
    # Configurar webhook URL base si no está configurado
    base_url = env['ir.config_parameter'].sudo().get_param('web.base.url')
    if base_url:
        webhook_url = f"{base_url}/payment/culqi/webhook"
        env['ir.config_parameter'].sudo().set_param('payment_culqi.webhook_url', webhook_url)

def uninstall_hook(cr, registry):
    """
    Hook ejecutado antes de la desinstalación del módulo.
    Limpia configuraciones y datos relacionados.
    """
    from odoo import api, SUPERUSER_ID
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Desactivar el proveedor de pago
    provider = env['payment.provider'].search([('code', '=', 'culqi')])
    if provider:
        provider.write({'state': 'disabled'})
    
    # Limpiar parámetros de configuración específicos
    params_to_clean = [
        'payment_culqi.webhook_url',
        'payment_culqi.public_key',
        'payment_culqi.private_key',
        'payment_culqi.rsa_public_key',
        'payment_culqi.rsa_id',
    ]
    
    for param in params_to_clean:
        env['ir.config_parameter'].sudo().search([('key', '=', param)]).unlink()





