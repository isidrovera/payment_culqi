# -*- coding: utf-8 -*-

import logging
import requests
import json
import hmac
import hashlib
from werkzeug import urls

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('culqi', 'Culqi')], 
        ondelete={'culqi': 'set default'}
    )
    
    # Credenciales de Culqi
    culqi_public_key = fields.Char(
        string="Public Key",
        help="Llave pública de Culqi (pk_test_xxx o pk_live_xxx)",
        required_if_provider='culqi',
        groups='base.group_system'
    )
    
    culqi_secret_key = fields.Char(
        string="Secret Key", 
        help="Llave secreta de Culqi (sk_test_xxx o sk_live_xxx)",
        required_if_provider='culqi',
        groups='base.group_system'
    )
    
    # Configuración RSA para encriptación
    culqi_rsa_id = fields.Char(
        string="RSA ID",
        help="ID de la llave RSA para encriptación de payload",
        groups='base.group_system'
    )
    
    culqi_rsa_public_key = fields.Text(
        string="RSA Public Key",
        help="Llave pública RSA para encriptación de payload",
        groups='base.group_system'
    )
    
    # Configuración de formulario
    culqi_checkout_mode = fields.Selection([
        ('embedded', 'Formulario Embebido'),
        ('popup', 'Ventana Emergente'),
        ('redirect', 'Redirección')
    ], string="Modo de Checkout", default='embedded', required=True)
    
    # URLs de Culqi
    culqi_webhook_url = fields.Char(
        string="Webhook URL",
        help="URL donde Culqi enviará notificaciones",
        compute='_compute_culqi_webhook_url',
        store=True
    )
    
    # Configuración de medios de pago
    culqi_enable_cards = fields.Boolean(
        string="Habilitar Tarjetas",
        default=True,
        help="Permite pagos con tarjetas de crédito/débito"
    )
    
    culqi_enable_yape = fields.Boolean(
        string="Habilitar Yape",
        default=True,
        help="Permite pagos con Yape"
    )
    
    culqi_enable_pagoefectivo = fields.Boolean(
        string="Habilitar PagoEfectivo",
        default=True,
        help="Permite pagos en efectivo con PagoEfectivo"
    )
    
    culqi_enable_cuotealo = fields.Boolean(
        string="Habilitar Cuotéalo",
        default=False,
        help="Permite pagos fraccionados con Cuotéalo"
    )

    @api.depends('code')
    def _compute_culqi_webhook_url(self):
        """Calcula la URL del webhook para notificaciones de Culqi"""
        for provider in self:
            if provider.code == 'culqi':
                base_url = provider.get_base_url()
                provider.culqi_webhook_url = urls.url_join(
                    base_url, '/payment/culqi/webhook'
                )
            else:
                provider.culqi_webhook_url = False

    @api.constrains('culqi_public_key', 'culqi_secret_key')
    def _check_culqi_credentials(self):
        """Valida el formato de las credenciales de Culqi"""
        for provider in self:
            if provider.code == 'culqi':
                if provider.culqi_public_key:
                    if not (provider.culqi_public_key.startswith('pk_test_') or 
                           provider.culqi_public_key.startswith('pk_live_')):
                        raise ValidationError(_(
                            "La llave pública debe comenzar con 'pk_test_' o 'pk_live_'"
                        ))
                
                if provider.culqi_secret_key:
                    if not (provider.culqi_secret_key.startswith('sk_test_') or 
                           provider.culqi_secret_key.startswith('sk_live_')):
                        raise ValidationError(_(
                            "La llave secreta debe comenzar con 'sk_test_' o 'sk_live_'"
                        ))
                
                # Verificar que ambas llaves sean del mismo ambiente
                if (provider.culqi_public_key and provider.culqi_secret_key):
                    pk_is_test = provider.culqi_public_key.startswith('pk_test_')
                    sk_is_test = provider.culqi_secret_key.startswith('sk_test_')
                    if pk_is_test != sk_is_test:
                        raise ValidationError(_(
                            "Las llaves pública y secreta deben ser del mismo ambiente (test o live)"
                        ))

    def _compute_feature_support_fields(self):
        """Override para habilitar características adicionales."""
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == 'culqi').update({
            'support_refund': 'partial',
            'support_manual_capture': False,
        })

    def _get_culqi_api_url(self):
        """Retorna la URL base de la API de Culqi"""
        return 'https://api.culqi.com/v2'

    def _culqi_make_request(self, endpoint, data=None, method='POST'):
        """
        Realiza una petición HTTP a la API de Culqi
        
        :param endpoint: Endpoint de la API (ej: '/charges')
        :param data: Datos a enviar en formato dict
        :param method: Método HTTP (GET, POST, etc.)
        :return: Respuesta de la API
        """
        self.ensure_one()
        
        if self.code != 'culqi':
            raise UserError(_("Este método solo está disponible para el proveedor Culqi"))
        
        if not self.culqi_secret_key:
            raise UserError(_("No se ha configurado la llave secreta de Culqi"))
        
        url = self._get_culqi_api_url() + endpoint
        
        headers = {
            'Authorization': f'Bearer {self.culqi_secret_key}',
            'Content-Type': 'application/json',
        }
        
        try:
            _logger.info("Culqi API Request: %s %s", method, url)
            if data:
                _logger.debug("Culqi API Data: %s", data)
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                timeout=60
            )
            
            _logger.info("Culqi API Response: %s", response.status_code)
            
            if response.status_code >= 400:
                error_data = response.json() if response.content else {}
                _logger.error("Culqi API Error: %s", error_data)
                raise UserError(_(
                    "Error en la API de Culqi: %s"
                ) % error_data.get('message', 'Error desconocido'))
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            _logger.error("Error en petición a Culqi: %s", str(e))
            raise UserError(_("Error de conexión con Culqi: %s") % str(e))

    def _culqi_test_credentials(self):
        """Prueba las credenciales configuradas"""
        self.ensure_one()
        
        try:
            # Intentar hacer una petición simple para validar credenciales
            result = self._culqi_make_request('/plans', method='GET')
            return {
                'success': True,
                'message': _("Credenciales válidas")
            }
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }

    def action_test_culqi_connection(self):
        """Acción para probar la conexión con Culqi desde la interfaz"""
        self.ensure_one()
        
        result = self._culqi_test_credentials()
        
        if result['success']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': result['message'],
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            raise UserError(result['message'])

    def _get_supported_currencies(self):
        """Retorna las monedas soportadas por Culqi"""
        culqi_currencies = super()._get_supported_currencies()
        if self.code == 'culqi':
            culqi_currencies = ['PEN', 'USD']
        return culqi_currencies

    def _get_validation_amount(self):
        """Monto mínimo para validación"""
        res = super()._get_validation_amount()
        if self.code == 'culqi':
            return 1.00
        return res

    def _get_default_payment_method_codes(self):
        """Métodos de pago por defecto para Culqi"""
        default_codes = super()._get_default_payment_method_codes()
        if self.code == 'culqi':
            default_codes = ['card']
            if self.culqi_enable_yape:
                default_codes.append('yape')
            if self.culqi_enable_pagoefectivo:
                default_codes.append('pagoefectivo')
            if self.culqi_enable_cuotealo:
                default_codes.append('cuotealo')
        return default_codes

    @api.model
    def _get_all_culqi_methods_codes(self):
        """Retorna lista de códigos de métodos para Culqi"""
        return self.search([('code', '=', 'culqi')]).with_context(active_test=False).mapped('payment_method_ids.code')

    @api.model
    def _get_compatible_providers(self, *args, currency_id=None, **kwargs):
        """Filtra proveedores compatibles según la moneda"""
        providers = super()._get_compatible_providers(*args, currency_id=currency_id, **kwargs)
        
        if currency_id:
            currency = self.env['res.currency'].browse(currency_id)
            if currency.name not in ['PEN', 'USD']:
                providers = providers.filtered(lambda p: p.code != 'culqi')
        
        return providers

    def _culqi_verify_webhook_signature(self, payload, signature):
        """Verifica la firma del webhook de Culqi"""
        if not self.culqi_secret_key:
            return False
            
        expected_signature = hmac.new(
            self.culqi_secret_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)