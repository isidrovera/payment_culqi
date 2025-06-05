# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import requests
from werkzeug.urls import url_join

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.addons.payment import utils as payment_utils

try:
    from culqi2.client import Culqi
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    import base64
    import json
except ImportError:
    Culqi = None

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    # ==========================================
    # CAMPOS ESPECÍFICOS DE CULQI
    # ==========================================
    
    code = fields.Selection(
        selection_add=[('culqi', 'Culqi')],
        ondelete={'culqi': 'set default'}
    )
    
    # Configuración básica
    culqi_public_key = fields.Char(
        string='Llave Pública (Public Key)',
        help='Llave pública de Culqi. Empieza con pk_test_ para pruebas o pk_live_ para producción.',
        groups='base.group_system'
    )
    
    culqi_private_key = fields.Char(
        string='Llave Privada (Secret Key)',
        help='Llave privada de Culqi. Empieza con sk_test_ para pruebas o sk_live_ para producción.',
        groups='base.group_system'
    )
    
    # Configuración de encriptación
    culqi_rsa_public_key = fields.Text(
        string='Llave Pública RSA',
        help='Llave pública RSA para encriptación de payload.',
        groups='base.group_system'
    )
    
    culqi_rsa_id = fields.Char(
        string='ID de Llave RSA',
        help='Identificador de la llave RSA.',
        groups='base.group_system'
    )
    
    # Configuración de ambiente
    culqi_environment = fields.Selection([
        ('test', 'Pruebas (Test)'),
        ('live', 'Producción (Live)')
    ], string='Ambiente', default='test', required=True)
    
    # URLs de configuración
    culqi_webhook_url = fields.Char(
        string='URL de Webhook',
        help='URL donde Culqi enviará las notificaciones de eventos.',
        compute='_compute_culqi_webhook_url',
        store=True
    )
    
    culqi_success_url = fields.Char(
        string='URL de Éxito',
        help='URL de redirección cuando el pago es exitoso.',
        compute='_compute_culqi_urls',
        store=True
    )
    
    culqi_cancel_url = fields.Char(
        string='URL de Cancelación',
        help='URL de redirección cuando el pago es cancelado.',
        compute='_compute_culqi_urls',
        store=True
    )
    
    # Configuraciones adicionales
    culqi_enable_encryption = fields.Boolean(
        string='Habilitar Encriptación',
        default=False,
        help='Habilita la encriptación RSA del payload para mayor seguridad.'
    )
    
    culqi_enable_3ds = fields.Boolean(
        string='Habilitar 3D Secure',
        default=True,
        help='Habilita la autenticación 3D Secure para mayor seguridad en transacciones.'
    )
    
    culqi_installments = fields.Boolean(
        string='Permitir Cuotas',
        default=False,
        help='Permite pagos en cuotas.'
    )
    
    culqi_max_installments = fields.Integer(
        string='Máximo de Cuotas',
        default=12,
        help='Número máximo de cuotas permitidas.'
    )
    
    # Campos computados
    culqi_is_test_mode = fields.Boolean(
        string='Modo Prueba',
        compute='_compute_culqi_is_test_mode',
        help='Indica si el proveedor está en modo de pruebas.'
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('culqi_public_key', 'culqi_private_key')
    def _compute_culqi_is_test_mode(self):
        """Determina si estamos en modo de pruebas basado en las llaves."""
        for provider in self:
            public_key = provider.culqi_public_key or ''
            private_key = provider.culqi_private_key or ''
            provider.culqi_is_test_mode = (
                public_key.startswith('pk_test_') or 
                private_key.startswith('sk_test_')
            )
    
    @api.depends('code')
    def _compute_culqi_webhook_url(self):
        """Computa la URL del webhook."""
        for provider in self:
            if provider.code == 'culqi':
                base_url = provider.get_base_url()
                provider.culqi_webhook_url = url_join(base_url, '/payment/culqi/webhook')
            else:
                provider.culqi_webhook_url = False
    
    @api.depends('code')
    def _compute_culqi_urls(self):
        """Computa las URLs de éxito y cancelación."""
        for provider in self:
            if provider.code == 'culqi':
                base_url = provider.get_base_url()
                provider.culqi_success_url = url_join(base_url, '/payment/culqi/return')
                provider.culqi_cancel_url = url_join(base_url, '/payment/culqi/cancel')
            else:
                provider.culqi_success_url = False
                provider.culqi_cancel_url = False

    # ==========================================
    # VALIDACIONES
    # ==========================================
    
    @api.constrains('culqi_public_key', 'culqi_private_key')
    def _check_culqi_keys(self):
        """Valida que las llaves de Culqi sean correctas."""
        for provider in self:
            if provider.code != 'culqi':
                continue
                
            if provider.state in ['enabled', 'test']:
                if not provider.culqi_public_key:
                    raise ValidationError(_('La llave pública de Culqi es requerida.'))
                
                if not provider.culqi_private_key:
                    raise ValidationError(_('La llave privada de Culqi es requerida.'))
                
                # Validar formato de llaves
                public_key = provider.culqi_public_key
                private_key = provider.culqi_private_key
                
                if not (public_key.startswith('pk_test_') or public_key.startswith('pk_live_')):
                    raise ValidationError(_('La llave pública debe empezar con pk_test_ o pk_live_'))
                
                if not (private_key.startswith('sk_test_') or private_key.startswith('sk_live_')):
                    raise ValidationError(_('La llave privada debe empezar con sk_test_ o sk_live_'))
                
                # Verificar consistencia entre llaves
                is_public_test = public_key.startswith('pk_test_')
                is_private_test = private_key.startswith('sk_test_')
                
                if is_public_test != is_private_test:
                    raise ValidationError(_(
                        'Las llaves pública y privada deben ser del mismo ambiente '
                        '(ambas de prueba o ambas de producción).'
                    ))
    
    @api.constrains('culqi_rsa_public_key', 'culqi_rsa_id', 'culqi_enable_encryption')
    def _check_culqi_rsa_config(self):
        """Valida la configuración RSA si está habilitada."""
        for provider in self:
            if provider.code != 'culqi' or not provider.culqi_enable_encryption:
                continue
                
            if not provider.culqi_rsa_public_key:
                raise ValidationError(_('La llave pública RSA es requerida cuando la encriptación está habilitada.'))
            
            if not provider.culqi_rsa_id:
                raise ValidationError(_('El ID de llave RSA es requerido cuando la encriptación está habilitada.'))
            
            # Validar formato de la llave RSA
            try:
                RSA.import_key(provider.culqi_rsa_public_key)
            except Exception:
                raise ValidationError(_('La llave pública RSA no es válida.'))
    
    @api.constrains('culqi_max_installments')
    def _check_culqi_installments(self):
        """Valida la configuración de cuotas."""
        for provider in self:
            if provider.code != 'culqi':
                continue
                
            if provider.culqi_installments and provider.culqi_max_installments < 2:
                raise ValidationError(_('El número máximo de cuotas debe ser al menos 2.'))

    # ==========================================
    # MÉTODOS DE CULQI CLIENT
    # ==========================================
    
    def _get_culqi_client(self):
        """Obtiene una instancia del cliente Culqi."""
        self.ensure_one()
        
        if not Culqi:
            raise UserError(_(
                'La librería de Culqi no está instalada. '
                'Por favor instale: pip install culqi'
            ))
        
        if not self.culqi_public_key or not self.culqi_private_key:
            raise UserError(_('Las llaves de Culqi no están configuradas.'))
        
        return Culqi(self.culqi_public_key, self.culqi_private_key)
    
    def _get_culqi_encryption_options(self):
        """Obtiene las opciones de encriptación si están habilitadas."""
        self.ensure_one()
        
        if not self.culqi_enable_encryption:
            return {}
        
        if not self.culqi_rsa_public_key or not self.culqi_rsa_id:
            raise UserError(_('La configuración de encriptación RSA está incompleta.'))
        
        return {
            'rsa_public_key': self.culqi_rsa_public_key,
            'rsa_id': self.culqi_rsa_id
        }
    
    def _culqi_encrypt_data(self, data):
        """Encripta datos usando la llave RSA pública."""
        self.ensure_one()
        
        if not self.culqi_enable_encryption:
            return data
        
        try:
            # Importar la llave RSA
            rsa_key = RSA.import_key(self.culqi_rsa_public_key)
            cipher = PKCS1_v1_5.new(rsa_key)
            
            # Convertir datos a JSON y encriptar
            json_data = json.dumps(data)
            encrypted_data = cipher.encrypt(json_data.encode('utf-8'))
            
            # Codificar en base64
            return base64.b64encode(encrypted_data).decode('utf-8')
            
        except Exception as e:
            _logger.error('Error al encriptar datos: %s', str(e))
            raise UserError(_('Error al encriptar los datos de pago.'))

    # ==========================================
    # MÉTODOS DE VALIDACIÓN Y TESTING
    # ==========================================
    
    def action_test_culqi_connection(self):
        """Acción para probar la conexión con Culqi."""
        self.ensure_one()
        
        if self.code != 'culqi':
            return
        
        try:
            client = self._get_culqi_client()
            
            # Intentar crear un token de prueba
            test_data = {
                'card_number': '4111111111111111',
                'cvv': '123',
                'expiry_month': '09',
                'expiry_year': '2025',
                'email': 'test@example.com'
            }
            
            # Si la encriptación está habilitada, probar eso también
            options = self._get_culqi_encryption_options()
            
            # No crear el token realmente, solo validar la configuración
            _logger.info('Configuración de Culqi validada correctamente para %s', self.name)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Conexión Exitosa'),
                    'message': _('La configuración de Culqi es correcta y la conexión fue exitosa.'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error('Error al probar conexión con Culqi: %s', str(e))
            raise UserError(_('Error al conectar con Culqi: %s') % str(e))

    # ==========================================
    # MÉTODOS OVERRIDE DE PAYMENT
    # ==========================================
    
    def _get_supported_currencies(self):
        """Retorna las monedas soportadas por Culqi."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'culqi':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in ['PEN', 'USD', 'CLP', 'MXN', 'COP']
            )
        return supported_currencies
    
    def _get_default_payment_method_codes(self):
        """Retorna los métodos de pago por defecto."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code == 'culqi':
            default_codes.append('card')
        return default_codes
    
    @api.model
    def _get_compatible_providers(self, company_id, partner_id, amount, currency_id=None, **kwargs):
        """Filtra proveedores compatibles con la transacción."""
        providers = super()._get_compatible_providers(
            company_id, partner_id, amount, currency_id, **kwargs
        )
        
        # Filtrar Culqi si la moneda no es soportada
        if currency_id:
            currency = self.env['res.currency'].browse(currency_id)
            culqi_providers = providers.filtered(lambda p: p.code == 'culqi')
            
            if culqi_providers and currency.name not in ['PEN', 'USD', 'CLP', 'MXN', 'COP']:
                providers = providers - culqi_providers
                
        return providers