# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    is_culqi_refund = fields.Boolean(
        string="Es Reembolso Culqi",
        help="Indica si este pago es un reembolso procesado por Culqi"
    )
    
    max_culqi_amount = fields.Float(
        string="Monto Máximo Culqi",
        help="Monto máximo que se puede reembolsar en Culqi"
    )
    
    culqi_transaction_id = fields.Many2one(
        'payment.transaction',
        string="Transacción Culqi",
        help="Transacción de Culqi asociada al reembolso"
    )

    def action_create_payments(self):
        """Sobrescribe para manejar reembolsos de Culqi"""
        payments = super().action_create_payments()
        
        # Procesamos un registro a la vez
        if len(self) == 1 and self.is_culqi_refund:
            # Validar monto máximo
            if not self.max_culqi_amount:
                raise UserError(_("El monto completo ya fue reembolsado para este pago"))
            
            if self.amount > self.max_culqi_amount:
                raise UserError(_(
                    "El monto máximo que puedes reembolsar es %s. "
                    "Por favor cambia el monto del reembolso."
                ) % self.max_culqi_amount)

            # Obtener datos del pago desde Culqi
            payment_data = self.culqi_transaction_id.provider_id._culqi_make_request(
                f'/charges/{self.culqi_transaction_id.culqi_charge_id}',
                method='GET'
            )
            
            # Crear reembolso en Culqi
            refund_data = {
                'charge_id': self.culqi_transaction_id.culqi_charge_id,
                'amount': int(self.amount * 100),  # Convertir a centavos
                'reason': 'requested_by_customer'
            }
            
            refund = self.culqi_transaction_id.provider_id._culqi_make_request(
                '/refunds', 
                refund_data
            )

            if refund.get('object') == 'refund' and payments.get('res_id'):
                description = refund['id']
                payment_record = self.env['account.payment'].browse(payments.get('res_id'))

                # Actualizar referencias de reembolso
                if (payment_record.reconciled_invoice_ids and 
                    payment_record.reconciled_invoice_ids.culqi_refund_reference):
                    description = f"{payment_record.reconciled_invoice_ids.culqi_refund_reference},{description}"

                payment_record.write({
                    'culqi_refund_reference': description,
                    'culqi_charge_id': self.culqi_transaction_id.culqi_charge_id
                })
                
                payment_record.reconciled_invoice_ids.write({
                    'culqi_refund_reference': refund['id']
                })

            return True

        return payments