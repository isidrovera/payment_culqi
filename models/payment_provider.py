# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import requests
import time
import pprint

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

    def _log_process_start(self, process_name, **kwargs):
        """Helper para loggear inicio de proceso con timestamp"""
        _logger.info("=" * 80)
        _logger.info("🚀 INICIANDO PROCESO: %s", process_name)
        _logger.info("⏰ Timestamp: %s", time.strftime('%Y-%m-%d %H:%M:%S'))
        _logger.info("🏢 Proveedor: %s (ID: %s)", self.name, self.id)
        _logger.info("🔧 Estado: %s", self.state)
        for key, value in kwargs.items():
            if 'key' in key.lower() and value:
                _logger.info("📋 %s: %s", key, str(value)[:8] + '***')
            elif 'secret' in key.lower() and value:
                _logger.info("📋 %s: %s", key, str(value)[:8] + '***')
            else:
                _logger.info("📋 %s: %s", key, value)
        _logger.info("=" * 80)

    def _log_process_end(self, process_name, success=True, **kwargs):
        """Helper para loggear fin de proceso"""
        status = "✅ COMPLETADO" if success else "❌ FALLIDO"
        _logger.info("-" * 80)
        _logger.info("%s PROCESO: %s", status, process_name)
        _logger.info("⏰ Timestamp: %s", time.strftime('%Y-%m-%d %H:%M:%S'))
        for key, value in kwargs.items():
            _logger.info("📊 %s: %s", key, value)
        _logger.info("-" * 80)

    def _culqi_make_request(self, endpoint, method='POST', payload=None, headers=None):
        """ Enviar una solicitud al API de Culqi. """
        self.ensure_one()
        start_time = time.time()
        
        self._log_process_start(
            "CULQI API REQUEST",
            endpoint=endpoint,
            method=method,
            payload_keys=list(payload.keys()) if payload else "None",
            headers_keys=list(headers.keys()) if headers else "None"
        )
        
        try:
            # Paso 1: Preparar URL y headers
            _logger.info("🔍 PASO 1: Preparando solicitud...")
            url = 'https://api.culqi.com/v2' + endpoint
            _logger.info("🌐 URL destino: %s", url)
            
            auth_headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.culqi_secret_key}',
            }
            
            if headers:
                _logger.info("📋 Headers adicionales proporcionados: %s", list(headers.keys()))
                auth_headers.update(headers)
            
            # Log headers sin exponer claves sensibles
            safe_headers = {}
            for key, value in auth_headers.items():
                if key == 'Authorization':
                    safe_headers[key] = f"Bearer {str(value)[7:15]}***"
                else:
                    safe_headers[key] = value
            _logger.info("📤 Headers finales: %s", safe_headers)
            
            # Log payload si existe
            if payload:
                _logger.info("📦 Payload a enviar: %s", pprint.pformat(payload))
            else:
                _logger.info("📦 Sin payload")
            
            _logger.info("✅ PASO 1 COMPLETADO: Solicitud preparada")
            
            # Paso 2: Realizar solicitud HTTP
            _logger.info("🔍 PASO 2: Realizando solicitud HTTP...")
            _logger.info("⚙️ Método: %s", method)
            _logger.info("⚙️ Timeout: 10 segundos")
            
            response = requests.request(
                method,
                url,
                json=payload,
                headers=auth_headers,
                timeout=10
            )
            
            elapsed_time = time.time() - start_time
            _logger.info("✅ PASO 2 COMPLETADO: Respuesta recibida en %.2fs", elapsed_time)
            
            # Paso 3: Analizar respuesta
            _logger.info("🔍 PASO 3: Analizando respuesta...")
            _logger.info("📥 Status Code: %s", response.status_code)
            _logger.info("📥 Headers de respuesta: %s", dict(response.headers))
            _logger.info("📥 Tamaño de respuesta: %s bytes", len(response.content))
            
            # Intentar parsear respuesta como JSON
            try:
                response_json = response.json()
                _logger.info("📋 Respuesta JSON: %s", pprint.pformat(response_json))
            except:
                _logger.info("📋 Respuesta (texto): %s", response.text[:500])
            
            # Verificar si hay errores HTTP
            try:
                response.raise_for_status()
                _logger.info("✅ PASO 3 COMPLETADO: Respuesta HTTP exitosa")
                
                # Proceso completado exitosamente
                self._log_process_end(
                    "CULQI API REQUEST",
                    True,
                    status_code=response.status_code,
                    response_size=f"{len(response.content)} bytes",
                    elapsed_time=f"{elapsed_time:.2f}s"
                )
                
                return response.json()
                
            except requests.exceptions.HTTPError as e:
                _logger.error("❌ Error HTTP: %s", e)
                _logger.error("📋 Respuesta de error: %s", response.text)
                
                self._log_process_end(
                    "CULQI API REQUEST",
                    False,
                    error="HTTP Error",
                    status_code=response.status_code,
                    error_detail=str(e),
                    elapsed_time=f"{elapsed_time:.2f}s"
                )
                
                raise ValidationError(_("Culqi: Error de comunicación con la API: %s") % e)
                
        except requests.exceptions.Timeout as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Timeout en solicitud a Culqi: %s", e)
            
            self._log_process_end(
                "CULQI API REQUEST",
                False,
                error="Timeout",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            raise ValidationError(_("Culqi: Tiempo de espera agotado conectando con la API."))
            
        except requests.exceptions.ConnectionError as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error de conexión a Culqi: %s", e)
            
            self._log_process_end(
                "CULQI API REQUEST",
                False,
                error="Connection Error",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            raise ValidationError(_("Culqi: No se pudo conectar con la API."))
            
        except requests.exceptions.RequestException as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error de solicitud a Culqi: %s", e)
            
            self._log_process_end(
                "CULQI API REQUEST",
                False,
                error="Request Exception",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            raise ValidationError(_("Culqi: No se pudo conectar con la API."))

    def _get_default_payment_method_codes(self):
        """ Añade el método Culqi como predeterminado si corresponde. """
        _logger.info("🔍 Obteniendo códigos de métodos de pago predeterminados para proveedor: %s", self.code)
        
        default_codes = super()._get_default_payment_method_codes()
        _logger.info("📋 Códigos base obtenidos: %s", default_codes)
        
        if self.code == 'culqi':
            updated_codes = default_codes | {'culqi', 'card'}
            _logger.info("✅ Códigos actualizados para Culqi: %s", updated_codes)
            return updated_codes
            
        _logger.info("📋 Códigos finales sin cambios: %s", default_codes)
        return default_codes

    def _get_supported_currencies(self):
        """ Culqi soporta solo PEN y USD. """
        _logger.info("🔍 Obteniendo monedas soportadas para proveedor: %s", self.code)
        
        supported = super()._get_supported_currencies()
        _logger.info("📋 Monedas base soportadas: %s", [c.name for c in supported])
        
        if self.code == 'culqi':
            filtered_currencies = supported.filtered(lambda c: c.name in ('PEN', 'USD'))
            currency_names = [c.name for c in filtered_currencies]
            _logger.info("✅ Monedas filtradas para Culqi: %s", currency_names)
            
            if not filtered_currencies:
                _logger.warning("⚠️ No se encontraron monedas PEN o USD en el sistema")
            
            return filtered_currencies
            
        _logger.info("📋 Monedas finales sin filtrar: %s", [c.name for c in supported])
        return supported
        
    def action_culqi_check_connection(self):
        """Probar conexión con Culqi con mejor manejo de respuestas"""
        self.ensure_one()
        start_time = time.time()
        
        self._log_process_start(
            "CULQI CONNECTION TEST",
            provider_code=self.code,
            provider_name=self.name,
            has_secret_key=bool(self.culqi_secret_key),
            has_public_key=bool(self.culqi_public_key)
        )
        
        try:
            # Paso 1: Validaciones previas
            _logger.info("🔍 PASO 1: Validaciones previas...")
            
            if self.code != 'culqi':
                _logger.error("❌ Proveedor no es Culqi: %s", self.code)
                raise UserError(_("Este método solo funciona para proveedores Culqi"))

            if not self.culqi_secret_key:
                _logger.error("❌ Clave secreta no configurada")
                raise UserError(_("❌ Falta configurar la clave secreta de Culqi"))
                
            _logger.info("✅ PASO 1 COMPLETADO: Validaciones pasaron")
            _logger.info("🔑 Clave secreta presente: %s caracteres", len(self.culqi_secret_key))
            
            # Paso 2: Preparar solicitud de prueba
            _logger.info("🔍 PASO 2: Preparando solicitud de prueba...")
            
            headers = {
                'Authorization': f'Bearer {self.culqi_secret_key}',
                'Content-Type': 'application/json',
            }
            
            # Probar con endpoint más básico
            url = 'https://api.culqi.com/v2/charges'
            _logger.info("🌐 URL de prueba: %s", url)
            _logger.info("📤 Headers preparados (clave oculta)")
            
            _logger.info("✅ PASO 2 COMPLETADO: Solicitud preparada")
            
            # Paso 3: Realizar solicitud de prueba
            _logger.info("🔍 PASO 3: Realizando solicitud de prueba...")
            _logger.info("⚙️ Timeout: 10 segundos")
            
            response = requests.get(url, headers=headers, timeout=10)
            
            elapsed_time = time.time() - start_time
            _logger.info("📥 Respuesta recibida en %.2fs", elapsed_time)
            _logger.info("📊 Status Code: %s", response.status_code)
            _logger.info("📊 Headers de respuesta: %s", dict(response.headers))
            
            # Log de respuesta (limitando tamaño)
            response_text = response.text[:500] if len(response.text) > 500 else response.text
            _logger.info("📋 Respuesta (primeros 500 chars): %s", response_text)
            
            _logger.info("✅ PASO 3 COMPLETADO: Solicitud realizada")
            
            # Paso 4: Interpretar resultado
            _logger.info("🔍 PASO 4: Interpretando resultado...")
            
            success_message = None
            
            if response.status_code == 200:
                _logger.info("✅ Conexión completamente exitosa (200 OK)")
                success_message = "✅ Conexión exitosa con Culqi"
                
            elif response.status_code == 401:
                _logger.error("❌ Clave secreta incorrecta (401 Unauthorized)")
                self._log_process_end(
                    "CULQI CONNECTION TEST",
                    False,
                    error="Unauthorized",
                    status_code=response.status_code,
                    elapsed_time=f"{elapsed_time:.2f}s"
                )
                raise UserError(_("❌ Clave secreta de Culqi incorrecta"))
                
            elif response.status_code == 403:
                _logger.info("✅ Clave secreta válida pero acceso restringido (403 Forbidden)")
                success_message = "✅ Clave secreta válida (acceso restringido)"
                
            else:
                _logger.warning("⚠️ Respuesta inesperada: %s", response.status_code)
                self._log_process_end(
                    "CULQI CONNECTION TEST",
                    False,
                    warning="Unexpected response",
                    status_code=response.status_code,
                    elapsed_time=f"{elapsed_time:.2f}s"
                )
                raise UserError(_("⚠️ Culqi respondió con código %s:\n%s") % (response.status_code, response_text))
            
            _logger.info("✅ PASO 4 COMPLETADO: Resultado interpretado")
            
            # Proceso completado exitosamente
            self._log_process_end(
                "CULQI CONNECTION TEST",
                True,
                status_code=response.status_code,
                message=success_message,
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            raise UserError(_(success_message))
                
        except UserError:
            # Re-lanzar UserErrors sin modificar (ya loggeados arriba)
            raise
            
        except requests.exceptions.ConnectionError as e:
            elapsed_time = time.time() - start_time
            _logger.error("❌ Error de conexión: %s", e)
            
            self._log_process_end(
                "CULQI CONNECTION TEST",
                False,
                error="Connection Error",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            raise UserError(_("❌ No se pudo conectar con Culqi. Verificar conexión a internet"))
            
        except requests.exceptions.Timeout as e:
            elapsed_time = time.time() - start_time
            _logger.error("❌ Timeout: %s", e)
            
            self._log_process_end(
                "CULQI CONNECTION TEST",
                False,
                error="Timeout",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            raise UserError(_("❌ Tiempo de espera agotado conectando con Culqi"))
            
        except requests.exceptions.RequestException as e:
            elapsed_time = time.time() - start_time
            _logger.error("❌ Error de requests: %s", e)
            
            self._log_process_end(
                "CULQI CONNECTION TEST",
                False,
                error="Request Exception",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            raise UserError(_("❌ Error de red: %s") % str(e))
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            _logger.error("❌ Error inesperado: %s", e)
            
            self._log_process_end(
                "CULQI CONNECTION TEST",
                False,
                error="Unexpected Error",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            raise UserError(_("❌ Error inesperado: %s") % str(e))