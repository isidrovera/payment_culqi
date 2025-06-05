# -*- coding: utf-8 -*-

import logging
from datetime import datetime
from werkzeug import urls

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # CAMPOS BÁSICOS CULQI (siguiendo patrón Mollie)
    culqi_token_id = fields.Char(string="Culqi Token ID", readonly=True)
    culqi_charge_id = fields.Char(string="Culqi Charge ID", readonly=True)
    culqi_payment_method = fields.Char(string="Método de Pago Culqi", readonly=True)
    culqi_reminder_payment_id = fields.Many2one('account.payment', string="Culqi Reminder Payment", readonly=True)
    culqi_fee = fields.Monetary(string="Comisión Culqi", readonly=True, currency_field='currency_id')

    def _get_specific_rendering_values(self, processing_values):
        """Obtiene valores específicos para renderizar el formulario de pago"""
        if self.provider_code != 'culqi':
            return super()._get_specific_rendering_values(processing_values)

        base_url = self.provider_id.get_base_url()
        
        # Crear orden/pago en Culqi
        payment_data = self._create_culqi_charge()
        
        if payment_data.get("checkout_url"):
            return {
                'api_url': payment_data["checkout_url"],
                'ref': self.reference
            }
        else:
            return {
                'api_url': payment_data.get('checkout_url'),
                'ref': self.reference
            }

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Obtiene la transacción desde los datos de notificación"""
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'culqi' or len(tx) == 1:
            return tx
            
        if notification_data.get('id'):
            tx = self.search([
                ('provider_reference', '=', notification_data.get('id')),
                ('provider_code', '=', 'culqi')
            ])
            if not tx:
                raise ValidationError("Culqi: " + _(
                    "No transaction found matching provider reference %s.", notification_data.get('id')
                ))
        return tx

    def _process_notification_data(self, notification_data):
        """Procesa los datos de notificación de Culqi"""
        if self.provider_code != 'culqi':
            return super()._process_notification_data(notification_data)

        if self.state == 'done':
            return

        # Obtener datos del pago desde Culqi
        culqi_payment = self.provider_id._culqi_make_request(
            f'/charges/{self.provider_reference}', method='GET'
        )
        
        outcome = culqi_payment.get('outcome', {})
        outcome_type = outcome.get('type', '')
        
        if outcome_type == 'venta_exitosa':
            self._set_done()
        elif outcome_type in ['venta_denegada', 'parametro_invalido']:
            self._set_error("Culqi: " + _("Pago rechazado: %s", outcome.get('merchant_message', '')))
        elif culqi_payment.get('state') == 'pending':
            self._set_pending()
        else:
            _logger.info("Received Culqi data with status: %s", outcome_type)
            self._set_error("Culqi: " + _("Estado de pago inválido: %s", outcome_type))

    def _send_refund_request(self, amount_to_refund=None):
        """Envía petición de reembolso a Culqi"""
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != 'culqi':
            return refund_tx

        if not self.provider_reference:
            raise UserError(_("No se puede reembolsar: falta la referencia del cargo"))

        refund_amount = amount_to_refund or self.amount
        refund_data = {
            'charge_id': self.provider_reference,
            'amount': int(refund_amount * 100),  # Convertir a centavos
            'reason': 'requested_by_customer'
        }

        refund_result = self.provider_id._culqi_make_request('/refunds', refund_data)
        refund_tx.provider_reference = refund_result.get('id')

        return refund_tx

    def _create_culqi_charge(self):
        """Crea un cargo/orden en Culqi"""
        self.ensure_one()
        
        # Preparar datos del pago
        charge_data = {
            'amount': int(self.amount * 100),  # Convertir a centavos
            'currency_code': self.currency_id.name,
            'email': self.partner_email,
            'description': f"Pago {self.reference}",
            'metadata': {
                'reference': self.reference,
                'transaction_id': self.id,
            }
        }
        
        # Crear cargo en Culqi
        result = self.provider_id._culqi_make_request('/charges', charge_data)
        
        if result.get('object') == 'charge':
            self.provider_reference = result.get('id')
            self.culqi_charge_id = result.get('id')
            return result
        else:
            raise UserError(_("Error creando cargo en Culqi: %s") % result.get('message', 'Error desconocido'))

    def _create_payment(self, **extra_create_values):
        """Método sobrescrito para crear pagos con integración de journals Culqi"""
        if self.provider_id.code == 'culqi':
            culqi_method = self.payment_method_id
            if culqi_method and hasattr(culqi_method, 'journal_id') and culqi_method.journal_id:
                culqi_method_payment_code = culqi_method._get_journal_method_code()
                payment_method_line = culqi_method.journal_id.inbound_payment_method_line_ids.filtered(
                    lambda l: l.code == culqi_method_payment_code
                )
                if payment_method_line:
                    extra_create_values['journal_id'] = culqi_method.journal_id.id
                    extra_create_values['payment_method_line_id'] = payment_method_line.id

        payment_record = super()._create_payment(**extra_create_values)

        # Post reminder payment if auto invoice is activated
        if self.invoice_ids and self.culqi_reminder_payment_id:
            (self.invoice_ids.line_ids + self.culqi_reminder_payment_id.line_ids).filtered(
                lambda line: line.account_id == self.culqi_reminder_payment_id.destination_account_id and not line.reconciled
            ).reconcile()

        return payment_record

    def _get_received_message(self):
        """Método sobrescrito para añadir información del pago de recordatorio"""
        self.ensure_one()

        message = super()._get_received_message()
        if message and self.state == 'done' and self.culqi_reminder_payment_id:
            message += _(
                "\nEl monto restante del pago fue registrado: %s",
                self.culqi_reminder_payment_id._get_html_link()
            )
        return message