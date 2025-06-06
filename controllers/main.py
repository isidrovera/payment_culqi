# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import pprint
import requests
import time

from werkzeug.exceptions import Forbidden
from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class CulqiController(http.Controller):
    _complete_url = '/payment/culqi/confirm'
    _webhook_url = '/payment/culqi/webhook/'
    _process_card_url = '/payment/culqi/process_card'

    def _log_process_start(self, process_name, **kwargs):
        """Helper para loggear inicio de proceso con timestamp"""
        _logger.info("=" * 80)
        _logger.info("🚀 INICIANDO PROCESO: %s", process_name)
        _logger.info("⏰ Timestamp: %s", time.strftime('%Y-%m-%d %H:%M:%S'))
        for key, value in kwargs.items():
            if 'token' in key.lower() and value:
                _logger.info("📋 %s: %s", key, str(value)[:12] + '***')
            elif 'key' in key.lower() and value:
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

    @http.route(_complete_url, type='json', auth='public', methods=['POST'])
    def culqi_confirm_order(self, provider_id, token, reference=None):
        """ Procesa el token recibido del frontend y ejecuta el cobro vía Culqi API.

        :param int provider_id: ID del proveedor 'culqi' (payment.provider)
        :param str token: Token generado en el frontend (tarjeta, yape, etc.)
        :param str reference: Referencia de la transacción Odoo
        :return: dict con redirect_url
        """
        start_time = time.time()
        
        self._log_process_start(
            "CULQI CONFIRM ORDER",
            provider_id=provider_id,
            token=token,
            reference=reference
        )
        
        try:
            # Paso 1: Validar proveedor
            _logger.info("🔍 PASO 1: Validando proveedor Culqi...")
            provider = request.env['payment.provider'].browse(provider_id).sudo()
            
            if not provider:
                _logger.error("❌ Proveedor no encontrado con ID: %s", provider_id)
                return {'success': False, 'error': 'Proveedor no encontrado'}
                
            if provider.code != 'culqi':
                _logger.error("❌ Proveedor no es Culqi: %s", provider.code)
                return {'success': False, 'error': 'Proveedor Culqi no encontrado'}
                
            _logger.info("✅ Proveedor Culqi válido encontrado: %s (ID: %s)", provider.name, provider.id)
            _logger.info("🔧 Configuración proveedor - Estado: %s, Modo: %s", 
                        provider.state, 'test' if provider.state == 'test' else 'producción')

            tx = None

            # Paso 2: Buscar transacción
            _logger.info("🔍 PASO 2: Buscando transacción...")
            
            if reference:
                _logger.info("📝 Referencia proporcionada: %s", reference)
                
                # Método 1: Búsqueda estándar
                _logger.info("🔎 Método 1: Búsqueda estándar por notificación...")
                try:
                    tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                        'culqi', {'metadata': {'tx_ref': reference}}
                    )
                    if tx:
                        _logger.info("✅ Transacción encontrada por método estándar: %s", tx.reference)
                    else:
                        _logger.info("⚠️ Método estándar no devolvió resultados")
                except Exception as e:
                    _logger.warning("⚠️ Búsqueda estándar falló: %s", e)
                
                # Método 2: Búsqueda directa por referencia
                if not tx:
                    _logger.info("🔎 Método 2: Búsqueda directa por referencia...")
                    tx = request.env['payment.transaction'].sudo().search([
                        ('reference', '=', reference),
                        ('provider_id', '=', provider_id)
                    ], limit=1)
                    
                    if tx:
                        _logger.info("✅ Transacción encontrada por búsqueda directa: %s", tx.reference)
                    else:
                        _logger.info("⚠️ Búsqueda directa no devolvió resultados")
                
                # Método 3: Búsqueda por referencia que contenga parte del reference
                if not tx and 'INV-' in reference:
                    _logger.info("🔎 Método 3: Búsqueda por parte de referencia de factura...")
                    invoice_id = reference.split('-')[2] if len(reference.split('-')) > 2 else None
                    if invoice_id:
                        _logger.info("📋 ID de factura extraído: %s", invoice_id)
                        tx = request.env['payment.transaction'].sudo().search([
                            ('reference', 'ilike', invoice_id),
                            ('provider_id', '=', provider_id),
                            ('state', 'in', ['draft', 'pending'])
                        ], limit=1)
                        
                        if tx:
                            _logger.info("✅ Transacción encontrada por ID de factura: %s", tx.reference)
                        else:
                            _logger.info("⚠️ Búsqueda por ID de factura no devolvió resultados")

            # Método 4: Buscar transacción pendiente más reciente
            if not tx:
                _logger.info("🔎 Método 4: Búsqueda de transacción pendiente más reciente...")
                tx = request.env['payment.transaction'].sudo().search([
                    ('provider_id', '=', provider_id),
                    ('state', 'in', ['draft', 'pending']),
                ], order='create_date desc', limit=1)
                
                if tx:
                    _logger.info("✅ Transacción pendiente encontrada: %s", tx.reference)
                else:
                    _logger.info("⚠️ No se encontraron transacciones pendientes")

            if not tx:
                _logger.error("❌ PASO 2 FALLIDO: No se encontró transacción válida")
                self._log_process_end("CULQI CONFIRM ORDER", False, error="Transacción no encontrada")
                return {'success': False, 'error': 'Transacción no encontrada'}

            # Log detalles de la transacción encontrada
            _logger.info("✅ PASO 2 COMPLETADO: Transacción encontrada")
            _logger.info("📊 Detalles de transacción:")
            _logger.info("   - ID: %s", tx.id)
            _logger.info("   - Referencia: %s", tx.reference)
            _logger.info("   - Estado: %s", tx.state)
            _logger.info("   - Monto: %s %s", tx.amount, tx.currency_id.name if tx.currency_id else 'N/A')
            _logger.info("   - Fecha creación: %s", tx.create_date)
            _logger.info("   - Proveedor: %s", tx.provider_id.name)

            # Paso 3: Procesar el pago
            _logger.info("🔍 PASO 3: Procesando el pago...")
            processing_values = {
                'culqi_token': token,
            }
            _logger.info("📦 Valores de procesamiento: %s", {
                'culqi_token': token[:12] + '***' if token else 'None'
            })

            # Procesar el pago
            _logger.info("⚙️ Ejecutando _process_direct_payment...")
            tx._process_direct_payment(processing_values)
            _logger.info("✅ PASO 3 COMPLETADO: Pago procesado exitosamente")
            
            # Paso 4: Determinar URL de redirección
            _logger.info("🔍 PASO 4: Determinando URL de redirección...")
            redirect_url = '/payment/status'
            
            if hasattr(tx, 'return_url') and tx.return_url:
                redirect_url = tx.return_url
                _logger.info("🔗 URL de retorno encontrada en transacción: %s", redirect_url)
            elif hasattr(tx, 'landing_route') and tx.landing_route:
                redirect_url = tx.landing_route
                _logger.info("🔗 Ruta de aterrizaje encontrada en transacción: %s", redirect_url)
            else:
                _logger.info("🔗 Usando URL de redirección por defecto: %s", redirect_url)

            _logger.info("✅ PASO 4 COMPLETADO: URL de redirección determinada")

            # Proceso completado exitosamente
            elapsed_time = time.time() - start_time
            self._log_process_end(
                "CULQI CONFIRM ORDER", 
                True,
                redirect_url=redirect_url,
                transaction_id=tx.id,
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            
            return {'redirect_url': redirect_url}
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error confirmando pago Culqi: %s", e)
            self._log_process_end(
                "CULQI CONFIRM ORDER", 
                False, 
                error=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            return {'success': False, 'error': str(e)}

    @http.route(_process_card_url, type='json', auth='public', methods=['POST'])
    def culqi_process_card(self, **kwargs):
        """ Procesa datos de tarjeta directamente, crea token y ejecuta el cobro.

        :param dict kwargs: Parámetros que incluyen provider_id, reference, card_data, amount
        :return: dict con success/error y redirect_url
        """
        start_time = time.time()
        
        # Extraer parámetros
        provider_id = kwargs.get('provider_id')
        reference = kwargs.get('reference')
        card_data = kwargs.get('card_data', {})
        amount = kwargs.get('amount')
        extra_info = kwargs.get('extra_info', {})

        self._log_process_start(
            "CULQI PROCESS CARD",
            provider_id=provider_id,
            reference=reference,
            amount=f"{amount} centavos" if amount else "No definido",
            card_data_keys=list(card_data.keys()) if card_data else "No definido",
            extra_info=extra_info
        )

        try:
            # Paso 1: Validaciones básicas
            _logger.info("🔍 PASO 1: Validaciones básicas...")
            
            if not provider_id:
                _logger.error("❌ ID de proveedor no proporcionado")
                return {'success': False, 'error': 'ID de proveedor requerido'}
            _logger.info("✅ Provider ID válido: %s", provider_id)
            
            if not reference:
                _logger.error("❌ Referencia de transacción no proporcionada")
                return {'success': False, 'error': 'Referencia de transacción requerida'}
            _logger.info("✅ Referencia válida: %s", reference)
                
            if not card_data:
                _logger.error("❌ Datos de tarjeta no proporcionados")
                return {'success': False, 'error': 'Datos de tarjeta requeridos'}
            _logger.info("✅ Datos de tarjeta proporcionados: %s", list(card_data.keys()))
                
            if not amount:
                _logger.error("❌ Monto no proporcionado")
                return {'success': False, 'error': 'Monto requerido'}
            _logger.info("✅ Monto válido: %s centavos (%.2f soles)", amount, amount/100.0)

            _logger.info("✅ PASO 1 COMPLETADO: Todas las validaciones básicas pasaron")

            # Paso 2: Obtener proveedor Culqi
            _logger.info("🔍 PASO 2: Obteniendo proveedor Culqi...")
            provider = request.env['payment.provider'].browse(provider_id).sudo()
            
            if not provider:
                _logger.error("❌ Proveedor no encontrado con ID: %s", provider_id)
                return {'success': False, 'error': 'Proveedor no encontrado'}
                
            if provider.code != 'culqi':
                _logger.error("❌ Proveedor no es Culqi: %s", provider.code)
                return {'success': False, 'error': 'Proveedor Culqi no encontrado'}

            _logger.info("✅ PASO 2 COMPLETADO: Proveedor Culqi válido")
            _logger.info("📊 Detalles del proveedor:")
            _logger.info("   - Nombre: %s", provider.name)
            _logger.info("   - Estado: %s", provider.state)
            _logger.info("   - Código: %s", provider.code)
            _logger.info("   - Clave pública configurada: %s", bool(provider.culqi_public_key))
            _logger.info("   - Clave secreta configurada: %s", bool(provider.culqi_secret_key))

            # Paso 3: Obtener transacción
            _logger.info("🔍 PASO 3: Obteniendo transacción...")
            tx = None
            
            # Método 1: Buscar por referencia usando el método estándar
            if reference and reference != 'NO_REFERENCE':
                _logger.info("🔎 Método 1: Búsqueda estándar por notificación...")
                try:
                    tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                        'culqi', {'metadata': {'tx_ref': reference}}
                    )
                    if tx:
                        _logger.info("✅ Transacción encontrada por método estándar")
                    else:
                        _logger.info("⚠️ Método estándar no devolvió resultados")
                except Exception as e:
                    _logger.warning("⚠️ No se pudo obtener transacción por método estándar: %s", e)
                
            # Método 2: Buscar directamente por referencia
            if not tx and reference and reference != 'NO_REFERENCE':
                _logger.info("🔎 Método 2: Búsqueda directa por referencia...")
                tx = request.env['payment.transaction'].sudo().search([
                    ('reference', '=', reference),
                    ('provider_id', '=', provider_id)
                ], limit=1)
                
                if tx:
                    _logger.info("✅ Transacción encontrada por búsqueda directa")
                else:
                    _logger.info("⚠️ Búsqueda directa no devolvió resultados")
                
            # Método 3: Buscar por monto y proveedor si tenemos información de la URL
            if not tx and extra_info.get('current_url'):
                _logger.info("🔎 Método 3: Búsqueda por monto y URL...")
                current_url = extra_info['current_url']
                amount_soles = amount / 100.0
                _logger.info("📋 URL actual: %s", current_url)
                _logger.info("📋 Monto en soles: %.2f", amount_soles)
                
                # Si es una factura, buscar por monto
                if 'invoices' in current_url:
                    _logger.info("🔎 Detectada factura en URL, buscando por monto...")
                    tx = request.env['payment.transaction'].sudo().search([
                        ('provider_id', '=', provider_id),
                        ('amount', '=', amount_soles),
                        ('state', 'in', ['draft', 'pending']),
                    ], order='create_date desc', limit=1)
                    
                    if tx:
                        _logger.info("✅ Transacción encontrada por monto de factura")
                    else:
                        _logger.info("⚠️ Búsqueda por monto no devolvió resultados")
                    
            # Método 4: Buscar la transacción más reciente del proveedor en estado pendiente
            if not tx:
                _logger.info("🔎 Método 4: Búsqueda de transacción pendiente más reciente...")
                tx = request.env['payment.transaction'].sudo().search([
                    ('provider_id', '=', provider_id),
                    ('state', 'in', ['draft', 'pending']),
                ], order='create_date desc', limit=1)
                
                if tx:
                    _logger.info("✅ Transacción pendiente más reciente encontrada")
                else:
                    _logger.info("⚠️ No se encontraron transacciones pendientes")
                
            if not tx:
                _logger.error("❌ PASO 3 FALLIDO: No se encontró transacción válida para referencia: %s", reference)
                self._log_process_end("CULQI PROCESS CARD", False, error="Transacción no encontrada")
                return {'success': False, 'error': f'No se encontró transacción válida para la referencia: {reference}'}

            _logger.info("✅ PASO 3 COMPLETADO: Transacción encontrada")
            _logger.info("📊 Detalles de transacción:")
            _logger.info("   - ID: %s", tx.id)
            _logger.info("   - Referencia: %s", tx.reference)
            _logger.info("   - Estado: %s", tx.state)
            _logger.info("   - Monto: %s %s", tx.amount, tx.currency_id.name if tx.currency_id else 'N/A')

            # Paso 4: Crear token en Culqi API
            _logger.info("🔍 PASO 4: Creando token en Culqi...")
            token_data = {
                'card_number': card_data['card_number'],
                'expiration_month': card_data['expiration_month'],
                'expiration_year': card_data['expiration_year'],
                'cvv': card_data['cvv'],
                'email': card_data['email']
            }

            _logger.info("📤 Datos para crear token:")
            _logger.info("   - Número de tarjeta: %s****", card_data['card_number'][:4])
            _logger.info("   - Mes expiración: %s", card_data['expiration_month'])
            _logger.info("   - Año expiración: %s", card_data['expiration_year'])
            _logger.info("   - Email: %s", card_data['email'])

            # Llamar a API de Culqi para crear token
            token_url = 'https://secure.culqi.com/v2/tokens'
            headers = {
                'Authorization': f'Bearer {provider.culqi_public_key}',
                'Content-Type': 'application/json'
            }
            
            _logger.info("🌐 Enviando petición a Culqi API...")
            _logger.info("   - URL: %s", token_url)
            _logger.info("   - Headers: %s", {k: v[:20] + '***' if k == 'Authorization' else v for k, v in headers.items()})

            token_response = requests.post(token_url, json=token_data, headers=headers, timeout=30)
            
            _logger.info("📥 Respuesta de Culqi recibida:")
            _logger.info("   - Status Code: %s", token_response.status_code)
            _logger.info("   - Headers: %s", dict(token_response.headers))
            
            if token_response.status_code != 200:
                _logger.error("❌ Error creando token: %s", token_response.text)
                self._log_process_end("CULQI PROCESS CARD", False, error="Error creando token")
                return {'success': False, 'error': 'Error creando token de pago'}

            token_result = token_response.json()
            _logger.info("📋 Respuesta completa del token: %s", pprint.pformat(token_result))
            
            culqi_token = token_result.get('id')
            
            if not culqi_token:
                _logger.error("❌ Token no recibido en respuesta: %s", token_result)
                self._log_process_end("CULQI PROCESS CARD", False, error="Token no generado")
                return {'success': False, 'error': 'Token de pago no generado'}

            _logger.info("✅ PASO 4 COMPLETADO: Token creado exitosamente")
            _logger.info("🎫 Token ID: %s", culqi_token[:12] + '***')

            # Paso 5: Crear cargo en Culqi
            _logger.info("🔍 PASO 5: Creando cargo en Culqi...")
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

            _logger.info("📤 Datos para crear cargo:")
            _logger.info("   - Monto: %s centavos", amount)
            _logger.info("   - Moneda: PEN")
            _logger.info("   - Descripción: %s", charge_data['description'])
            _logger.info("   - Email: %s", card_data['email'])
            _logger.info("   - Source ID: %s", culqi_token[:12] + '***')
            _logger.info("   - Metadata: %s", charge_data['metadata'])

            charge_url = 'https://api.culqi.com/v2/charges'
            charge_headers = {
                'Authorization': f'Bearer {provider.culqi_secret_key}',
                'Content-Type': 'application/json'
            }

            _logger.info("🌐 Enviando petición de cargo a Culqi API...")
            _logger.info("   - URL: %s", charge_url)
            _logger.info("   - Headers: %s", {k: v[:20] + '***' if k == 'Authorization' else v for k, v in charge_headers.items()})

            charge_response = requests.post(charge_url, json=charge_data, headers=charge_headers, timeout=30)
            
            _logger.info("📥 Respuesta de cargo recibida:")
            _logger.info("   - Status Code: %s", charge_response.status_code)
            _logger.info("   - Headers: %s", dict(charge_response.headers))
            
            if charge_response.status_code != 200:
                _logger.error("❌ Error creando cargo: %s", charge_response.text)
                self._log_process_end("CULQI PROCESS CARD", False, error="Error procesando pago")
                return {'success': False, 'error': 'Error procesando el pago'}

            charge_result = charge_response.json()
            _logger.info("📋 Respuesta completa del cargo: %s", pprint.pformat(charge_result))
            
            _logger.info("✅ PASO 5 COMPLETADO: Cargo creado exitosamente")
            _logger.info("💳 Cargo ID: %s", charge_result.get('id', 'No ID'))

            # Paso 6: Procesar la transacción en Odoo
            _logger.info("🔍 PASO 6: Procesando transacción en Odoo...")
            processing_values = {
                'culqi_token': culqi_token,
                'culqi_charge_id': charge_result.get('id'),
                'culqi_charge': charge_result
            }
            
            _logger.info("📦 Valores de procesamiento para Odoo:")
            _logger.info("   - Token: %s", culqi_token[:12] + '***')
            _logger.info("   - Charge ID: %s", charge_result.get('id'))
            _logger.info("   - Charge data keys: %s", list(charge_result.keys()) if charge_result else 'None')

            _logger.info("⚙️ Ejecutando _process_direct_payment...")
            tx._process_direct_payment(processing_values)
            _logger.info("✅ PASO 6 COMPLETADO: Transacción procesada en Odoo")

            # Paso 7: Determinar URL de redirección
            _logger.info("🔍 PASO 7: Determinando URL de redirección...")
            redirect_url = '/payment/status'
            
            if hasattr(tx, 'return_url') and tx.return_url:
                redirect_url = tx.return_url
                _logger.info("🔗 URL de retorno encontrada: %s", redirect_url)
            else:
                _logger.info("🔗 Usando URL por defecto: %s", redirect_url)

            _logger.info("✅ PASO 7 COMPLETADO: URL de redirección determinada")

            # Proceso completado exitosamente
            elapsed_time = time.time() - start_time
            self._log_process_end(
                "CULQI PROCESS CARD", 
                True,
                redirect_url=redirect_url,
                transaction_id=tx.id,
                charge_id=charge_result.get('id'),
                elapsed_time=f"{elapsed_time:.2f}s"
            )

            return {
                'success': True, 
                'redirect_url': redirect_url,
                'transaction_id': tx.id,
                'charge_id': charge_result.get('id')
            }

        except requests.exceptions.Timeout as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Timeout en conexión con Culqi: %s", e)
            self._log_process_end("CULQI PROCESS CARD", False, error="Timeout", elapsed_time=f"{elapsed_time:.2f}s")
            return {'success': False, 'error': 'Timeout de conexión con el procesador de pagos'}
        
        except requests.exceptions.RequestException as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error de conexión con Culqi: %s", e)
            self._log_process_end("CULQI PROCESS CARD", False, error="Error de conexión", elapsed_time=f"{elapsed_time:.2f}s")
            return {'success': False, 'error': 'Error de conexión con el procesador de pagos'}
        
        except Exception as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error inesperado procesando tarjeta: %s", e)
            self._log_process_end("CULQI PROCESS CARD", False, error=str(e), elapsed_time=f"{elapsed_time:.2f}s")
            return {'success': False, 'error': 'Error inesperado procesando el pago'}

    @http.route(_webhook_url, type='http', auth='public', methods=['POST'], csrf=False)
    def culqi_webhook(self, **post):
        """ Procesa la notificación de Culqi (evento tipo 'charge.created', etc.)

        :return: Respuesta vacía (200 OK) para confirmar la recepción.
        """
        start_time = time.time()
        
        try:
            _logger.info("=" * 80)
            _logger.info("🔔 WEBHOOK CULQI RECIBIDO")
            _logger.info("⏰ Timestamp: %s", time.strftime('%Y-%m-%d %H:%M:%S'))
            _logger.info("📡 Headers recibidos: %s", dict(request.httprequest.headers))
            _logger.info("📡 Método: %s", request.httprequest.method)
            _logger.info("📡 URL: %s", request.httprequest.url)
            _logger.info("=" * 80)
            
            # Leer datos del webhook
            raw_data = request.httprequest.data.decode('utf-8')
            _logger.info("📥 Datos crudos recibidos: %s", raw_data)
            
            data = json.loads(raw_data)
            _logger.info("📊 Datos JSON parseados: %s", pprint.pformat(data))
            
            event_type = data.get('type')
            charge = data.get('data', {}).get('object', {})
            
            _logger.info("🔍 Procesando webhook:")
            _logger.info("   - Tipo de evento: %s", event_type)
            _logger.info("   - ID del cargo: %s", charge.get('id'))
            _logger.info("   - Estado del cargo: %s", charge.get('outcome', {}).get('code'))
            _logger.info("   - Monto: %s %s", charge.get('amount'), charge.get('currency_code'))
            
            if charge.get('metadata'):
                _logger.info("   - Metadata: %s", charge.get('metadata'))

            # Buscar transacción
            _logger.info("🔍 Buscando transacción relacionada...")
            try:
                tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                    'culqi', charge
                )
                
                if tx:
                    _logger.info("✅ Transacción encontrada:")
                    _logger.info("   - ID: %s", tx.id)
                    _logger.info("   - Referencia: %s", tx.reference)
                    _logger.info("   - Estado antes: %s", tx.state)
                else:
                    _logger.warning("⚠️ No se encontró transacción para el webhook")
                    
            except Exception as e:
                _logger.error("❌ Error buscando transacción: %s", e)
                tx = None

            # Procesar notificación
            if tx:
                _logger.info("⚙️ Procesando notificación de webhook...")
                try:
                    tx._handle_notification_data('culqi', charge)
                    _logger.info("✅ Notificación procesada exitosamente")
                    _logger.info("   - Estado después: %s", tx.state)
                    
                    # Log adicional del estado de la transacción
                    if hasattr(tx, 'state_message'):
                        _logger.info("   - Mensaje de estado: %s", tx.state_message)
                        
                except Exception as e:
                    _logger.error("❌ Error procesando notificación: %s", e)
                    raise
            else:
                _logger.warning("⚠️ Webhook recibido pero no se pudo procesar - transacción no encontrada")

            elapsed_time = time.time() - start_time
            _logger.info("-" * 80)
            _logger.info("✅ WEBHOOK PROCESADO EXITOSAMENTE")
            _logger.info("⏰ Tiempo de procesamiento: %.2fs", elapsed_time)
            _logger.info("-" * 80)
            
        except json.JSONDecodeError as e:
            elapsed_time = time.time() - start_time
            _logger.error("❌ Error parseando JSON del webhook: %s", e)
            _logger.error("📥 Datos recibidos: %s", request.httprequest.data.decode('utf-8', errors='ignore'))
            _logger.info("⏰ Tiempo transcurrido: %.2fs", elapsed_time)
            raise Forbidden(description="JSON inválido en webhook.")
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error procesando webhook de Culqi: %s", e)
            _logger.info("⏰ Tiempo transcurrido: %.2fs", elapsed_time)
            _logger.info("📊 Contexto del error:")
            _logger.info("   - Headers: %s", dict(request.httprequest.headers))
            _logger.info("   - Datos: %s", request.httprequest.data.decode('utf-8', errors='ignore')[:500])
            raise Forbidden(description="Webhook no válido o incompleto.")

        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])