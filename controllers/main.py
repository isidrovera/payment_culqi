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
        :return: None
        """
        provider = request.env['payment.provider'].browse(provider_id).sudo()
        tx = None

        if reference:
            tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'culqi', {'metadata': {'tx_ref': reference}}
            )

        processing_values = {
            'culqi_token': token,
        }

        if tx:
            tx._process_direct_payment(processing_values)
        return {}

    @http.route(_process_card_url, type='json', auth='public', methods=['POST'])
    def culqi_process_card(self, provider_id, reference, card_data, amount):
        """ Procesa datos de tarjeta directamente, crea token y ejecuta el cobro.

        :param int provider_id: ID del proveedor 'culqi'
        :param str reference: Referencia de la transacción Odoo
        :param dict card_data: Datos de la tarjeta (card_number, expiration_month, etc.)
        :param int amount: Monto en centavos
        :return: dict con success/error y redirect_url
        """
        try:
            _logger.info("🚀 Procesando tarjeta para referencia: %s, monto: %s centavos", reference, amount)
            
            # Obtener proveedor Culqi
            provider = request.env['payment.provider'].browse(provider_id).sudo()
            if not provider or provider.code != 'culqi':
                return {'success': False, 'error': 'Proveedor Culqi no encontrado'}

            # Obtener transacción
            tx = None
            if reference:
                tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                    'culqi', {'metadata': {'tx_ref': reference}}
                )
            
            if not tx:
                return {'success': False, 'error': 'Transacción no encontrada'}

            _logger.info("✅ Transacción encontrada: %s", tx.reference)

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