# -*- coding: utf-8 -*-
from odoo import models, fields, _, api
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        """ Procesa pagos adicionales de recordatorio de Culqi cuando hay diferentes journals.
        """
        posted = super()._post(soft)

        for invoice in posted.filtered(lambda move: move.is_invoice()):
            payments = invoice.mapped('transaction_ids.culqi_reminder_payment_id')
            move_lines = payments.move_id.line_ids.filtered(
                lambda line: line.account_type in ('asset_receivable', 'liability_payable') and not line.reconciled
            )
            for line in move_lines:
                invoice.js_assign_outstanding_line(line.id)
        return posted

    # Campos para procesar reembolsos desde notas de crédito
    valid_for_culqi_refund = fields.Boolean(compute="_compute_valid_for_culqi_refund")
    culqi_refund_reference = fields.Char(string="Culqi Refund Reference")

    def _get_culqi_payment_data_for_refund(self):
        """Obtiene datos de pago de Culqi para reembolso"""
        self.ensure_one()
        culqi_transactions = self._find_valid_culqi_transactions()
        
        if self.move_type == 'out_refund' and culqi_transactions:
            # TODO: Manejar múltiples transacciones
            if len(culqi_transactions) > 1:
                raise UserError(_(
                    "Múltiples transacciones Culqi están vinculadas con la factura. "
                    "Por favor, reembolse manualmente desde el portal de Culqi"
                ))
            
            # ✅ CORREGIDO: Usar provider_reference en lugar de culqi_charge_id
            payment_record = culqi_transactions.provider_id._culqi_make_request(
                f'/charges/{culqi_transactions.provider_reference}', 
                method='GET'
            )
            return payment_record, culqi_transactions
        
        return False, culqi_transactions

    def _compute_valid_for_culqi_refund(self):
        """Calcula si la factura es válida para reembolso Culqi"""
        for move in self:
            has_culqi_tx = False
            if (move.move_type == 'out_refund' and 
                move._find_valid_culqi_transactions() and 
                move.state == "posted"):
                has_culqi_tx = True
            move.valid_for_culqi_refund = has_culqi_tx

    def _find_valid_culqi_transactions(self):
        """Encuentra transacciones Culqi válidas para reembolso"""
        self.ensure_one()

        # CASO 1: Para notas de crédito generadas desde factura
        transactions = self.reversed_entry_id.transaction_ids.filtered(
            lambda tx: tx.state == 'done' and tx.provider_id.code == 'culqi'
        )

        # CASO 2: Para notas de crédito generadas debido a devoluciones de entrega
        if not transactions and 'sale_line_ids' in self.invoice_line_ids._fields:
            transactions = self.invoice_line_ids.mapped(
                'sale_line_ids.order_id.transaction_ids'
            ).filtered(lambda tx: tx.state == 'done' and tx.provider_id.code == 'culqi')

        return transactions

    def action_register_refund_payment(self):
        """Acción para registrar pago de reembolso Culqi"""
        context = {
            'active_model': 'account.move',
            'active_ids': self.ids,
        }

        payment_record, culqi_transactions = self._get_culqi_payment_data_for_refund()
        
        # ✅ SIMPLIFICADO: Verificar disponibilidad de reembolso
        if payment_record:
            # Calcular monto disponible para reembolso
            total_amount_cents = payment_record.get('amount', 0)
            refunded_amount_cents = payment_record.get('amount_refunded', 0)
            remaining_amount_cents = total_amount_cents - refunded_amount_cents
            
            if remaining_amount_cents > 0:
                remaining_amount = remaining_amount_cents / 100  # Convertir de centavos
                context.update({
                    'default_journal_id': culqi_transactions.payment_id.journal_id.id,
                    'default_payment_method_id': culqi_transactions.payment_id.payment_method_id.id,
                    'default_amount': min(self.amount_residual, remaining_amount),
                    'default_is_culqi_refund': True,
                    'default_max_culqi_amount': remaining_amount,
                    'default_culqi_transaction_id': culqi_transactions.id
                })

        return {
            'name': _('Registrar Pago de Reembolso Culqi'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'context': context,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    # ✅ MÉTODOS SIMPLIFICADOS para integración con facturas
    def _culqi_get_payment_url(self):
        """Genera URL de pago para esta factura"""
        self.ensure_one()
        
        if self.state != 'posted' or self.payment_state != 'not_paid':
            return False
        
        # Obtener proveedor Culqi activo
        culqi_provider = self.env['payment.provider'].search([
            ('code', '=', 'culqi'),
            ('state', 'in', ['enabled', 'test']),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not culqi_provider:
            return False
        
        base_url = culqi_provider.get_base_url()
        return f"{base_url}/payment/culqi/pay?invoice_id={self.id}&amount={self.amount_residual}"

    def action_culqi_pay_invoice(self):
        """Acción para pagar factura con Culqi"""
        payment_url = self._culqi_get_payment_url()
        
        if not payment_url:
            raise UserError(_("No se puede generar el link de pago. Verifique la configuración de Culqi."))
        
        return {
            'type': 'ir.actions.act_url',
            'url': payment_url,
            'target': 'self',
        }
    
    # ✅ CAMPOS COMPUTADOS básicos para mostrar información Culqi
    show_button_culqi = fields.Boolean(compute="_compute_show_button_culqi")
    show_transaction_culqi_tab = fields.Boolean(compute="_compute_show_button_culqi")
    has_culqi_done = fields.Boolean(compute="_compute_show_button_culqi")
    has_culqi_pending = fields.Boolean(compute="_compute_show_button_culqi")
    culqi_total_paid = fields.Monetary(compute="_compute_culqi_summary", currency_field="currency_id")
    culqi_total_fee = fields.Monetary(compute="_compute_culqi_summary", currency_field="currency_id")

    @api.depends('transaction_ids')
    def _compute_show_button_culqi(self):
        """Computa visibilidad de botones Culqi"""
        for move in self:
            txs = move.transaction_ids.filtered(lambda t: t.provider_code == 'culqi')
            move.show_button_culqi = bool(txs)
            move.show_transaction_culqi_tab = bool(txs)
            move.has_culqi_done = any(t.state == 'done' for t in txs)
            move.has_culqi_pending = any(t.state == 'pending' for t in txs)

    @api.depends('transaction_ids')
    def _compute_culqi_summary(self):
        """Computa resumen de pagos Culqi"""
        for move in self:
            txs = move.transaction_ids.filtered(lambda t: t.provider_code == 'culqi' and t.state == 'done')
            move.culqi_total_paid = sum(t.amount for t in txs)
            move.culqi_total_fee = sum(t.culqi_fee or 0.0 for t in txs)