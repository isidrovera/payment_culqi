# -*- coding: utf-8 -*-

import logging
from odoo import http
from odoo.http import request
from odoo.addons.payment.controllers.portal import PaymentPortal

_logger = logging.getLogger(__name__)


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

    @http.route('/payment/culqi/pay', type='http', auth='public', website=True, csrf=False)
    def culqi_pay_invoice(self, invoice_id=None, amount=None, access_token=None, **kwargs):
        """Ruta para pagar facturas específicas con Culqi"""
        
        if not invoice_id:
            return request.not_found()
        
        try:
            invoice_id = int(invoice_id)
            invoice = request.env['account.move'].sudo().browse(invoice_id)
            
            # Verificar que la factura existe y está en estado correcto
            if not invoice.exists() or invoice.state != 'posted':
                return request.not_found()
            
            # Verificar token de acceso si se proporciona
            if access_token and not invoice._portal_ensure_token():
                return request.not_found()
            
            # Monto a pagar (por defecto el residual de la factura)
            payment_amount = float(amount) if amount else invoice.amount_residual
            
            if payment_amount <= 0:
                return request.render('payment_culqi.payment_error', {
                    'error_message': 'Esta factura ya está pagada o no tiene monto pendiente.'
                })
            
            # Obtener proveedor Culqi activo
            culqi_provider = request.env['payment.provider'].sudo().search([
                ('code', '=', 'culqi'),
                ('state', 'in', ['enabled', 'test']),
                ('company_id', '=', invoice.company_id.id)
            ], limit=1)
            
            if not culqi_provider:
                return request.render('payment_culqi.payment_error', {
                    'error_message': 'Culqi no está configurado para esta empresa.'
                })
            
            # Valores para el template
            values = {
                'invoice': invoice,
                'amount': payment_amount,
                'currency': invoice.currency_id,
                'partner': invoice.partner_id,
                'provider': culqi_provider,
                'return_url': f'/payment/culqi/return?invoice_id={invoice_id}',
                'reference': f'INV-{invoice.name}-{invoice.id}',
            }
            
            return request.render('payment_culqi.invoice_payment_form', values)
            
        except (ValueError, TypeError):
            return request.not_found()

    @http.route('/payment/culqi/create_transaction', type='json', auth='public', csrf=False)
    def culqi_create_transaction_from_invoice(self, invoice_id, amount, **kwargs):
        """Crea una transacción de pago para una factura específica"""
        
        try:
            invoice = request.env['account.move'].sudo().browse(int(invoice_id))
            
            if not invoice.exists():
                return {'error': 'Factura no encontrada'}
            
            # Obtener proveedor Culqi
            culqi_provider = request.env['payment.provider'].sudo().search([
                ('code', '=', 'culqi'),
                ('state', 'in', ['enabled', 'test']),
                ('company_id', '=', invoice.company_id.id)
            ], limit=1)
            
            if not culqi_provider:
                return {'error': 'Proveedor Culqi no configurado'}
            
            # Método de pago por defecto (tarjetas)
            payment_method = request.env['payment.method'].sudo().search([
                ('code', '=', 'card'),
                ('provider_ids', 'in', culqi_provider.ids)
            ], limit=1)
            
            if not payment_method:
                return {'error': 'Método de pago no disponible'}
            
            # Crear transacción
            transaction_values = {
                'provider_id': culqi_provider.id,
                'payment_method_id': payment_method.id,
                'amount': float(amount),
                'currency_id': invoice.currency_id.id,
                'partner_id': invoice.partner_id.id,
                'reference': f'INV-{invoice.name}-{invoice.id}',
                'invoice_ids': [(4, invoice.id)],
                'landing_route': f'/payment/culqi/status?invoice_id={invoice_id}',
                'operation': 'online_direct',
            }
            
            # Agregar valores específicos de Culqi si se proporcionan
            if kwargs.get('culqi_token_id'):
                transaction_values['culqi_token_id'] = kwargs['culqi_token_id']
            if kwargs.get('culqi_payment_method'):
                transaction_values['culqi_payment_method'] = kwargs['culqi_payment_method']
            if kwargs.get('culqi_email'):
                transaction_values['culqi_email'] = kwargs['culqi_email']
            
            transaction = request.env['payment.transaction'].sudo().create(transaction_values)
            
            # Obtener valores de renderizado
            rendering_values = transaction._get_specific_rendering_values({})
            
            return {
                'success': True,
                'transaction_id': transaction.id,
                'reference': transaction.reference,
                'rendering_values': rendering_values
            }
            
        except Exception as e:
            _logger.error("Error creando transacción Culqi: %s", str(e))
            return {'error': 'Error interno del servidor'}

    @http.route('/payment/culqi/validate_payment_data', type='json', auth='public', csrf=False)
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
                method_data = method._get_culqi_payment_form_data(amount, currency_obj)
                return {'valid': True, 'method_data': method_data}
            except Exception as e:
                return {'valid': False, 'error': str(e)}
                
        except Exception as e:
            _logger.error("Error validando datos Culqi: %s", str(e))
            return {'valid': False, 'error': 'Error de validación'}

    @http.route('/payment/culqi/get_methods', type='json', auth='public', csrf=False)
    def culqi_get_payment_methods(self, amount=None, currency='PEN', invoice_id=None, **kwargs):
        """Obtiene métodos de pago disponibles para Culqi según el contexto"""
        
        try:
            # Obtener proveedor Culqi activo
            culqi_provider = request.env['payment.provider'].sudo().search([
                ('code', '=', 'culqi'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if not culqi_provider:
                return {'methods': []}
            
            # Filtrar métodos según configuración del proveedor
            available_methods = []
            
            if culqi_provider.culqi_enable_cards:
                available_methods.append({
                    'code': 'card',
                    'name': 'Tarjetas de Crédito/Débito',
                    'description': 'Visa, Mastercard, American Express, Diners Club',
                    'icon': '/payment_culqi/static/src/img/cards_icon.png',
                    'min_amount': 1.0,
                    'max_amount': 50000.0
                })
            
            if culqi_provider.culqi_enable_yape:
                available_methods.append({
                    'code': 'yape',
                    'name': 'Yape',
                    'description': 'Billetera digital del BCP',
                    'icon': '/payment_culqi/static/src/img/yape_icon.png',
                    'min_amount': 1.0,
                    'max_amount': 2000.0
                })
            
            if culqi_provider.culqi_enable_pagoefectivo:
                available_methods.append({
                    'code': 'pagoefectivo',
                    'name': 'PagoEfectivo',
                    'description': 'Paga en efectivo en agentes PagoEfectivo',
                    'icon': '/payment_culqi/static/src/img/pagoefectivo_icon.png',
                    'min_amount': 1.0,
                    'max_amount': 10000.0
                })
            
            if culqi_provider.culqi_enable_cuotealo:
                available_methods.append({
                    'code': 'cuotealo',
                    'name': 'Cuotéalo',
                    'description': 'Paga en cuotas sin tarjeta de crédito',
                    'icon': '/payment_culqi/static/src/img/cuotealo_icon.png',
                    'min_amount': 50.0,
                    'max_amount': 15000.0
                })
            
            # Filtrar por monto si se proporciona
            if amount:
                amount_float = float(amount)
                available_methods = [
                    method for method in available_methods
                    if method['min_amount'] <= amount_float <= method['max_amount']
                ]
            
            return {
                'methods': available_methods,
                'provider': {
                    'name': culqi_provider.name,
                    'state': culqi_provider.state,
                    'public_key': culqi_provider.culqi_public_key
                }
            }
            
        except Exception as e:
            _logger.error("Error obteniendo métodos Culqi: %s", str(e))
            return {'methods': [], 'error': str(e)}