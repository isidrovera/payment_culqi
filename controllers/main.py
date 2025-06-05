# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import pprint

from werkzeug.exceptions import Forbidden
from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class CulqiController(http.Controller):
    _complete_url = '/payment/culqi/confirm'
    _webhook_url = '/payment/culqi/webhook/'

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
