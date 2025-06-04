# -*- coding: utf-8 -*-

import json
import logging
import pprint
from werkzeug.exceptions import Forbidden

from odoo import http, _
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.addons.payment.controllers.portal import PaymentPortal

_logger = logging.getLogger(__name__)


class CulqiController(http.Controller):
    """Controlador para manejar webhooks y respuestas de Culqi"""

    _return_url = '/payment/culqi/return'
    _webhook_url = '/payment/culqi/webhook'
    _notification_url = '/payment/culqi/notification'

    # ==========================================
    # RUTAS DE RETORNO Y CONFIRMACIÓN
    # ==========================================

    @http.route(['/payment/culqi/return'], type='http', auth='public', 
                methods=['GET', 'POST'], csrf=False, save_session=False)
    def culqi_return_from_checkout(self, **kwargs):
        """Maneja el retorno desde el checkout de Culqi"""
        _logger.info("Culqi return: %s", pprint.pformat(kwargs))
        
        # Obtener referencia de la transacción
        reference = kwargs.get('ref') or kwargs.get('reference')
        if not reference:
            _logger.error("Culqi return sin referencia: %s", kwargs)
            return request.render('payment.payment_error', {
                'error_message': _("Referencia de transacción no encontrada")
            })

        # Buscar la transacción
        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'culqi')
        ], limit=1)

        if not tx:
            _logger.error("Transacción Culqi no encontrada: %s", reference)
            return request.render('payment.payment_error', {
                'error_message': _("Transacción no encontrada")
            })

        # Procesar datos de retorno si existen
        if kwargs:
            try:
                tx._process_notification_data(kwargs)
            except Exception as e:
                _logger.error("Error procesando retorno Culqi: %s", str(e))
                return request.render('payment.payment_error', {
                    'error_message': _("Error procesando el pago")
                })

        # Redireccionar según el estado
        if tx.state == 'done':
            return request.redirect('/payment/status')
        elif tx.state == 'pending':
            return request.redirect('/payment/status')
        else:
            return request.render('payment.payment_error', {
                'error_message': _("El pago no pudo ser procesado")
            })

    @http.route(['/payment/culqi/confirm'], type='json', auth='public', 
                methods=['POST'], csrf=False, save_session=False)
    def culqi_confirm_payment(self, **kwargs):
        """Confirma un pago desde el frontend (para checkout embebido)"""
        _logger.info("Culqi confirm payment: %s", pprint.pformat(kwargs))
        
        try:
            reference = kwargs.get('reference')
            token_id = kwargs.get('token_id')
            
            if not reference or not token_id:
                return {'success': False, 'error': 'Datos incompletos'}

            # Buscar la transacción
            tx = request.env['payment.transaction'].sudo().search([
                ('reference', '=', reference),
                ('provider_code', '=', 'culqi')
            ], limit=1)

            if not tx:
                return {'success': False, 'error': 'Transacción no encontrada'}

            # Crear cargo en Culqi
            charge_result = tx._culqi_create_charge(token_id)
            
            if charge_result.get('object') == 'charge':
                # Procesar resultado del cargo
                tx._process_notification_data(charge_result)
                return {
                    'success': True,
                    'status': tx.state,
                    'redirect_url': '/payment/status'
                }
            else:
                return {
                    'success': False,
                    'error': charge_result.get('user_message', 'Error en el pago')
                }
                
        except Exception as e:
            _logger.error("Error confirmando pago Culqi: %s", str(e))
            return {'success': False, 'error': str(e)}

    # ==========================================
    # WEBHOOK DE NOTIFICACIONES
    # ==========================================

    @http.route(['/payment/culqi/webhook'], type='http', auth='public',
                methods=['POST'], csrf=False, save_session=False)
    def culqi_webhook(self, **kwargs):
        """Maneja webhooks de Culqi"""
        
        # Obtener datos del webhook
        try:
            payload = request.httprequest.get_data(as_text=True)
            _logger.info("Culqi webhook recibido: %s", payload)
            
            if not payload:
                _logger.warning("Webhook Culqi vacío")
                return 'no data', 400
            
            data = json.loads(payload)
            
        except (ValueError, TypeError) as e:
            _logger.error("Error parseando webhook Culqi: %s", str(e))
            return 'invalid json', 400

        # Validar estructura del webhook
        if not isinstance(data, dict):
            _logger.error("Webhook Culqi con formato inválido: %s", data)
            return 'invalid format', 400

        # Obtener headers de seguridad
        signature = request.httprequest.headers.get('X-Culqi-Signature')
        event_type = request.httprequest.headers.get('X-Event-Type')
        
        _logger.info("Culqi webhook - Event Type: %s, Signature: %s", event_type, signature)

        try:
            # Procesar según el tipo de evento
            if event_type in ['charge.creation.succeeded', 'charge.update']:
                self._process_charge_webhook(data, signature, payload)
            elif event_type in ['refund.creation.succeeded']:
                self._process_refund_webhook(data, signature, payload)
            else:
                _logger.info("Tipo de evento Culqi no procesado: %s", event_type)
                
            return 'ok', 200
            
        except Exception as e:
            _logger.error("Error procesando webhook Culqi: %s", str(e))
            return 'error', 500

    def _process_charge_webhook(self, data, signature, payload):
        """Procesa webhook de cargo"""
        
        # Obtener información del cargo
        charge_data = data.get('data', {})
        charge_id = charge_data.get('id')
        
        if not charge_id:
            _logger.error("Webhook Culqi sin charge ID: %s", data)
            return

        # Buscar transacción por charge_id o reference
        tx = request.env['payment.transaction'].sudo().search([
            ('culqi_charge_id', '=', charge_id),
            ('provider_code', '=', 'culqi')
        ], limit=1)

        if not tx:
            # Buscar por referencia en metadata
            metadata = charge_data.get('metadata', {})
            reference = metadata.get('reference') or metadata.get('order_id')
            
            if reference:
                tx = request.env['payment.transaction'].sudo().search([
                    ('reference', '=', reference),
                    ('provider_code', '=', 'culqi')
                ], limit=1)

        if not tx:
            _logger.warning("Transacción Culqi no encontrada para charge: %s", charge_id)
            return

        # Verificar firma si está configurada
        if signature and tx.provider_id.culqi_secret_key:
            if not tx.provider_id._culqi_verify_webhook_signature(payload, signature):
                _logger.error("Firma de webhook Culqi inválida")
                raise Forbidden("Invalid signature")

        # Procesar datos del cargo
        try:
            tx._process_notification_data(charge_data)
            _logger.info("Webhook Culqi procesado exitosamente para tx: %s", tx.reference)
        except Exception as e:
            _logger.error("Error procesando webhook para tx %s: %s", tx.reference, str(e))
            raise

    def _process_refund_webhook(self, data, signature, payload):
        """Procesa webhook de reembolso"""
        
        refund_data = data.get('data', {})
        charge_id = refund_data.get('charge_id')
        
        if not charge_id:
            _logger.error("Webhook reembolso Culqi sin charge_id: %s", data)
            return

        # Buscar transacción original
        tx = request.env['payment.transaction'].sudo().search([
            ('culqi_charge_id', '=', charge_id),
            ('provider_code', '=', 'culqi')
        ], limit=1)

        if not tx:
            _logger.warning("Transacción Culqi no encontrada para reembolso: %s", charge_id)
            return

        # Verificar firma
        if signature and tx.provider_id.culqi_secret_key:
            if not tx.provider_id._culqi_verify_webhook_signature(payload, signature):
                _logger.error("Firma de webhook reembolso Culqi inválida")
                raise Forbidden("Invalid signature")

        # Registrar el reembolso
        try:
            refund_amount = refund_data.get('amount', 0) / 100  # Convertir de centavos
            
            # Crear transacción de reembolso si no existe
            refund_tx = request.env['payment.transaction'].sudo().search([
                ('culqi_charge_id', '=', refund_data.get('id')),
                ('operation', '=', 'refund')
            ], limit=1)
            
            if not refund_tx:
                refund_tx = tx._create_child_transaction(
                    refund_amount,
                    operation='refund'
                )
                refund_tx.culqi_charge_id = refund_data.get('id')
                refund_tx.provider_reference = refund_data.get('id')
            
            refund_tx._set_done()
            _logger.info("Reembolso Culqi procesado: %s", refund_data.get('id'))
            
        except Exception as e:
            _logger.error("Error procesando reembolso Culqi: %s", str(e))
            raise

    # ==========================================
    # RUTAS AUXILIARES
    # ==========================================

    @http.route(['/payment/culqi/form'], type='http', auth='public',
                methods=['GET'], csrf=False, save_session=False)
    def culqi_payment_form(self, **kwargs):
        """Renderiza el formulario de pago de Culqi"""
        
        reference = kwargs.get('reference')
        if not reference:
            return request.not_found()

        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'culqi')
        ], limit=1)

        if not tx:
            return request.not_found()

        # Obtener valores para el template
        rendering_values = tx._get_specific_rendering_values({})
        
        return request.render('payment_culqi.culqi_payment_form', {
            'tx': tx,
            'provider': tx.provider_id,
            **rendering_values
        })

    @http.route(['/payment/culqi/status'], type='http', auth='public',
                methods=['GET'], csrf=False, save_session=False)
    def culqi_payment_status(self, **kwargs):
        """Muestra el estado del pago"""
        
        reference = kwargs.get('reference')
        if not reference:
            return request.redirect('/payment/status')

        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'culqi')
        ], limit=1)

        if not tx:
            return request.redirect('/payment/status')

        return request.render('payment_culqi.payment_status', {
            'tx': tx,
            'payment_method_info': tx._get_culqi_payment_method_info()
        })

    @http.route(['/payment/culqi/validate'], type='json', auth='public',
                methods=['POST'], csrf=False, save_session=False)
    def culqi_validate_payment_data(self, **kwargs):
        """Valida datos de pago antes de procesar"""
        
        try:
            payment_method = kwargs.get('payment_method')
            amount = float(kwargs.get('amount', 0))
            currency = kwargs.get('currency', 'PEN')
            
            # Validaciones básicas
            if not payment_method:
                return {'valid': False, 'error': 'Método de pago requerido'}
            
            if amount <= 0:
                return {'valid': False, 'error': 'Monto inválido'}
            
            # Validar método de pago específico
            method = request.env['payment.method'].sudo().search([
                ('code', '=', payment_method),
                ('culqi_payment_type', '!=', False)
            ], limit=1)
            
            if not method:
                return {'valid': False, 'error': 'Método de pago no soportado'}
            
            # Validar montos según el método
            currency_obj = request.env['res.currency'].sudo().search([('name', '=', currency)], limit=1)
            
            try:
                method.get_culqi_form_data(amount, currency_obj)
                return {'valid': True}
            except ValidationError as e:
                return {'valid': False, 'error': str(e)}
                
        except Exception as e:
            _logger.error("Error validando datos Culqi: %s", str(e))
            return {'valid': False, 'error': 'Error de validación'}


