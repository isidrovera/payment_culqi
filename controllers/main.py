# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import pprint
import requests

from werkzeug.exceptions import Forbidden
from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class CulqiController(http.Controller):
    _complete_url = '/payment/culqi/confirm'
    _webhook_url = '/payment/culqi/webhook/'
    _process_card_url = '/payment/culqi/process_card'

    @http.route(_complete_url, type='json', auth='public', methods=['POST'])
    def culqi_confirm_order(self, provider_id, token, reference=None):
        """ Procesa el token recibido del frontend y ejecuta el cobro vía Culqi API.

        :param int provider_id: ID del proveedor 'culqi' (payment.provider)
        :param str token: Token generado en el frontend (tarjeta, yape, etc.)
        :param str reference: Referencia de la transacción Odoo
        :return: dict con redirect_url
        """
        try:
            _logger.info("🚀 Confirmando pago Culqi - Provider: %s, Token: %s, Referencia: %s", 
                        provider_id, token[:12] + '***' if token else 'None', reference)
            
            provider = request.env['payment.provider'].browse(provider_id).sudo()
            if not provider or provider.code != 'culqi':
                return {'success': False, 'error': 'Proveedor Culqi no encontrado'}

            tx = None

            # Buscar transacción de múltiples maneras
            if reference:
                # Método 1: Búsqueda estándar
                try:
                    tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                        'culqi', {'metadata': {'tx_ref': reference}}
                    )
                except Exception as e:
                    _logger.warning("⚠️ Búsqueda estándar falló: %s", e)
                
                # Método 2: Búsqueda directa por referencia
                if not tx:
                    tx = request.env['payment.transaction'].sudo().search([
                        ('reference', '=', reference),
                        ('provider_id', '=', provider_id)
                    ], limit=1)
                
                # Método 3: Búsqueda por referencia que contenga parte del reference
                if not tx and 'INV-' in reference:
                    invoice_id = reference.split('-')[2] if len(reference.split('-')) > 2 else None
                    if invoice_id:
                        tx = request.env['payment.transaction'].sudo().search([
                            ('reference', 'ilike', invoice_id),
                            ('provider_id', '=', provider_id),
                            ('state', 'in', ['draft', 'pending'])
                        ], limit=1)

            # Método 4: Buscar transacción pendiente más reciente
            if not tx:
                _logger.info("🔍 Buscando transacción pendiente más reciente para proveedor %s", provider_id)
                tx = request.env['payment.transaction'].sudo().search([
                    ('provider_id', '=', provider_id),
                    ('state', 'in', ['draft', 'pending']),
                ], order='create_date desc', limit=1)

            if not tx:
                _logger.error("❌ No se encontró transacción válida")
                return {'success': False, 'error': 'Transacción no encontrada'}

            _logger.info("✅ Transacción encontrada: %s (ID: %s, Estado: %s)", tx.reference, tx.id, tx.state)

            processing_values = {
                'culqi_token': token,
            }

            # Procesar el pago
            tx._process_direct_payment(processing_values)
            
            # Determinar URL de redirección
            redirect_url = '/payment/status'
            if hasattr(tx, 'return_url') and tx.return_url:
                redirect_url = tx.return_url
            elif hasattr(tx, 'landing_route') and tx.landing_route:
                redirect_url = tx.landing_route

            _logger.info("🎉 Pago procesado exitosamente, redirigiendo a: %s", redirect_url)
            
            return {'redirect_url': redirect_url}
            
        except Exception as e:
            _logger.exception("❌ Error confirmando pago Culqi: %s", e)
            return {'success': False, 'error': str(e)}

    @http.route(_process_card_url, type='json', auth='public', methods=['POST'])
    def culqi_process_card(self, **kwargs):
        """ Procesa datos de tarjeta directamente, crea token y ejecuta el cobro.

        :param dict kwargs: Parámetros que incluyen provider_id, reference, card_data, amount
        :return: dict con success/error y redirect_url
        """
        try:
            # Extraer parámetros
            provider_id = kwargs.get('provider_id')
            reference = kwargs.get('reference')
            card_data = kwargs.get('card_data', {})
            amount = kwargs.get('amount')
            extra_info = kwargs.get('extra_info', {})

            _logger.info("🚀 Procesando tarjeta - Provider: %s, Referencia: %s, Monto: %s centavos", 
                        provider_id, reference, amount)
            _logger.info("📋 Info extra: %s", extra_info)
            
            # Validaciones básicas
            if not provider_id:
                return {'success': False, 'error': 'ID de proveedor requerido'}
            
            if not reference:
                return {'success': False, 'error': 'Referencia de transacción requerida'}
                
            if not card_data:
                return {'success': False, 'error': 'Datos de tarjeta requeridos'}
                
            if not amount:
                return {'success': False, 'error': 'Monto requerido'}

            # Obtener proveedor Culqi
            provider = request.env['payment.provider'].browse(provider_id).sudo()
            if not provider or provider.code != 'culqi':
                return {'success': False, 'error': 'Proveedor Culqi no encontrado'}

            # Obtener transacción
            tx = None
            
            # Método 1: Buscar por referencia usando el método estándar
            try:
                if reference and reference != 'NO_REFERENCE':
                    tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                        'culqi', {'metadata': {'tx_ref': reference}}
                    )
            except Exception as e:
                _logger.warning("⚠️ No se pudo obtener transacción por método estándar: %s", e)
                
            # Método 2: Buscar directamente por referencia
            if not tx and reference and reference != 'NO_REFERENCE':
                tx = request.env['payment.transaction'].sudo().search([
                    ('reference', '=', reference),
                    ('provider_id', '=', provider_id)
                ], limit=1)
                
            # Método 3: Buscar por monto y proveedor si tenemos información de la URL
            if not tx and extra_info.get('current_url'):
                current_url = extra_info['current_url']
                amount_soles = amount / 100.0
                
                # Si es una factura, buscar por monto
                if 'invoices' in current_url:
                    tx = request.env['payment.transaction'].sudo().search([
                        ('provider_id', '=', provider_id),
                        ('amount', '=', amount_soles),
                        ('state', 'in', ['draft', 'pending']),
                    ], order='create_date desc', limit=1)
                    _logger.info("🔍 Búsqueda por monto de factura: %s soles", amount_soles)
                    
            # Método 4: Buscar la transacción más reciente del proveedor en estado pendiente
            if not tx:
                _logger.info("🔍 Buscando transacción pendiente más reciente para proveedor %s", provider_id)
                tx = request.env['payment.transaction'].sudo().search([
                    ('provider_id', '=', provider_id),
                    ('state', 'in', ['draft', 'pending']),
                ], order='create_date desc', limit=1)
                
            if not tx:
                return {'success': False, 'error': f'No se encontró transacción válida para la referencia: {reference}'}

            _logger.info("✅ Transacción encontrada: %s (ID: %s, Estado: %s)", tx.reference, tx.id, tx.state)

            # Crear token en Culqi API
            token_data = {
                'card_number': card_data['card_number'],
                'expiration_month': card_data['expiration_month'],
                'expiration_year': card_data['expiration_year'],
                'cvv': card_data['cvv'],
                'email': card_data['email']
            }

            _logger.info("📤 Creando token en Culqi con datos: %s", {
                'card_number': card_data['card_number'][:4] + '****',
                'expiration_month': card_data['expiration_month'],
                'expiration_year': card_data['expiration_year'],
                'email': card_data['email']
            })

            # Llamar a API de Culqi para crear token
            token_url = 'https://secure.culqi.com/v2/tokens'
            headers = {
                'Authorization': f'Bearer {provider.culqi_public_key}',
                'Content-Type': 'application/json'
            }

            token_response = requests.post(token_url, json=token_data, headers=headers, timeout=30)
            
            if token_response.status_code != 200:
                _logger.error("❌ Error creando token: %s", token_response.text)
                return {'success': False, 'error': 'Error creando token de pago'}

            token_result = token_response.json()
            culqi_token = token_result.get('id')
            
            if not culqi_token:
                _logger.error("❌ Token no recibido en respuesta: %s", token_result)
                return {'success': False, 'error': 'Token de pago no generado'}

            _logger.info("✅ Token creado exitosamente: %s", culqi_token[:12] + '***')

            # Crear cargo en Culqi
            charge_data = {
                'amount': amount,
                'currency_code': 'PEN',
                'description': f'Pago Odoo - {tx.reference}',
                'email': card_data['email'],
                'source_id': culqi_token,
                'metadata': {
                    'order_id': tx.reference,
                    'odoo_tx_id': tx.id
                }
            }

            charge_url = 'https://api.culqi.com/v2/charges'
            charge_headers = {
                'Authorization': f'Bearer {provider.culqi_secret_key}',
                'Content-Type': 'application/json'
            }

            _logger.info("💳 Creando cargo en Culqi para monto: %s centavos", amount)

            charge_response = requests.post(charge_url, json=charge_data, headers=charge_headers, timeout=30)
            
            if charge_response.status_code != 200:
                _logger.error("❌ Error creando cargo: %s", charge_response.text)
                return {'success': False, 'error': 'Error procesando el pago'}

            charge_result = charge_response.json()
            
            _logger.info("✅ Cargo creado exitosamente: %s", charge_result.get('id', 'No ID'))

            # Procesar la transacción en Odoo
            processing_values = {
                'culqi_token': culqi_token,
                'culqi_charge_id': charge_result.get('id'),
                'culqi_charge': charge_result
            }

            tx._process_direct_payment(processing_values)

            # Determinar URL de redirección
            redirect_url = '/payment/status'
            if hasattr(tx, 'return_url') and tx.return_url:
                redirect_url = tx.return_url

            _logger.info("🎉 Pago procesado exitosamente, redirigiendo a: %s", redirect_url)

            return {
                'success': True, 
                'redirect_url': redirect_url,
                'transaction_id': tx.id,
                'charge_id': charge_result.get('id')
            }

        except requests.exceptions.RequestException as e:
            _logger.exception("❌ Error de conexión con Culqi: %s", e)
            return {'success': False, 'error': 'Error de conexión con el procesador de pagos'}
        
        except Exception as e:
            _logger.exception("❌ Error inesperado procesando tarjeta: %s", e)
            return {'success': False, 'error': 'Error inesperado procesando el pago'}

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False)
    def culqi_webhook(self, **post):
        """ Procesa la notificación de Culqi (evento tipo 'charge.created', etc.)

        :return: Respuesta vacía (200 OK) para confirmar la recepción.
        """
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            event_type = data.get('type')
            charge = data.get('data', {}).get('object', {})

            _logger.info("Webhook recibido desde Culqi [%s]:\n%s", event_type, pprint.pformat(charge))

            tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'culqi', charge
            )

            tx._handle_notification_data('culqi', charge)
        except Exception as e:
            _logger.exception("Error procesando webhook de Culqi: %s", e)
            raise Forbidden(description="Webhook no válido o incompleto.")

        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])