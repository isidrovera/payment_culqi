# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import UserError


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    @api.model
    def _get_payment_method_information(self):
        """Añade información de métodos de pago de Culqi al sistema contable"""
        res = super()._get_payment_method_information()

        # Obtener todos los códigos de métodos Culqi disponibles
        method_codes = self.env['payment.provider'].sudo()._get_all_culqi_methods_codes()
        
        for culqi_method_code in method_codes:
            res[f'culqi_{culqi_method_code}'] = {
                'mode': 'unique',  # Un método por journal
                'type': ('bank',)  # Tipo banco para todos los métodos Culqi
            }
        
        return res


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    culqi_refund_reference = fields.Char(
        string="Culqi Refund Reference",
        help="Referencia del reembolso en Culqi"
    )
    
    culqi_charge_id = fields.Char(
        string="Culqi Charge ID",
        help="ID del cargo en Culqi asociado a este pago"
    )
    
    culqi_payment_method_type = fields.Selection([
        ('card', 'Tarjeta de Crédito/Débito'),
        ('yape', 'Yape'),
        ('pagoefectivo', 'PagoEfectivo'),
        ('cuotealo', 'Cuotéalo'),
    ], string="Método de Pago Culqi", readonly=True)

    def _get_culqi_payment_data(self):
        """Obtiene datos del pago desde Culqi"""
        self.ensure_one()
        
        if not self.culqi_charge_id:
            return False
        
        # Buscar el proveedor Culqi
        culqi_provider = self.env['payment.provider'].search([
            ('code', '=', 'culqi'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not culqi_provider:
            return False
        
        try:
            payment_data = culqi_provider._culqi_make_request(
                f'/charges/{self.culqi_charge_id}',
                method='GET'
            )
            return payment_data
        except Exception as e:
            return False

    def action_view_culqi_payment(self):
        """Acción para ver el pago en el panel de Culqi"""
        self.ensure_one()
        
        if not self.culqi_charge_id:
            raise UserError(_("Este pago no tiene un ID de cargo en Culqi"))
        
        # URL del panel de Culqi
        culqi_panel_url = "https://panel.culqi.com"
        payment_url = f"{culqi_panel_url}/transactions/{self.culqi_charge_id}"
        
        return {
            'type': 'ir.actions.act_url',
            'url': payment_url,
            'target': 'new',
        }

    def _create_culqi_refund(self, amount_to_refund):
        """Crea un reembolso en Culqi"""
        self.ensure_one()
        
        if not self.culqi_charge_id:
            raise UserError(_("No se puede reembolsar: falta el ID del cargo en Culqi"))
        
        # Buscar el proveedor Culqi
        culqi_provider = self.env['payment.provider'].search([
            ('code', '=', 'culqi'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not culqi_provider:
            raise UserError(_("No se encontró un proveedor Culqi configurado"))
        
        # Crear reembolso en Culqi
        refund_data = {
            'charge_id': self.culqi_charge_id,
            'amount': int(amount_to_refund * 100),  # Convertir a centavos
            'reason': 'requested_by_customer'
        }
        
        try:
            result = culqi_provider._culqi_make_request('/refunds', refund_data)
            
            if result.get('object') == 'refund':
                self.culqi_refund_reference = result.get('id')
                return result
            else:
                raise UserError(_("Error en el reembolso: %s") % result.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            raise UserError(_("Error al procesar el reembolso: %s") % str(e))


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
                f'/charges/{self.culqi_transaction_id.provider_reference}',
                method='GET'
            )
            
            # Crear reembolso en Culqi
            refund_data = {
                'charge_id': self.culqi_transaction_id.provider_reference,
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
                    'culqi_charge_id': self.culqi_transaction_id.provider_reference
                })
                
                payment_record.reconciled_invoice_ids.write({
                    'culqi_refund_reference': refund['id']
                })

            return True

        return payments

    @api.onchange('amount')
    def _onchange_amount_culqi_validation(self):
        """Valida el monto para reembolsos Culqi"""
        if self.is_culqi_refund and self.max_culqi_amount:
            if self.amount > self.max_culqi_amount:
                return {
                    'warning': {
                        'title': _("Monto excedido"),
                        'message': _(
                            "El monto máximo para reembolso es %s. "
                            "El monto será ajustado automáticamente."
                        ) % self.max_culqi_amount
                    }
                }


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    def _get_culqi_method_info(self):
        """Obtiene información del método de pago Culqi"""
        self.ensure_one()
        
        if not self.code.startswith('culqi_'):
            return {}
        
        culqi_method_code = self.code.replace('culqi_', '')
        payment_method = self.env['payment.method'].search([
            ('code', '=', culqi_method_code),
            ('provider_ids.code', '=', 'culqi')
        ], limit=1)
        
        return {
            'method_code': culqi_method_code,
            'method_name': payment_method.name if payment_method else culqi_method_code.title(),
            'description': payment_method.culqi_description if payment_method else '',
        }