class CulqiPaymentPortal(PaymentPortal):
    """Extensión del portal de pagos para manejar datos específicos de Culqi"""

    @staticmethod
    def _validate_transaction_kwargs(kwargs, additional_allowed_keys=()):
        """Valida argumentos de transacción incluyendo parámetros específicos de Culqi"""
        
        if kwargs.get('provider_id'):
            provider_id = request.env['payment.provider'].sudo().browse(int(kwargs['provider_id']))
            if provider_id.code == 'culqi':
                # Agregar claves adicionales permitidas para Culqi
                culqi_allowed_keys = (
                    'culqi_token_id',
                    'culqi_payment_method', 
                    'culqi_installments',
                    'culqi_email',
                    'culqi_device_fingerprint'
                )
                
                if isinstance(additional_allowed_keys, tuple):
                    additional_allowed_keys += culqi_allowed_keys
                elif isinstance(additional_allowed_keys, set):
                    additional_allowed_keys.update(culqi_allowed_keys)
                else:
                    additional_allowed_keys = culqi_allowed_keys
        
        super(CulqiPaymentPortal, CulqiPaymentPortal)._validate_transaction_kwargs(
            kwargs, 
            additional_allowed_keys=additional_allowed_keys
        )

    def _create_transaction(
        self, provider_id, payment_method_id, token_id, amount, currency_id, partner_id, flow,
        tokenization_requested, landing_route, reference_prefix=None, is_validation=False,
        custom_create_values=None, **kwargs
    ):
        """Crea transacción incluyendo valores específicos de Culqi"""
        
        # Extraer valores específicos de Culqi
        culqi_custom_create_values = {
            "culqi_token_id": kwargs.pop("culqi_token_id", None),
            "culqi_payment_method": kwargs.pop("culqi_payment_method", None),
            "culqi_installments": kwargs.pop("culqi_installments", None),
            "culqi_email": kwargs.pop("culqi_email", None),
            "culqi_device_fingerprint": kwargs.pop("culqi_device_fingerprint", None)
        }
        
        # Combinar con valores personalizados existentes
        custom_create_values = custom_create_values or {}
        custom_create_values.update(culqi_custom_create_values)
        
        return super()._create_transaction(
            provider_id, payment_method_id, token_id, amount, currency_id, partner_id, flow,
            tokenization_requested, landing_route, reference_prefix=reference_prefix, 
            is_validation=is_validation, custom_create_values=custom_create_values, **kwargs
        )