# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import json
import logging
import hashlib
import hmac
from datetime import datetime
from werkzeug.exceptions import Forbidden, BadRequest

from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError
from odoo.addons.payment import utils as payment_utils
from odoo.addons.website.controllers.main import Website

_logger = logging.getLogger(__name__)


class CulqiController(http.Controller):
    """Controlador principal para manejar webhooks y callbacks de Culqi."""

    _webhook_url = '/payment/culqi/webhook'
    _return_url = '/payment/culqi/return'
    _cancel_url = '/payment/culqi/cancel'
    _notification_url = '/payment/culqi/notification'

    # ==========================================
    # WEBHOOK HANDLERS
    # ==========================================

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def culqi_webhook(self):
        """
        Maneja los webhooks de Culqi.
        Los webhooks son llamadas HTTP POST que Culqi envía para notificar eventos.
        """
        _logger.info('Recibido webhook de Culqi')
        
        try:
            # Obtener datos del webhook
            webhook_data = request.jsonrequest or json.loads(request.httprequest.data.decode('utf-8'))
            
            # Validar webhook
            if not self._validate_webhook_signature(webhook_data):
                _logger.warning('Webhook con firma inválida rechazado')
                raise Forbidden('Invalid webhook signature')
            
            # Procesar webhook según el tipo de evento
            event_type = webhook_data.get('type')
            event_data = webhook_data.get('data', {})
            
            _logger.info('Procesando webhook tipo: %s', event_type)
            
            if event_type.startswith('charge.'):
                self._handle_charge_webhook(event_type, event_data)
            elif event_type.startswith('subscription.'):
                self._handle_subscription_webhook(event_type, event_data)
            elif event_type.startswith('refund.'):
                self._handle_refund_webhook(event_type, event_data)
            elif event_type.startswith('customer.'):
                self._handle_customer_webhook(event_type, event_data)
            else:
                _logger.warning('Tipo de webhook no manejado: %s', event_type)
            
            return 'OK'
            
        except Exception as e:
            _logger.error('Error procesando webhook de Culqi: %s', str(e))
            # Retornar 200 para evitar reintentos de Culqi en errores conocidos
            return 'ERROR: %s' % str(e)

    def _validate_webhook_signature(self, webhook_data):
        """
        Valida la firma del webhook para asegurar que viene de Culqi.
        """
        # TODO: Implementar validación de firma cuando Culqi la soporte
        # Por ahora, validamos que tenga la estructura esperada
        required_fields = ['type', 'data']
        
        for field in required_fields:
            if field not in webhook_data:
                return False
        
        return True

    def _handle_charge_webhook(self, event_type, charge_data):
        """Maneja webhooks relacionados con cargos."""
        charge_id = charge_data.get('id')
        if not charge_id:
            _logger.warning('Webhook de cargo sin ID: %s', charge_data)
            return
        
        # Buscar la transacción por charge_id
        transaction = request.env['payment.transaction'].sudo().search([
            ('culqi_charge_id', '=', charge_id)
        ], limit=1)
        
        if transaction:
            transaction._handle_culqi_notification({
                'type': event_type,
                'data': charge_data
            })
        else:
            _logger.warning('No se encontró transacción para charge_id: %s', charge_id)

    def _handle_subscription_webhook(self, event_type, subscription_data):
        """Maneja webhooks relacionados con suscripciones."""
        subscription_id = subscription_data.get('id')
        if not subscription_id:
            _logger.warning('Webhook de suscripción sin ID: %s', subscription_data)
            return
        
        # Buscar la suscripción por ID de Culqi
        subscription = request.env['culqi.subscription'].sudo().search([
            ('culqi_subscription_id', '=', subscription_id)
        ], limit=1)
        
        if subscription:
            # Procesar evento de suscripción
            if event_type == 'subscription.charged':
                self._handle_subscription_charged(subscription, subscription_data)
            elif event_type == 'subscription.charge_failed':
                self._handle_subscription_charge_failed(subscription, subscription_data)
            elif event_type == 'subscription.canceled':
                self._handle_subscription_canceled(subscription, subscription_data)
            elif event_type == 'subscription.updated':
                subscription.retrieve_from_culqi()
        else:
            _logger.warning('No se encontró suscripción para ID: %s', subscription_id)

    def _handle_subscription_charged(self, subscription, data):
        """Maneja el evento de cargo exitoso de suscripción."""
        subscription.successful_charges += 1
        subscription.total_paid += subscription.total_amount
        subscription.billing_cycle_count += 1
        subscription._update_billing_period()
        
        # Crear factura si es necesario
        if subscription.plan_id.product_id:
            subscription._create_subscription_invoice(None)  # TODO: Crear transacción desde webhook

    def _handle_subscription_charge_failed(self, subscription, data):
        """Maneja el evento de cargo fallido de suscripción."""
        subscription.failed_charges += 1
        subscription.state = 'past_due'

    def _handle_subscription_canceled(self, subscription, data):
        """Maneja el evento de cancelación de suscripción."""
        subscription.state = 'cancelled'
        subscription.cancelled_date = datetime.now().date()

    def _handle_refund_webhook(self, event_type, refund_data):
        """Maneja webhooks relacionados con reembolsos."""
        request.env['culqi.refund'].sudo().handle_culqi_webhook_refund({
            'type': event_type,
            'data': refund_data
        })

    def _handle_customer_webhook(self, event_type, customer_data):
        """Maneja webhooks relacionados con clientes."""
        customer_id = customer_data.get('id')
        if not customer_id:
            return
        
        customer = request.env['culqi.customer'].sudo().search([
            ('culqi_customer_id', '=', customer_id)
        ], limit=1)
        
        if customer and event_type == 'customer.updated':
            customer.retrieve_from_culqi()

    # ==========================================
    # CALLBACK HANDLERS (URLs de retorno)
    # ==========================================

    @http.route(_return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def culqi_return(self, **kwargs):
        """
        Maneja el retorno exitoso desde Culqi.
        El cliente es redirigido aquí después de un pago exitoso.
        """
        _logger.info('Cliente retornó de Culqi con parámetros: %s', kwargs)
        
        try:
            # Obtener referencia de la transacción
            tx_reference = kwargs.get('reference') or kwargs.get('tx_ref')
            if not tx_reference:
                raise ValidationError(_('No se encontró referencia de transacción'))
            
            # Buscar la transacción
            transaction = request.env['payment.transaction'].sudo().search([
                ('reference', '=', tx_reference)
            ], limit=1)
            
            if not transaction:
                raise ValidationError(_('Transacción no encontrada: %s') % tx_reference)
            
            # Procesar el retorno
            self._handle_return_data(transaction, kwargs)
            
            # Redireccionar según el contexto
            return self._redirect_after_payment(transaction, success=True)
            
        except Exception as e:
            _logger.error('Error en retorno de Culqi: %s', str(e))
            return request.render('payment_culqi.payment_error', {
                'error_message': str(e)
            })

    @http.route(_cancel_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def culqi_cancel(self, **kwargs):
        """
        Maneja la cancelación desde Culqi.
        El cliente es redirigido aquí cuando cancela el pago.
        """
        _logger.info('Cliente canceló pago en Culqi con parámetros: %s', kwargs)
        
        try:
            # Obtener referencia de la transacción
            tx_reference = kwargs.get('reference') or kwargs.get('tx_ref')
            if tx_reference:
                transaction = request.env['payment.transaction'].sudo().search([
                    ('reference', '=', tx_reference)
                ], limit=1)
                
                if transaction:
                    transaction._set_canceled(_('Pago cancelado por el usuario'))
                    return self._redirect_after_payment(transaction, success=False)
            
            # Si no hay referencia, redireccionar a página de error genérica
            return request.render('payment_culqi.payment_canceled')
            
        except Exception as e:
            _logger.error('Error en cancelación de Culqi: %s', str(e))
            return request.render('payment_culqi.payment_error', {
                'error_message': str(e)
            })

    def _handle_return_data(self, transaction, return_data):
        """Procesa los datos de retorno de Culqi."""
        # Obtener token o charge_id de los parámetros de retorno
        token_id = return_data.get('token_id')
        charge_id = return_data.get('charge_id')
        
        if token_id and not transaction.culqi_token_id:
            # Si tenemos un token, crear el cargo
            transaction.culqi_token_id = token_id
            transaction.culqi_source_id = token_id
            transaction._create_culqi_charge()
            
        elif charge_id and not transaction.culqi_charge_id:
            # Si tenemos un charge_id directamente, actualizar la transacción
            transaction.culqi_charge_id = charge_id
            # Obtener información del cargo desde Culqi
            try:
                client = transaction.provider_id._get_culqi_client()
                charge_response = client.charge.read(charge_id)
                transaction._process_culqi_charge_response(charge_response)
            except Exception as e:
                _logger.error('Error obteniendo información del cargo %s: %s', charge_id, str(e))

    def _redirect_after_payment(self, transaction, success=True):
        """Redirecciona después del pago según el contexto."""
        # Si es un pago de eCommerce
        if hasattr(transaction, 'sale_order_ids') and transaction.sale_order_ids:
            if success:
                return request.redirect('/shop/confirmation')
            else:
                return request.redirect('/shop/payment')
        
        # Si es un pago de factura
        elif hasattr(transaction, 'invoice_ids') and transaction.invoice_ids:
            invoice = transaction.invoice_ids[0]
            if success:
                return request.redirect(f'/my/invoices/{invoice.id}?access_token={invoice.access_token}')
            else:
                return request.redirect(f'/my/invoices/{invoice.id}?access_token={invoice.access_token}&payment_error=1')
        
        # Redirección por defecto
        elif success:
            return request.redirect('/payment/status/success?tx_ref=%s' % transaction.reference)
        else:
            return request.redirect('/payment/status/error?tx_ref=%s' % transaction.reference)

    # ==========================================
    # API ENDPOINTS PARA FRONTEND
    # ==========================================

    @http.route('/payment/culqi/create_token', type='json', auth='public', methods=['POST'], csrf=False)
    def create_token(self, **kwargs):
        """
        API endpoint para crear un token desde el frontend.
        Usado por el JavaScript del formulario de pago.
        """
        try:
            # Validar datos de entrada
            required_fields = ['card_number', 'cvv', 'expiry_month', 'expiry_year', 'email']
            for field in required_fields:
                if not kwargs.get(field):
                    raise ValidationError(_('Campo requerido: %s') % field)
            
            # Obtener o crear la transacción
            tx_reference = kwargs.get('tx_reference')
            if not tx_reference:
                raise ValidationError(_('Referencia de transacción requerida'))
            
            transaction = request.env['payment.transaction'].sudo().search([
                ('reference', '=', tx_reference)
            ], limit=1)
            
            if not transaction:
                raise ValidationError(_('Transacción no encontrada'))
            
            # Crear token
            card_data = {
                'card_number': kwargs['card_number'],
                'cvv': kwargs['cvv'],
                'expiry_month': kwargs['expiry_month'],
                'expiry_year': kwargs['expiry_year'],
                'email': kwargs['email'],
            }
            
            token_response = transaction._create_culqi_token(card_data)
            
            if token_response:
                return {
                    'success': True,
                    'token_id': token_response['id'],
                    'message': _('Token creado exitosamente')
                }
            else:
                return {
                    'success': False,
                    'error': _('Error al crear token')
                }
                
        except Exception as e:
            _logger.error('Error creando token: %s', str(e))
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/payment/culqi/create_charge', type='json', auth='public', methods=['POST'], csrf=False)
    def create_charge(self, **kwargs):
        """
        API endpoint para crear un cargo desde el frontend.
        """
        try:
            tx_reference = kwargs.get('tx_reference')
            token_id = kwargs.get('token_id')
            
            if not tx_reference or not token_id:
                raise ValidationError(_('Referencia de transacción y token requeridos'))
            
            transaction = request.env['payment.transaction'].sudo().search([
                ('reference', '=', tx_reference)
            ], limit=1)
            
            if not transaction:
                raise ValidationError(_('Transacción no encontrada'))
            
            # Crear cargo
            transaction.culqi_token_id = token_id
            transaction.culqi_source_id = token_id
            charge_response = transaction._create_culqi_charge()
            
            if charge_response and transaction.state == 'done':
                return {
                    'success': True,
                    'charge_id': charge_response['id'],
                    'redirect_url': self._get_success_url(transaction)
                }
            else:
                return {
                    'success': False,
                    'error': transaction.state_message or _('Error al procesar el pago')
                }
                
        except Exception as e:
            _logger.error('Error creando cargo: %s', str(e))
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/payment/culqi/create_subscription', type='json', auth='user', methods=['POST'], csrf=False)
    def create_subscription(self, **kwargs):
        """
        API endpoint para crear una suscripción.
        """
        try:
            # Validar parámetros requeridos
            required_fields = ['plan_id', 'token_id']
            for field in required_fields:
                if not kwargs.get(field):
                    raise ValidationError(_('Campo requerido: %s') % field)
            
            plan_id = kwargs['plan_id']
            token_id = kwargs['token_id']
            
            # Obtener o crear cliente
            partner = request.env.user.partner_id
            customer = request.env['culqi.customer'].search([
                ('partner_id', '=', partner.id)
            ], limit=1)
            
            if not customer:
                # Crear cliente
                provider = request.env['payment.provider'].search([('code', '=', 'culqi')], limit=1)
                customer = request.env['culqi.customer'].create({
                    'partner_id': partner.id,
                    'provider_id': provider.id,
                    'name': partner.name,
                    'email': partner.email,
                })
                customer.create_in_culqi()
            
            # Crear tarjeta desde token
            card = request.env['culqi.card'].create({
                'customer_id': customer.id,
                'name': 'Tarjeta principal',
            })
            card.create_in_culqi(token_id)
            
            # Crear suscripción
            subscription = request.env['culqi.subscription'].create({
                'customer_id': customer.id,
                'plan_id': plan_id,
                'card_id': card.id,
            })
            subscription.create_in_culqi()
            
            return {
                'success': True,
                'subscription_id': subscription.id,
                'redirect_url': f'/my/subscriptions/{subscription.id}'
            }
            
        except Exception as e:
            _logger.error('Error creando suscripción: %s', str(e))
            return {
                'success': False,
                'error': str(e)
            }

    def _get_success_url(self, transaction):
        """Obtiene la URL de éxito según el contexto."""
        base_url = transaction.provider_id.get_base_url()
        return f"{base_url}/payment/culqi/return?reference={transaction.reference}"

    # ==========================================
    # ENDPOINTS DE ESTADO
    # ==========================================

    @http.route('/payment/status/success', type='http', auth='public', website=True)
    def payment_success(self, **kwargs):
        """Página de éxito del pago."""
        tx_ref = kwargs.get('tx_ref')
        transaction = None
        
        if tx_ref:
            transaction = request.env['payment.transaction'].sudo().search([
                ('reference', '=', tx_ref)
            ], limit=1)
        
        return request.render('payment_culqi.payment_success', {
            'transaction': transaction,
            'page_name': 'payment_success',
        })

    @http.route('/payment/status/error', type='http', auth='public', website=True)
    def payment_error(self, **kwargs):
        """Página de error del pago."""
        tx_ref = kwargs.get('tx_ref')
        transaction = None
        
        if tx_ref:
            transaction = request.env['payment.transaction'].sudo().search([
                ('reference', '=', tx_ref)
            ], limit=1)
        
        return request.render('payment_culqi.payment_error', {
            'transaction': transaction,
            'error_message': kwargs.get('error', _('Error desconocido en el procesamiento del pago')),
            'page_name': 'payment_error',
        })

    # ==========================================
    # ENDPOINTS PARA TESTING
    # ==========================================

    @http.route('/payment/culqi/test', type='http', auth='user', website=True)
    def test_payment(self, **kwargs):
        """Página de prueba para el formulario de pago."""
        if not request.env.user.has_group('base.group_system'):
            raise Forbidden('Solo administradores pueden acceder a esta página')
        
        # Obtener proveedor Culqi
        provider = request.env['payment.provider'].search([('code', '=', 'culqi')], limit=1)
        if not provider:
            raise ValidationError(_('Proveedor Culqi no configurado'))
        
        # Crear transacción de prueba
        transaction = request.env['payment.transaction'].create({
            'reference': 'TEST-%s' % datetime.now().strftime('%Y%m%d%H%M%S'),
            'amount': 10.00,
            'currency_id': request.env.company.currency_id.id,
            'partner_id': request.env.user.partner_id.id,
            'provider_id': provider.id,
        })
        
        rendering_values = transaction._get_specific_rendering_values({})
        
        return request.render('payment_culqi.test_payment_form', {
            'transaction': transaction,
            'rendering_values': rendering_values,
            'provider': provider,
        })

    @http.route('/payment/culqi/test_webhook', type='json', auth='user', methods=['POST'])
    def test_webhook(self, **kwargs):
        """Endpoint para probar webhooks localmente."""
        if not request.env.user.has_group('base.group_system'):
            raise Forbidden('Solo administradores pueden usar este endpoint')
        
        # Webhook de prueba
        test_webhook_data = {
            'type': 'charge.success',
            'data': {
                'id': 'test_charge_id',
                'amount': 1000,  # $10.00 en centavos
                'currency_code': 'PEN',
                'metadata': {
                    'odoo_reference': kwargs.get('tx_reference', 'TEST-123')
                }
            }
        }
        
        try:
            self._handle_charge_webhook(
                test_webhook_data['type'],
                test_webhook_data['data']
            )
            return {'success': True, 'message': 'Webhook de prueba procesado'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class CulqiWebsiteController(Website):
    """Extensión del controlador de website para páginas específicas de Culqi."""

    @http.route('/shop/payment/culqi', type='http', auth='public', website=True, sitemap=False)
    def shop_payment_culqi(self, **kwargs):
        """Página de pago específica para Culqi en eCommerce."""
        order = request.website.sale_get_order()
        
        if not order or not order.order_line:
            return request.redirect('/shop')
        
        # Obtener proveedor Culqi
        provider = request.env['payment.provider'].sudo().search([
            ('code', '=', 'culqi'),
            ('state', 'in', ['enabled', 'test'])
        ], limit=1)
        
        if not provider:
            raise ValidationError(_('Método de pago Culqi no disponible'))
        
        # Crear o obtener transacción
        transaction = request.env['payment.transaction'].sudo().search([
            ('sale_order_ids', 'in', order.ids),
            ('provider_id', '=', provider.id),
            ('state', 'in', ['draft', 'pending'])
        ], limit=1)
        
        if not transaction:
            transaction = order._create_payment_transaction(provider)
        
        rendering_values = transaction._get_specific_rendering_values({})
        
        return request.render('payment_culqi.shop_payment_form', {
            'transaction': transaction,
            'rendering_values': rendering_values,
            'provider': provider,
            'order': order,
        })

    @http.route('/my/payment_methods', type='http', auth='user', website=True)
    def portal_my_payment_methods(self, **kwargs):
        """Portal del cliente para gestionar métodos de pago."""
        partner = request.env.user.partner_id
        
        # Obtener cliente Culqi
        customer = request.env['culqi.customer'].search([
            ('partner_id', '=', partner.id)
        ], limit=1)
        
        cards = request.env['culqi.card']
        if customer:
            cards = customer.card_ids
        
        return request.render('payment_culqi.portal_payment_methods', {
            'customer': customer,
            'cards': cards,
            'page_name': 'payment_methods',
        })

    @http.route('/my/subscriptions', type='http', auth='user', website=True)
    def portal_my_subscriptions(self, **kwargs):
        """Portal del cliente para gestionar suscripciones."""
        partner = request.env.user.partner_id
        
        subscriptions = request.env['culqi.subscription'].search([
            ('partner_id', '=', partner.id)
        ])
        
        return request.render('payment_culqi.portal_subscriptions', {
            'subscriptions': subscriptions,
            'page_name': 'subscriptions',
        })

    @http.route('/my/subscriptions/<int:subscription_id>', type='http', auth='user', website=True)
    def portal_subscription_detail(self, subscription_id, **kwargs):
        """Detalle de una suscripción en el portal."""
        partner = request.env.user.partner_id
        
        subscription = request.env['culqi.subscription'].search([
            ('id', '=', subscription_id),
            ('partner_id', '=', partner.id)
        ])
        
        if not subscription:
            raise request.not_found()
        
        return request.render('payment_culqi.portal_subscription_detail', {
            'subscription': subscription,
            'page_name': 'subscription_detail',
        })