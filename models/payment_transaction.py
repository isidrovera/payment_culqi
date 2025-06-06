# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
import time

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    culqi_charge_id = fields.Char(string="Culqi Charge ID", readonly=True)

    def _log_transaction_start(self, process_name, **kwargs):
        """Helper para loggear inicio de proceso de transacción con timestamp"""
        _logger.info("=" * 80)
        _logger.info("🚀 INICIANDO PROCESO: %s", process_name)
        _logger.info("⏰ Timestamp: %s", time.strftime('%Y-%m-%d %H:%M:%S'))
        _logger.info("📋 Transacción:")
        _logger.info("   - ID: %s", self.id)
        _logger.info("   - Referencia: %s", self.reference)
        _logger.info("   - Estado: %s", self.state)
        _logger.info("   - Monto: %s %s", self.amount, self.currency_id.name if self.currency_id else 'N/A')
        _logger.info("   - Proveedor: %s", self.provider_code)
        _logger.info("   - Partner: %s (%s)", self.partner_id.name if self.partner_id else 'N/A', 
                    self.partner_email or 'Sin email')
        for key, value in kwargs.items():
            if 'token' in key.lower() and value:
                _logger.info("📋 %s: %s", key, str(value)[:12] + '***')
            elif 'charge' in key.lower() and value:
                _logger.info("📋 %s: %s", key, str(value)[:12] + '***')
            else:
                _logger.info("📋 %s: %s", key, value)
        _logger.info("=" * 80)

    def _log_transaction_end(self, process_name, success=True, **kwargs):
        """Helper para loggear fin de proceso de transacción"""
        status = "✅ COMPLETADO" if success else "❌ FALLIDO"
        _logger.info("-" * 80)
        _logger.info("%s PROCESO: %s", status, process_name)
        _logger.info("⏰ Timestamp: %s", time.strftime('%Y-%m-%d %H:%M:%S'))
        _logger.info("📊 Estado final transacción: %s", self.state)
        if hasattr(self, 'culqi_charge_id') and self.culqi_charge_id:
            _logger.info("📊 Culqi Charge ID: %s", self.culqi_charge_id)
        if hasattr(self, 'provider_reference') and self.provider_reference:
            _logger.info("📊 Provider Reference: %s", self.provider_reference)
        for key, value in kwargs.items():
            _logger.info("📊 %s: %s", key, value)
        _logger.info("-" * 80)

    def _get_specific_processing_values(self, processing_values):
        """Preparar los datos necesarios para procesar un pago con Culqi."""
        start_time = time.time()
        
        _logger.info("🔍 Ejecutando _get_specific_processing_values...")
        _logger.info("📋 Processing values recibidos: %s", 
                    {k: (str(v)[:12] + '***' if 'token' in k.lower() and v else v) 
                     for k, v in processing_values.items()})
        
        # Ejecutar método padre primero
        _logger.info("⚙️ Ejecutando método padre...")
        res = super()._get_specific_processing_values(processing_values)
        _logger.info("📋 Resultado del método padre: %s", res)
        
        # Verificar si es transacción Culqi
        if self.provider_code != 'culqi':
            _logger.info("ℹ️ Transacción no es Culqi (%s), retornando resultado padre", self.provider_code)
            return res

        self._log_transaction_start(
            "CULQI SPECIFIC PROCESSING",
            processing_values_keys=list(processing_values.keys()),
            parent_result=res
        )

        try:
            # Paso 1: Validar token
            _logger.info("🔍 PASO 1: Validando token Culqi...")
            token = processing_values.get('culqi_token')
            
            if not token:
                _logger.error("❌ Token Culqi no recibido en processing_values")
                _logger.error("📋 Processing values disponibles: %s", list(processing_values.keys()))
                raise ValidationError(_("Culqi: Token no recibido para la transacción."))
            
            _logger.info("✅ Token Culqi válido recibido: %s", token[:12] + '***')
            _logger.info("✅ PASO 1 COMPLETADO: Token validado")

            # Paso 2: Preparar payload para Culqi
            _logger.info("🔍 PASO 2: Preparando payload para Culqi...")
            
            # Calcular monto en centavos
            amount_cents = int(self.amount * 100)
            _logger.info("💰 Conversión de monto: %.2f %s -> %d centavos", 
                        self.amount, self.currency_id.name, amount_cents)
            
            # Determinar email
            email = self.partner_email or (self.partner_id.email if self.partner_id else None)
            if not email:
                _logger.warning("⚠️ No se encontró email para la transacción")
            else:
                _logger.info("📧 Email para transacción: %s", email)
            
            payload = {
                'amount': amount_cents,
                'currency_code': self.currency_id.name,
                'email': email,
                'source_id': token,
                'metadata': {
                    'tx_ref': self.reference,
                }
            }

            _logger.info("📦 Payload preparado para Culqi:")
            _logger.info("   - Monto: %d centavos", payload['amount'])
            _logger.info("   - Moneda: %s", payload['currency_code'])
            _logger.info("   - Email: %s", payload['email'])
            _logger.info("   - Source ID: %s", payload['source_id'][:12] + '***')
            _logger.info("   - Metadata: %s", payload['metadata'])
            
            _logger.info("✅ PASO 2 COMPLETADO: Payload preparado")

            # Paso 3: Enviar solicitud a Culqi
            _logger.info("🔍 PASO 3: Enviando solicitud a Culqi...")
            _logger.info("🌐 Endpoint: /charges")
            _logger.info("📤 Payload completo para log:")
            _logger.info("%s", pprint.pformat(payload))

            charge = self.provider_id._culqi_make_request('/charges', payload=payload)
            
            _logger.info("📥 Respuesta recibida de Culqi:")
            _logger.info("%s", pprint.pformat(charge))
            _logger.info("✅ PASO 3 COMPLETADO: Solicitud enviada y respuesta recibida")

            # Paso 4: Procesar respuesta
            _logger.info("🔍 PASO 4: Procesando respuesta de Culqi...")
            self._process_culqi_response(charge)
            _logger.info("✅ PASO 4 COMPLETADO: Respuesta procesada")

            # Proceso completado exitosamente
            elapsed_time = time.time() - start_time
            self._log_transaction_end(
                "CULQI SPECIFIC PROCESSING",
                True,
                elapsed_time=f"{elapsed_time:.2f}s",
                charge_id=charge.get('id', 'N/A'),
                final_state=self.state
            )

            return {}

        except ValidationError as e:
            elapsed_time = time.time() - start_time
            _logger.error("❌ Error de validación: %s", e)
            self._log_transaction_end(
                "CULQI SPECIFIC PROCESSING",
                False,
                error="Validation Error",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            raise
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error inesperado en _get_specific_processing_values: %s", e)
            self._log_transaction_end(
                "CULQI SPECIFIC PROCESSING",
                False,
                error="Unexpected Error",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            raise

    def _process_culqi_response(self, response):
        """Interpretar la respuesta de Culqi y actualizar la transacción."""
        self.ensure_one()
        start_time = time.time()
        
        self._log_transaction_start(
            "CULQI RESPONSE PROCESSING",
            response_keys=list(response.keys()) if response else "None",
            response_id=response.get('id') if response else "N/A"
        )

        try:
            # Paso 1: Extraer datos básicos de la respuesta
            _logger.info("🔍 PASO 1: Extrayendo datos básicos de la respuesta...")
            
            charge_id = response.get('id')
            _logger.info("💳 Charge ID: %s", charge_id)
            
            # Actualizar campos de la transacción
            old_charge_id = self.culqi_charge_id
            old_provider_ref = self.provider_reference
            
            self.culqi_charge_id = charge_id
            self.provider_reference = charge_id
            
            _logger.info("📊 Actualizaciones realizadas:")
            _logger.info("   - culqi_charge_id: %s -> %s", old_charge_id, self.culqi_charge_id)
            _logger.info("   - provider_reference: %s -> %s", old_provider_ref, self.provider_reference)
            
            _logger.info("✅ PASO 1 COMPLETADO: Datos básicos extraídos y actualizados")

            # Paso 2: Analizar outcome de la respuesta
            _logger.info("🔍 PASO 2: Analizando outcome de la respuesta...")
            
            outcome = response.get('outcome', {})
            outcome_type = outcome.get('type')
            outcome_code = outcome.get('code')
            
            _logger.info("📊 Outcome completo: %s", outcome)
            _logger.info("📊 Outcome type: %s", outcome_type)
            _logger.info("📊 Outcome code: %s", outcome_code)
            
            # Estado previo de la transacción
            previous_state = self.state
            _logger.info("📊 Estado previo: %s", previous_state)
            
            _logger.info("✅ PASO 2 COMPLETADO: Outcome analizado")

            # Paso 3: Determinar y aplicar nuevo estado
            _logger.info("🔍 PASO 3: Determinando nuevo estado de transacción...")
            
            if outcome_type == 'venta_exitosa':
                _logger.info("✅ Pago exitoso detectado")
                self._set_done()
                new_state = 'done'
                state_message = "Pago exitoso"
                
            elif outcome_type == 'venta_rechazada':
                _logger.info("❌ Pago rechazado detectado")
                error_message = _("Pago rechazado por Culqi.")
                if outcome_code:
                    error_message += f" Código: {outcome_code}"
                self._set_error(error_message)
                new_state = 'error'
                state_message = f"Pago rechazado - {outcome_code}"
                
            else:
                _logger.info("⏳ Estado pendiente o desconocido: %s", outcome_type)
                pending_message = _("Esperando confirmación de pago.")
                if outcome_type:
                    pending_message += f" Estado: {outcome_type}"
                self._set_pending(pending_message)
                new_state = 'pending'
                state_message = f"Pendiente - {outcome_type}"

            _logger.info("📊 Transición de estado: %s -> %s", previous_state, new_state)
            _logger.info("📊 Mensaje de estado: %s", state_message)
            _logger.info("✅ PASO 3 COMPLETADO: Estado actualizado")

            # Proceso completado exitosamente
            elapsed_time = time.time() - start_time
            self._log_transaction_end(
                "CULQI RESPONSE PROCESSING",
                True,
                previous_state=previous_state,
                new_state=new_state,
                state_message=state_message,
                outcome_type=outcome_type,
                elapsed_time=f"{elapsed_time:.2f}s"
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error procesando respuesta de Culqi: %s", e)
            self._log_transaction_end(
                "CULQI RESPONSE PROCESSING",
                False,
                error="Processing Error",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            raise

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        start_time = time.time()
        
        _logger.info("=" * 80)
        _logger.info("🚀 INICIANDO PROCESO: GET TX FROM NOTIFICATION")
        _logger.info("⏰ Timestamp: %s", time.strftime('%Y-%m-%d %H:%M:%S'))
        _logger.info("📋 Provider code: %s", provider_code)
        _logger.info("📋 Notification data keys: %s", list(notification_data.keys()) if notification_data else "None")
        if notification_data:
            _logger.info("📋 Notification data: %s", pprint.pformat(notification_data))
        _logger.info("=" * 80)

        try:
            # Paso 1: Ejecutar método padre
            _logger.info("🔍 PASO 1: Ejecutando método padre...")
            tx = super()._get_tx_from_notification_data(provider_code, notification_data)
            
            _logger.info("📊 Resultado del método padre:")
            if tx:
                _logger.info("   - Transacciones encontradas: %d", len(tx))
                for i, transaction in enumerate(tx):
                    _logger.info("   - TX %d: ID=%s, Ref=%s, Estado=%s", 
                                i+1, transaction.id, transaction.reference, transaction.state)
            else:
                _logger.info("   - No se encontraron transacciones")
            
            _logger.info("✅ PASO 1 COMPLETADO: Método padre ejecutado")

            # Paso 2: Verificar si necesitamos procesamiento adicional para Culqi
            _logger.info("🔍 PASO 2: Verificando necesidad de procesamiento adicional...")
            
            if provider_code != 'culqi':
                _logger.info("ℹ️ Provider no es Culqi (%s), retornando resultado padre", provider_code)
                elapsed_time = time.time() - start_time
                _logger.info("⏰ Tiempo total: %.2fs", elapsed_time)
                return tx
                
            if len(tx) == 1:
                _logger.info("ℹ️ Exactamente 1 transacción encontrada, retornando resultado padre")
                elapsed_time = time.time() - start_time
                _logger.info("⏰ Tiempo total: %.2fs", elapsed_time)
                return tx
                
            _logger.info("🔍 Necesario procesamiento adicional para Culqi")
            _logger.info("✅ PASO 2 COMPLETADO: Verificación realizada")

            # Paso 3: Búsqueda específica para Culqi
            _logger.info("🔍 PASO 3: Búsqueda específica para Culqi...")
            
            # Extraer referencia de metadata
            reference = notification_data.get('metadata', {}).get('tx_ref')
            _logger.info("📋 Referencia extraída de metadata: %s", reference)
            
            if not reference:
                _logger.warning("⚠️ No se encontró referencia en metadata")
                _logger.warning("📋 Metadata disponible: %s", notification_data.get('metadata', {}))
            
            # Buscar transacción por referencia
            _logger.info("🔍 Buscando transacción con referencia: %s", reference)
            tx = self.search([
                ('reference', '=', reference), 
                ('provider_code', '=', 'culqi')
            ])
            
            _logger.info("📊 Resultado de búsqueda específica:")
            if tx:
                _logger.info("   - Transacciones encontradas: %d", len(tx))
                for i, transaction in enumerate(tx):
                    _logger.info("   - TX %d: ID=%s, Ref=%s, Estado=%s", 
                                i+1, transaction.id, transaction.reference, transaction.state)
            else:
                _logger.info("   - No se encontraron transacciones")
            
            if not tx:
                error_msg = f"Culqi: No se encontró la transacción con referencia {reference}."
                _logger.error("❌ %s", error_msg)
                
                elapsed_time = time.time() - start_time
                _logger.info("-" * 80)
                _logger.info("❌ FALLIDO PROCESO: GET TX FROM NOTIFICATION")
                _logger.info("⏰ Tiempo total: %.2fs", elapsed_time)
                _logger.info("📊 Error: Transacción no encontrada")
                _logger.info("-" * 80)
                
                raise ValidationError(_(error_msg))
            
            _logger.info("✅ PASO 3 COMPLETADO: Transacción encontrada")

            # Proceso completado exitosamente
            elapsed_time = time.time() - start_time
            _logger.info("-" * 80)
            _logger.info("✅ COMPLETADO PROCESO: GET TX FROM NOTIFICATION")
            _logger.info("⏰ Tiempo total: %.2fs", elapsed_time)
            _logger.info("📊 Transacción retornada: ID=%s, Ref=%s", tx.id, tx.reference)
            _logger.info("-" * 80)
            
            return tx

        except ValidationError as e:
            elapsed_time = time.time() - start_time
            _logger.error("❌ Error de validación: %s", e)
            _logger.info("⏰ Tiempo transcurrido: %.2fs", elapsed_time)
            raise
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error inesperado en _get_tx_from_notification_data: %s", e)
            _logger.info("⏰ Tiempo transcurrido: %.2fs", elapsed_time)
            raise

    def _process_notification_data(self, notification_data):
        start_time = time.time()
        
        self._log_transaction_start(
            "PROCESS NOTIFICATION DATA",
            notification_data_keys=list(notification_data.keys()) if notification_data else "None",
            provider_code=self.provider_code
        )

        try:
            # Paso 1: Ejecutar método padre
            _logger.info("🔍 PASO 1: Ejecutando método padre...")
            super()._process_notification_data(notification_data)
            _logger.info("✅ PASO 1 COMPLETADO: Método padre ejecutado")

            # Paso 2: Verificar si es transacción Culqi
            _logger.info("🔍 PASO 2: Verificando provider code...")
            if self.provider_code != 'culqi':
                _logger.info("ℹ️ Transacción no es Culqi (%s), proceso completado", self.provider_code)
                elapsed_time = time.time() - start_time
                self._log_transaction_end(
                    "PROCESS NOTIFICATION DATA",
                    True,
                    message="No Culqi transaction",
                    elapsed_time=f"{elapsed_time:.2f}s"
                )
                return
            
            _logger.info("✅ PASO 2 COMPLETADO: Transacción Culqi confirmada")

            # Paso 3: Extraer datos de la notificación
            _logger.info("🔍 PASO 3: Extrayendo datos de notificación...")
            
            _logger.info("📋 Notification data completa: %s", pprint.pformat(notification_data))
            
            status = notification_data.get('outcome', {}).get('type')
            charge_id = notification_data.get('id')
            outcome = notification_data.get('outcome', {})
            
            _logger.info("📊 Datos extraídos:")
            _logger.info("   - Status: %s", status)
            _logger.info("   - Charge ID: %s", charge_id)
            _logger.info("   - Outcome completo: %s", outcome)
            
            # Actualizar campos
            old_charge_id = self.culqi_charge_id
            old_provider_ref = self.provider_reference
            
            self.culqi_charge_id = charge_id
            self.provider_reference = charge_id
            
            _logger.info("📊 Campos actualizados:")
            _logger.info("   - culqi_charge_id: %s -> %s", old_charge_id, self.culqi_charge_id)
            _logger.info("   - provider_reference: %s -> %s", old_provider_ref, self.provider_reference)
            
            _logger.info("✅ PASO 3 COMPLETADO: Datos extraídos y campos actualizados")

            # Paso 4: Procesar estado de la transacción
            _logger.info("🔍 PASO 4: Procesando estado de transacción...")
            
            previous_state = self.state
            _logger.info("📊 Estado previo: %s", previous_state)
            
            if status == 'venta_exitosa':
                _logger.info("✅ Procesando venta exitosa...")
                self._set_done()
                new_state = 'done'
                state_message = "Venta exitosa"
                
            elif status == 'venta_rechazada':
                _logger.info("❌ Procesando venta rechazada...")
                error_message = _("Pago rechazado por Culqi.")
                outcome_code = outcome.get('code')
                if outcome_code:
                    error_message += f" Código: {outcome_code}"
                self._set_error(error_message)
                new_state = 'error'
                state_message = f"Venta rechazada - {outcome_code}"
                
            else:
                _logger.info("⏳ Procesando estado pendiente o desconocido...")
                pending_message = _("Estado del pago: %s") % status if status else _("Estado del pago desconocido")
                self._set_pending(pending_message)
                new_state = 'pending'
                state_message = f"Estado: {status}"

            _logger.info("📊 Transición de estado: %s -> %s", previous_state, new_state)
            _logger.info("📊 Mensaje de estado: %s", state_message)
            _logger.info("✅ PASO 4 COMPLETADO: Estado procesado")

            # Proceso completado exitosamente
            elapsed_time = time.time() - start_time
            self._log_transaction_end(
                "PROCESS NOTIFICATION DATA",
                True,
                previous_state=previous_state,
                new_state=new_state,
                state_message=state_message,
                status=status,
                elapsed_time=f"{elapsed_time:.2f}s"
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            _logger.exception("❌ Error en _process_notification_data: %s", e)
            self._log_transaction_end(
                "PROCESS NOTIFICATION DATA",
                False,
                error="Processing Error",
                error_detail=str(e),
                elapsed_time=f"{elapsed_time:.2f}s"
            )
            raise