# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    culqi_charge_id = fields.Char(string="Culqi Charge ID", readonly=True)

    def _get_specific_processing_values(self, processing_values):
        """Preparar los datos necesarios para procesar un pago con Culqi."""
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'culqi':
            return res

        # En este punto se espera que el token de la tarjeta ya se haya generado en frontend
        token = processing_values.get('culqi_token')
        if not token:
            raise ValidationError(_("Culqi: Token no recibido para la transacción."))

        payload = {
            'amount': int(self.amount * 100),  # Monto en centavos
            'currency_code': self.currency_id.name,
            'email': self.partner_email or self.partner_id.email,
            'source_id': token,
            'metadata': {
                'tx_ref': self.reference,
            }
        }

        _logger.info("Enviando solicitud a Culqi para capturar transacción %s:\n%s", self.reference, pprint.pformat(payload))

        charge = self.provider_id._culqi_make_request('/charges', payload=payload)
        self._process_culqi_response(charge)

        return {}

    def _process_culqi_response(self, response):
        """Interpretar la respuesta de Culqi y actualizar la transacción."""
        self.ensure_one()
        self.culqi_charge_id = response.get('id')
        self.provider_reference = response.get('id')

        if response.get('outcome', {}).get('type') == 'venta_exitosa':
            self._set_done()
        elif response.get('outcome', {}).get('type') == 'venta_rechazada':
            self._set_error(_("Pago rechazado por Culqi."))
        else:
            self._set_pending(_("Esperando confirmación de pago."))

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'culqi' or len(tx) == 1:
            return tx

        reference = notification_data.get('metadata', {}).get('tx_ref')
        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'culqi')])
        if not tx:
            raise ValidationError(_("Culqi: No se encontró la transacción con referencia %s.") % reference)
        return tx

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)
        if self.provider_code != 'culqi':
            return

        status = notification_data.get('outcome', {}).get('type')
        self.culqi_charge_id = notification_data.get('id')
        self.provider_reference = notification_data.get('id')

        if status == 'venta_exitosa':
            self._set_done()
        elif status == 'venta_rechazada':
            self._set_error(_("Pago rechazado por Culqi."))
        else:
            self._set_pending(_("Estado del pago: %s") % status)
