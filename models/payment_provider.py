# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('culqi', "Culqi")],
        ondelete={'culqi': 'set default'}
    )

    culqi_public_key = fields.Char(
        string="Culqi Public Key",
        required_if_provider='culqi'
    )
    culqi_secret_key = fields.Char(
        string="Culqi Secret Key",
        required_if_provider='culqi',
        groups='base.group_system'
    )
    culqi_rsa_id = fields.Char(
        string="Culqi RSA ID",
        help="ID de la llave pública RSA (para cifrado de payloads)"
    )
    culqi_rsa_public_key = fields.Text(
        string="Culqi RSA Public Key",
        help="Llave pública en formato PEM, obtenida desde el panel de Culqi"
    )

    def _culqi_make_request(self, endpoint, method='POST', payload=None, headers=None):
        """ Enviar una solicitud al API de Culqi. """
        self.ensure_one()
        url = 'https://api.culqi.com/v2' + endpoint
        auth_headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.culqi_secret_key}',
        }
        if headers:
            auth_headers.update(headers)
        try:
            response = requests.request(
                method,
                url,
                json=payload,
                headers=auth_headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            _logger.exception("Culqi API error: %s", e)
            raise ValidationError(_("Culqi: Error de comunicación con la API: %s") % e)
        except requests.exceptions.RequestException as e:
            _logger.exception("Culqi API unreachable: %s", e)
            raise ValidationError(_("Culqi: No se pudo conectar con la API."))

    def _get_default_payment_method_codes(self):
        """ Añade el método Culqi como predeterminado si corresponde. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code == 'culqi':
            return default_codes | {'culqi'}
        return default_codes

    def _get_supported_currencies(self):
        """ Culqi soporta solo PEN y USD. """
        supported = super()._get_supported_currencies()
        if self.code == 'culqi':
            return supported.filtered(lambda c: c.name in ('PEN', 'USD'))
        return supported
    def action_culqi_check_connection(self):
        self.ensure_one()
        if self.code != 'culqi':
            return

        headers = {
            'Authorization': f'Bearer {self.culqi_secret_key}',
            'Content-Type': 'application/json',
        }

        # Culqi recomienda probar con GET /v1/charges o /v1/orders
        url = 'https://api.culqi.com/v2/orders'

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                raise UserError(_("✅ Conexión exitosa con Culqi."))
            else:
                raise UserError(_("❌ Culqi respondió con error:\n%s") % response.text)
        except Exception as e:
            raise UserError(_("❌ No se pudo conectar con Culqi:\n%s") % str(e))