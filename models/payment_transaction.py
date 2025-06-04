# -*- coding: utf-8 -*-

import logging
import json
import hashlib
import hmac
from datetime import datetime
from werkzeug import urls

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # Campos específicos de Culqi
    culqi_token_id = fields.Char(
        string="Culqi Token ID",
        help="ID del token generado por Culqi",
        readonly=True
    )
    
    culqi_charge_id = fields.Char(
        string="Culqi Charge ID", 
        help="ID del cargo en Culqi",
        readonly=True
    )
    
    culqi_payment_method = fields.Selection([
        ('card', 'Tarjeta de Crédito/Débito'),
        ('yape', 'Yape'),
        ('pagoefectivo', 'PagoEfectivo'),
        ('cuotealo', 'Cuotéalo'),
    ], string="Método de Pago Culqi", readonly=True)
    
    culqi_card_brand = fields.Char(
        string="Marca de Tarjeta",
        help="Visa, Mastercard, etc.",
        readonly=True
    )
    
    culqi_card_last_four = fields.Char(
        string="Últimos 4 dígitos",
        help="Últimos 4 dígitos de la tarjeta",
        readonly=True
    )
    
    culqi_creation_date = fields.Datetime(
        string="Fecha de Creación Culqi",
        help="Fecha de creación en Culqi",
        readonly=True
    )
    
    culqi_outcome_type = fields.Char(
        string="Tipo de Resultado",
        help="Tipo de resultado devuelto por Culqi",
        readonly=True
    )
    
    culqi_outcome_code = fields.Char(
        string="Código de Resultado", 
        help="Código específico del resultado",
        readonly=True
    )
    
    culqi_fee = fields.Monetary(
        string="Comisión Culqi",
        help="Comisión cobrada por Culqi",
        readonly=True,
        currency_field='currency_id'
    )
    
    culqi_net_amount = fields.Monetary(
        string="Monto Neto",
        help="Monto neto después de comisiones",
        readonly=True,
        currency_field='currency_id'
    )
    
    culqi_pagoefectivo_cip = fields.Char(
        string="CIP PagoEfectivo",
        help="Código CIP para pagos en efectivo",
        readonly=True
    )
    
    culqi_pagoefectivo_expiration = fields.Datetime(
        string="Expiración PagoEfectivo",
        help="Fecha de expiración del CIP",
        readonly=True
    )

    # ==========================================
    # MÉTODOS DE PROCESAMIENTO DE TRANSACCIONES
    # ==========================================

    def _get_specific_rendering_values(self, processing_values):
        """Obtiene valores específicos para renderizar el formulario de pago"""
        res = super()._get_specific_rendering_values(processing_values)
        
        if self.provider_code != 'culqi':
            return res

        # Generar token de formulario si es necesario
        form_token = self._culqi_generate_form_token()
        
        culqi_values = {
            'public_key': self.provider_id.culqi_public_key,
            'form_token': form_token,
            'checkout_mode': self.provider_id.culqi_checkout_mode,
            'return_url': urls.url_join(
                self.provider_id.get_base_url(),
                f'/payment/culqi/return?ref={self.reference}'
            ),
            'webhook_url': self.provider_id.culqi_webhook_url,
            'reference': self.reference,
            'amount_cents': int(self.amount * 100),  # Culqi maneja centavos
            'currency': self.currency_id.name,
            'customer_email': self.partner_email or '',
            'description': f"Pago {self.reference}",
        }
        
        res.update(culqi_values)
        return res

    def _culqi_generate_form_token(self):
        """Genera un token de formulario para Culqi (si es necesario)"""
        # En algunos casos, Culqi puede requerir un token de formulario
        # Por ahora retornamos None, se puede implementar según necesidades
        return None

    def _send_payment_request(self):
        """Envía la petición de pago a Culqi"""
        if self.provider_code != 'culqi':
            return super()._send_payment_request()

        # Para Culqi, el pago se procesa cuando se recibe el webhook
        # o cuando se confirma desde el frontend
        _logger.info("Enviando petición de pago Culqi para transacción %s", self.reference)
        return self._set_pending()

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Obtiene la transacción desde los datos de notificación"""
        if provider_code != 'culqi':
            return super()._get_tx_from_notification_data(provider_code, notification_data)

        reference = notification_data.get('reference')
        charge_id = notification_data.get('id')
        
        if reference:
            tx = self.search([('reference', '=', reference), ('provider_code', '=', 'culqi')])
        elif charge_id:
            tx = self.search([('culqi_charge_id', '=', charge_id), ('provider_code', '=', 'culqi')])
        else:
            tx = self.env['payment.transaction']
            
        return tx

    def _process_notification_data(self, notification_data):
        """Procesa los datos de notificación de Culqi"""
        if self.provider_code != 'culqi':
            return super()._process_notification_data(notification_data)

        _logger.info("Procesando notificación Culqi para transacción %s: %s", 
                    self.reference, notification_data)

        # Actualizar campos específicos de Culqi
        self._update_culqi_transaction_data(notification_data)
        
        # Determinar el estado de la transacción
        outcome = notification_data.get('outcome', {})
        outcome_type = outcome.get('type', '')
        
        if outcome_type == 'venta_exitosa':
            self._set_done()
        elif outcome_type in ['venta_denegada', 'parametro_invalido']:
            self._set_error("Pago rechazado por Culqi: %s" % outcome.get('merchant_message', ''))
        else:
            self._set_pending()

    def _update_culqi_transaction_data(self, data):
        """Actualiza los campos específicos de Culqi"""
        self.ensure_one()
        
        # Información básica
        self.culqi_charge_id = data.get('id')
        self.culqi_payment_method = data.get('source', {}).get('type')
        
        # Información de resultado
        outcome = data.get('outcome', {})
        self.culqi_outcome_type = outcome.get('type')
        self.culqi_outcome_code = outcome.get('code')
        
        # Información de tarjeta (si aplica)
        source = data.get('source', {})
        if source.get('type') == 'card':
            self.culqi_card_brand = source.get('card_brand')
            self.culqi_card_last_four = source.get('last_four')
        
        # Información de PagoEfectivo (si aplica)
        if source.get('type') == 'pagoefectivo':
            self.culqi_pagoefectivo_cip = source.get('cip_code')
            if source.get('expiration_date'):
                self.culqi_pagoefectivo_expiration = datetime.fromtimestamp(
                    source.get('expiration_date') / 1000
                )
        
        # Información financiera
        if data.get('total_fee'):
            self.culqi_fee = data.get('total_fee') / 100  # Convertir de centavos
        if data.get('net_amount'):
            self.culqi_net_amount = data.get('net_amount') / 100
        
        # Fecha de creación
        if data.get('creation_date'):
            self.culqi_creation_date = datetime.fromtimestamp(
                data.get('creation_date') / 1000
            )

    # ==========================================
    # MÉTODOS DE VALIDACIÓN Y SEGURIDAD
    # ==========================================

    def _culqi_verify_webhook_signature(self, payload, signature):
        """Verifica la firma del webhook de Culqi"""
        if not self.provider_id.culqi_secret_key:
            return False
            
        expected_signature = hmac.new(
            self.provider_id.culqi_secret_key.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)

    # ==========================================
    # MÉTODOS DE REEMBOLSO
    # ==========================================

    def _send_refund_request(self, amount_to_refund=None):
        """Envía petición de reembolso a Culqi"""
        if self.provider_code != 'culqi':
            return super()._send_refund_request(amount_to_refund)

        if not self.culqi_charge_id:
            raise UserError(_("No se puede reembolsar: falta el ID del cargo en Culqi"))

        refund_amount = amount_to_refund or self.amount
        refund_data = {
            'charge_id': self.culqi_charge_id,
            'amount': int(refund_amount * 100),  # Convertir a centavos
            'reason': 'requested_by_customer'
        }

        try:
            result = self.provider_id._culqi_make_request('/refunds', refund_data)
            
            if result.get('object') == 'refund':
                # Crear registro de reembolso
                refund_tx = self._create_refund_transaction(refund_amount)
                refund_tx.culqi_charge_id = result.get('id')
                refund_tx._set_done()
                
                _logger.info("Reembolso Culqi exitoso: %s", result.get('id'))
                return refund_tx
            else:
                raise UserError(_("Error en el reembolso: %s") % result.get('message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error("Error en reembolso Culqi: %s", str(e))
            raise UserError(_("Error al procesar el reembolso: %s") % str(e))

    def _create_refund_transaction(self, amount):
        """Crea una transacción de reembolso"""
        return self.create({
            'reference': f"{self.reference}-refund-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}",
            'provider_id': self.provider_id.id,
            'provider_reference': f"refund-{self.provider_reference}",
            'amount': -amount,  # Monto negativo para reembolso
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'operation': 'refund',
            'source_transaction_id': self.id,
        })

    # ==========================================
    # MÉTODOS DE INFORMACIÓN
    # ==========================================

    def action_view_culqi_transaction(self):
        """Acción para ver la transacción en el panel de Culqi"""
        self.ensure_one()
        
        if not self.culqi_charge_id:
            raise UserError(_("Esta transacción no tiene un ID de cargo en Culqi"))
        
        # URL del panel de Culqi (puede variar)
        culqi_panel_url = "https://panel.culqi.com"
        transaction_url = f"{culqi_panel_url}/transactions/{self.culqi_charge_id}"
        
        return {
            'type': 'ir.actions.act_url',
            'url': transaction_url,
            'target': 'new',
        }

    def _get_culqi_payment_method_info(self):
        """Obtiene información del método de pago utilizado"""
        self.ensure_one()
        
        if self.culqi_payment_method == 'card' and self.culqi_card_brand:
            return f"{self.culqi_card_brand} ****{self.culqi_card_last_four}"
        elif self.culqi_payment_method == 'yape':
            return "Yape"
        elif self.culqi_payment_method == 'pagoefectivo':
            cip_info = f" (CIP: {self.culqi_pagoefectivo_cip})" if self.culqi_pagoefectivo_cip else ""
            return f"PagoEfectivo{cip_info}"
        elif self.culqi_payment_method == 'cuotealo':
            return "Cuotéalo"
        else:
            return self.culqi_payment_method or "Desconocido"