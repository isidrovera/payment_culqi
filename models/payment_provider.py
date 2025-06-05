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

    # Campos obligatorios para Culqi
    culqi_public_key = fields.Char(
        string="Culqi Public Key",
        required_if_provider='culqi',
        help="Clave pública de Culqi para el frontend"
    )
    culqi_secret_key = fields.Char(
        string="Culqi Secret Key",
        required_if_provider='culqi',
        groups='base.group_system',
        help="Clave secreta de Culqi para el backend"
    )
    
    # Campos para personalización del checkout (nuevos)
    culqi_logo_url = fields.Char(
        string="Logo URL",
        help="URL del logo a mostrar en el checkout de Culqi (opcional)"
    )
    culqi_banner_color = fields.Char(
        string="Color del Banner",
        help="Color hexadecimal para el banner (ej: #0033A0)",
        default="#0033A0"
    )
    culqi_button_color = fields.Char(
        string="Color del Botón",
        help="Color hexadecimal para el botón de pago (ej: #0033A0)",
        default="#0033A0"
    )
    
    # Campos para cifrado RSA (opcionales)
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
            return default_codes | {'culqi', 'card'}  # Agregamos 'card' también
        return default_codes

    def _get_supported_currencies(self):
        """ Culqi soporta solo PEN y USD. """
        supported = super()._get_supported_currencies()
        if self.code == 'culqi':
            return supported.filtered(lambda c: c.name in ('PEN', 'USD'))
        return supported
        
    def action_culqi_check_connection(self):
        """Probar conexión con Culqi con mejor manejo de respuestas"""
        self.ensure_one()
        if self.code != 'culqi':
            raise UserError(_("Este método solo funciona para proveedores Culqi"))

        if not self.culqi_secret_key:
            raise UserError(_("❌ Falta configurar la clave secreta de Culqi"))

        headers = {
            'Authorization': f'Bearer {self.culqi_secret_key}',
            'Content-Type': 'application/json',
        }

        # Probar con endpoint más básico
        url = 'https://api.culqi.com/v2/charges'

        try:
            _logger.info(f"Probando conexión con Culqi usando clave: {self.culqi_secret_key[:10]}...")
            
            response = requests.get(url, headers=headers, timeout=10)
            _logger.info(f"Respuesta de Culqi: {response.status_code} - {response.text[:200]}")
            
            if response.status_code == 200:
                raise UserError(_("✅ Conexión exitosa con Culqi"))
            elif response.status_code == 401:
                raise UserError(_("❌ Clave secreta de Culqi incorrecta"))
            elif response.status_code == 403:
                raise UserError(_("✅ Clave secreta válida (acceso restringido)"))
            else:
                raise UserError(_("⚠️ Culqi respondió con código %s:\n%s") % (response.status_code, response.text))
                
        except UserError:
            # Re-lanzar UserErrors sin modificar
            raise
        except requests.exceptions.ConnectionError as e:
            _logger.error(f"Error de conexión: {e}")
            raise UserError(_("❌ No se pudo conectar con Culqi. Verificar conexión a internet"))
        except requests.exceptions.Timeout as e:
            _logger.error(f"Timeout: {e}")
            raise UserError(_("❌ Tiempo de espera agotado conectando con Culqi"))
        except requests.exceptions.RequestException as e:
            _logger.error(f"Error de requests: {e}")
            raise UserError(_("❌ Error de red: %s") % str(e))
        except Exception as e:
            _logger.error(f"Error inesperado: {e}")
            raise UserError(_("❌ Error inesperado: %s") % str(e))