# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import json
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """Extensión del modelo account.move para integrar con Culqi."""
    _inherit = 'account.move'

    # ==========================================
    # CAMPOS ESPECÍFICOS DE CULQI
    # ==========================================
    
    # Relación con suscripciones
    culqi_subscription_id = fields.Many2one(
        'culqi.subscription',
        string='Suscripción Culqi',
        help='Suscripción que generó esta factura',
        tracking=True
    )
    
    # Relación con reembolsos
    culqi_refund_ids = fields.One2many(
        'culqi.refund',
        'credit_note_id',
        string='Reembolsos Culqi',
        help='Reembolsos asociados a esta nota de crédito'
    )
    
    # Información de pago Culqi
    culqi_payment_method = fields.Selection([
        ('card', 'Tarjeta de Crédito/Débito'),
        ('pagoefectivo', 'PagoEfectivo'),
        ('yape', 'Yape'),
        ('billetera', 'Billetera Digital'),
    ], string='Método de Pago Culqi', help='Método de pago utilizado en Culqi')
    
    culqi_transaction_id = fields.Many2one(
        'payment.transaction',
        string='Transacción Culqi',
        help='Transacción de pago asociada',
        compute='_compute_culqi_transaction',
        store=True
    )
    
    culqi_charge_id = fields.Char(
        string='ID de Cargo Culqi',
        help='ID del cargo en Culqi',
        related='culqi_transaction_id.culqi_charge_id',
        readonly=True
    )
    
    # Estados de pago específicos de Culqi
    culqi_payment_state = fields.Selection([
        ('not_applicable', 'No Aplicable'),
        ('pending', 'Pago Pendiente'),
        ('processing', 'Procesando'),
        ('paid', 'Pagado'),
        ('failed', 'Pago Fallido'),
        ('refunded', 'Reembolsado'),
        ('partially_refunded', 'Parcialmente Reembolsado'),
    ], string='Estado de Pago Culqi', 
       compute='_compute_culqi_payment_state', 
       store=True)
    
    # Información de reembolsos
    culqi_refundable_amount = fields.Monetary(
        string='Monto Reembolsable',
        compute='_compute_culqi_refund_amounts',
        help='Monto disponible para reembolso en Culqi'
    )
    
    culqi_refunded_amount = fields.Monetary(
        string='Monto Reembolsado',
        compute='_compute_culqi_refund_amounts',
        help='Monto ya reembolsado en Culqi'
    )
    
    # Configuración de pagos
    culqi_enable_online_payment = fields.Boolean(
        string='Habilitar Pago Online',
        default=True,
        help='Permite que esta factura sea pagada online con Culqi'
    )
    
    culqi_payment_url = fields.Char(
        string='URL de Pago',
        compute='_compute_culqi_payment_url',
        help='URL para pagar esta factura online'
    )
    
    # Campos de seguimiento
    culqi_payment_deadline = fields.Date(
        string='Fecha Límite de Pago',
        compute='_compute_culqi_payment_deadline',
        store=True,
        help='Fecha límite para el pago online'
    )
    
    # Contadores
    culqi_refund_count = fields.Integer(
        string='Número de Reembolsos',
        compute='_compute_culqi_refund_count'
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('transaction_ids')
    def _compute_culqi_transaction(self):
        """Computa la transacción Culqi asociada."""
        for move in self:
            culqi_tx = move.transaction_ids.filtered(
                lambda tx: tx.provider_code == 'culqi' and tx.state == 'done'
            )
            move.culqi_transaction_id = culqi_tx[0] if culqi_tx else False
    
    @api.depends('culqi_transaction_id.state', 'payment_state', 'culqi_refund_ids.state')
    def _compute_culqi_payment_state(self):
        """Computa el estado de pago específico de Culqi."""
        for move in self:
            if not move.culqi_transaction_id:
                move.culqi_payment_state = 'not_applicable'
                continue
            
            tx = move.culqi_transaction_id
            
            # Verificar si hay reembolsos
            successful_refunds = move.culqi_refund_ids.filtered(lambda r: r.state == 'succeeded')
            total_refunded = sum(successful_refunds.mapped('amount'))
            
            if total_refunded > 0:
                if float_compare(total_refunded, move.amount_total, precision_digits=2) >= 0:
                    move.culqi_payment_state = 'refunded'
                else:
                    move.culqi_payment_state = 'partially_refunded'
            elif tx.state == 'done':
                move.culqi_payment_state = 'paid'
            elif tx.state == 'pending':
                move.culqi_payment_state = 'pending'
            elif tx.state == 'authorized':
                move.culqi_payment_state = 'processing'
            elif tx.state in ['error', 'cancel']:
                move.culqi_payment_state = 'failed'
            else:
                move.culqi_payment_state = 'pending'
    
    @api.depends('culqi_transaction_id', 'culqi_refund_ids')
    def _compute_culqi_refund_amounts(self):
        """Computa los montos de reembolso."""
        for move in self:
            if move.culqi_transaction_id and move.culqi_transaction_id.state == 'done':
                # Monto total reembolsado
                successful_refunds = move.culqi_refund_ids.filtered(lambda r: r.state == 'succeeded')
                refunded_amount = sum(successful_refunds.mapped('amount'))
                
                # Monto disponible para reembolso
                refundable_amount = max(0, move.amount_total - refunded_amount)
                
                move.culqi_refunded_amount = refunded_amount
                move.culqi_refundable_amount = refundable_amount
            else:
                move.culqi_refunded_amount = 0
                move.culqi_refundable_amount = 0
    
    @api.depends('culqi_refund_ids')
    def _compute_culqi_refund_count(self):
        """Computa el número de reembolsos."""
        for move in self:
            move.culqi_refund_count = len(move.culqi_refund_ids)
    
    @api.depends('name', 'access_token')
    def _compute_culqi_payment_url(self):
        """Computa la URL de pago online."""
        for move in self:
            if (move.move_type == 'out_invoice' and 
                move.state == 'posted' and 
                move.payment_state in ['not_paid', 'partial'] and
                move.culqi_enable_online_payment):
                
                base_url = move.get_base_url()
                move.culqi_payment_url = f"{base_url}/my/invoices/{move.id}/pay?access_token={move.access_token}"
            else:
                move.culqi_payment_url = False
    
    @api.depends('invoice_date_due', 'invoice_date')
    def _compute_culqi_payment_deadline(self):
        """Computa la fecha límite de pago online."""
        for move in self:
            if move.move_type == 'out_invoice':
                # Usar fecha de vencimiento si existe, sino fecha de factura + 30 días
                if move.invoice_date_due:
                    move.culqi_payment_deadline = move.invoice_date_due
                elif move.invoice_date:
                    move.culqi_payment_deadline = move.invoice_date + timedelta(days=30)
                else:
                    move.culqi_payment_deadline = False
            else:
                move.culqi_payment_deadline = False

    # ==========================================
    # VALIDACIONES Y CONSTRAINS
    # ==========================================
    
    @api.constrains('culqi_subscription_id', 'move_type')
    def _check_subscription_invoice_type(self):
        """Valida que las facturas de suscripción sean del tipo correcto."""
        for move in self:
            if move.culqi_subscription_id and move.move_type != 'out_invoice':
                raise ValidationError(_(
                    'Las facturas de suscripción deben ser facturas de cliente (out_invoice).'
                ))

    # ==========================================
    # MÉTODOS DE PAGO CULQI
    # ==========================================
    
    def action_pay_with_culqi(self):
        """Acción para pagar la factura con Culqi."""
        self.ensure_one()
        
        if self.move_type != 'out_invoice':
            raise UserError(_('Solo se pueden pagar facturas de cliente.'))
        
        if self.state != 'posted':
            raise UserError(_('Solo se pueden pagar facturas confirmadas.'))
        
        if self.payment_state == 'paid':
            raise UserError(_('Esta factura ya está pagada.'))
        
        # Obtener proveedor Culqi
        provider = self.env['payment.provider'].search([
            ('code', '=', 'culqi'),
            ('state', 'in', ['enabled', 'test'])
        ], limit=1)
        
        if not provider:
            raise UserError(_('El proveedor de pago Culqi no está disponible.'))
        
        # Crear transacción de pago
        transaction_vals = {
            'reference': f"INV-{self.name}",
            'amount': self.amount_residual,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'provider_id': provider.id,
            'invoice_ids': [(4, self.id)],
            'operation': 'online_direct',
        }
        
        transaction = self.env['payment.transaction'].create(transaction_vals)
        
        # Redireccionar al formulario de pago
        return {
            'type': 'ir.actions.act_url',
            'url': f'/payment/pay?tx_ref={transaction.reference}',
            'target': 'self',
        }
    
    def action_create_culqi_refund(self):
        """Acción para crear un reembolso Culqi."""
        self.ensure_one()
        
        if not self.culqi_transaction_id:
            raise UserError(_('Esta factura no tiene una transacción Culqi asociada.'))
        
        if self.culqi_refundable_amount <= 0:
            raise UserError(_('No hay monto disponible para reembolso.'))
        
        # Abrir wizard de reembolso
        return {
            'name': _('Crear Reembolso Culqi'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.refund.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': self.culqi_transaction_id.id,
                'default_invoice_id': self.id,
                'default_amount': self.culqi_refundable_amount,
            },
        }
    
    def action_view_culqi_refunds(self):
        """Acción para ver los reembolsos de la factura."""
        self.ensure_one()
        
        return {
            'name': _('Reembolsos Culqi'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.refund',
            'view_mode': 'tree,form',
            'domain': [('credit_note_id', '=', self.id)],
            'context': {'default_transaction_id': self.culqi_transaction_id.id},
        }
    
    def action_view_culqi_transaction(self):
        """Acción para ver la transacción Culqi."""
        self.ensure_one()
        
        if not self.culqi_transaction_id:
            raise UserError(_('Esta factura no tiene una transacción Culqi asociada.'))
        
        return {
            'name': _('Transacción Culqi'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'res_id': self.culqi_transaction_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_send_payment_link(self):
        """Envía enlace de pago por email al cliente."""
        self.ensure_one()
        
        if not self.culqi_payment_url:
            raise UserError(_('No se puede generar enlace de pago para esta factura.'))
        
        # Usar template de email para enviar enlace de pago
        template = self.env.ref('payment_culqi.invoice_payment_link_email_template', raise_if_not_found=False)
        
        if template:
            template.send_mail(self.id, force_send=True)
            
            self.message_post(
                body=_('Enlace de pago enviado por email a %s') % self.partner_id.email
            )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Enlace Enviado'),
                'message': _('El enlace de pago ha sido enviado por email al cliente.'),
                'type': 'success',
            }
        }

    # ==========================================
    # MÉTODOS DE SUSCRIPCIÓN
    # ==========================================
    
    def _create_subscription_invoice_lines(self, subscription, period_start, period_end):
        """Crea líneas de factura para una suscripción."""
        self.ensure_one()
        
        if not subscription.plan_id.product_id:
            raise UserError(_('El plan de suscripción debe tener un producto asociado.'))
        
        product = subscription.plan_id.product_id
        
        # Descripción del periodo
        period_description = _('Periodo del %s al %s') % (
            period_start.strftime('%d/%m/%Y'),
            period_end.strftime('%d/%m/%Y')
        )
        
        line_vals = {
            'product_id': product.id,
            'name': f"{product.name} - {period_description}",
            'quantity': subscription.quantity,
            'price_unit': subscription.plan_id.amount,
            'account_id': product.property_account_income_id.id or 
                         product.categ_id.property_account_income_categ_id.id,
            'tax_ids': [(6, 0, product.taxes_id.ids)],
        }
        
        self.write({
            'invoice_line_ids': [(0, 0, line_vals)]
        })
    
    @api.model
    def create_subscription_invoice(self, subscription, period_start, period_end):
        """Crea una factura para un periodo de suscripción."""
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': subscription.partner_id.id,
            'company_id': subscription.company_id.id,
            'currency_id': subscription.currency_id.id,
            'culqi_subscription_id': subscription.id,
            'invoice_date': fields.Date.today(),
            'payment_reference': subscription.reference,
            'ref': f'Suscripción {subscription.reference} - Ciclo {subscription.billing_cycle_count + 1}',
        }
        
        invoice = self.create(invoice_vals)
        invoice._create_subscription_invoice_lines(subscription, period_start, period_end)
        
        # Confirmar la factura
        invoice.action_post()
        
        return invoice

    # ==========================================
    # MÉTODOS DE PORTAL DEL CLIENTE
    # ==========================================
    
    def get_portal_payment_methods(self):
        """Obtiene los métodos de pago disponibles para el portal."""
        self.ensure_one()
        
        # Obtener proveedores de pago habilitados
        providers = self.env['payment.provider'].sudo().search([
            ('state', 'in', ['enabled', 'test']),
            ('is_published', '=', True),
        ])
        
        # Filtrar por moneda si es necesario
        compatible_providers = providers.filtered(
            lambda p: self.currency_id in p._get_supported_currencies()
        )
        
        return compatible_providers
    
    def create_portal_payment_transaction(self, provider_id, **kwargs):
        """Crea una transacción de pago desde el portal."""
        self.ensure_one()
        
        provider = self.env['payment.provider'].sudo().browse(provider_id)
        
        if not provider.exists():
            raise UserError(_('Proveedor de pago no válido.'))
        
        # Crear transacción
        transaction_vals = {
            'reference': f"INV-{self.name}-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}",
            'amount': self.amount_residual,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'provider_id': provider.id,
            'invoice_ids': [(4, self.id)],
            'operation': 'online_direct',
        }
        
        # Agregar metadatos específicos de Culqi
        if provider.code == 'culqi':
            metadata = {
                'invoice_id': self.id,
                'invoice_number': self.name,
                'customer_email': self.partner_id.email,
                'due_date': self.invoice_date_due.isoformat() if self.invoice_date_due else None,
            }
            transaction_vals['culqi_metadata'] = json.dumps(metadata)
        
        return self.env['payment.transaction'].sudo().create(transaction_vals)

    # ==========================================
    # MÉTODOS DE REPORTES
    # ==========================================
    
    def _get_culqi_payment_summary(self):
        """Obtiene resumen de pagos Culqi para reportes."""
        self.ensure_one()
        
        summary = {
            'invoice_number': self.name,
            'partner_name': self.partner_id.name,
            'amount_total': self.amount_total,
            'payment_state': self.payment_state,
            'culqi_payment_state': self.culqi_payment_state,
            'payment_method': self.culqi_payment_method,
            'transaction_reference': self.culqi_transaction_id.reference if self.culqi_transaction_id else None,
            'charge_id': self.culqi_charge_id,
            'refunded_amount': self.culqi_refunded_amount,
            'refundable_amount': self.culqi_refundable_amount,
            'subscription_reference': self.culqi_subscription_id.reference if self.culqi_subscription_id else None,
        }
        
        return summary
    
    @api.model
    def get_culqi_revenue_report(self, date_from, date_to):
        """Genera reporte de ingresos por Culqi."""
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('culqi_transaction_id', '!=', False),
        ]
        
        invoices = self.search(domain)
        
        # Agrupar por método de pago
        payment_methods = {}
        total_revenue = 0
        total_refunded = 0
        
        for invoice in invoices:
            method = invoice.culqi_payment_method or 'unknown'
            
            if method not in payment_methods:
                payment_methods[method] = {
                    'count': 0,
                    'revenue': 0,
                    'refunded': 0,
                    'net_revenue': 0,
                }
            
            payment_methods[method]['count'] += 1
            payment_methods[method]['revenue'] += invoice.amount_total
            payment_methods[method]['refunded'] += invoice.culqi_refunded_amount
            payment_methods[method]['net_revenue'] += (invoice.amount_total - invoice.culqi_refunded_amount)
            
            total_revenue += invoice.amount_total
            total_refunded += invoice.culqi_refunded_amount
        
        return {
            'period': {'from': date_from, 'to': date_to},
            'summary': {
                'total_invoices': len(invoices),
                'total_revenue': total_revenue,
                'total_refunded': total_refunded,
                'net_revenue': total_revenue - total_refunded,
            },
            'by_payment_method': payment_methods,
        }

    # ==========================================
    # MÉTODOS OVERRIDE
    # ==========================================
    
    def action_post(self):
        """Override para procesar facturas de suscripción."""
        result = super().action_post()
        
        # Procesar facturas de suscripción
        subscription_invoices = self.filtered('culqi_subscription_id')
        for invoice in subscription_invoices:
            # Enviar notificación de nueva factura al cliente
            if invoice.partner_id.email:
                template = self.env.ref(
                    'payment_culqi.subscription_invoice_email_template', 
                    raise_if_not_found=False
                )
                if template:
                    template.send_mail(invoice.id)
        
        return result
    
    def _compute_access_url(self):
        """Override para incluir parámetros de pago en la URL."""
        super()._compute_access_url()
        
        for invoice in self:
            if (invoice.move_type == 'out_invoice' and 
                invoice.state == 'posted' and 
                invoice.payment_state in ['not_paid', 'partial']):
                
                # Agregar parámetro para mostrar opciones de pago
                if '?' in invoice.access_url:
                    invoice.access_url += '&show_payment=1'
                else:
                    invoice.access_url += '?show_payment=1'

    # ==========================================
    # MÉTODOS DE AUTOMATIZACIÓN
    # ==========================================
    
    @api.model
    def _cron_send_payment_reminders(self):
        """Cron job para enviar recordatorios de pago."""
        # Buscar facturas vencidas con pago online habilitado
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('culqi_enable_online_payment', '=', True),
            ('invoice_date_due', '<', fields.Date.today()),
            ('invoice_date_due', '>=', fields.Date.today() - timedelta(days=30)),  # No más de 30 días vencidas
        ]
        
        overdue_invoices = self.search(domain)
        
        # Filtrar las que no han recibido recordatorio en los últimos 7 días
        invoices_to_remind = overdue_invoices.filtered(
            lambda inv: not inv.message_ids.filtered(
                lambda msg: msg.create_date >= fields.Datetime.now() - timedelta(days=7) and
                           'recordatorio de pago' in (msg.body or '').lower()
            )
        )
        
        template = self.env.ref(
            'payment_culqi.invoice_payment_reminder_email_template',
            raise_if_not_found=False
        )
        
        sent_count = 0
        for invoice in invoices_to_remind:
            if invoice.partner_id.email and template:
                try:
                    template.send_mail(invoice.id, force_send=True)
                    invoice.message_post(
                        body=_('Recordatorio de pago enviado automáticamente')
                    )
                    sent_count += 1
                except Exception as e:
                    _logger.error('Error enviando recordatorio para factura %s: %s', invoice.name, str(e))
        
        _logger.info('Enviados %d recordatorios de pago automáticos', sent_count)
        return sent_count
    
    @api.model
    def _cron_update_payment_deadlines(self):
        """Actualiza fechas límite de pago expiradas."""
        expired_invoices = self.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('culqi_payment_deadline', '<', fields.Date.today()),
            ('culqi_enable_online_payment', '=', True),
        ])
        
        for invoice in expired_invoices:
            # Deshabilitar pago online para facturas muy vencidas (más de 60 días)
            if invoice.invoice_date_due and invoice.invoice_date_due < fields.Date.today() - timedelta(days=60):
                invoice.culqi_enable_online_payment = False
                invoice.message_post(
                    body=_('Pago online deshabilitado automáticamente por vencimiento excesivo')
                )
        
        return len(expired_invoices)