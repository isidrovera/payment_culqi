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
            return request.redirect