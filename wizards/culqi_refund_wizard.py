# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class CulqiRefundWizard(models.TransientModel):
    """Asistente para crear reembolsos Culqi de forma guiada."""
    _name = 'culqi.refund.wizard'
    _description = 'Asistente de Reembolso Culqi'

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    # Información de la transacción
    transaction_id = fields.Many2one(
        'payment.transaction',
        string='Transacción Original',
        required=True,
        readonly=True,
        help='Transacción que se va a reembolsar'
    )
    
    invoice_id = fields.Many2one(
        'account.move',
        string='Factura Relacionada',
        readonly=True,
        help='Factura asociada a la transacción'
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='transaction_id.partner_id',
        readonly=True
    )
    
    # Información de montos
    original_amount = fields.Monetary(
        string='Monto Original',
        related='transaction_id.amount',
        readonly=True,
        currency_field='currency_id'
    )
    
    already_refunded_amount = fields.Monetary(
        string='Ya Reembolsado',
        compute='_compute_refund_amounts',
        readonly=True,
        currency_field='currency_id'
    )
    
    available_amount = fields.Monetary(
        string='Disponible para Reembolso',
        compute='_compute_refund_amounts',
        readonly=True,
        currency_field='currency_id'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='transaction_id.currency_id',
        readonly=True
    )
    
    # Configuración del reembolso
    refund_type = fields.Selection([
        ('full', 'Reembolso Total'),
        ('partial', 'Reembolso Parcial'),
    ], string='Tipo de Reembolso', required=True, default='full')
    
    refund_amount = fields.Monetary(
        string='Monto a Reembolsar',
        currency_field='currency_id',
        help='Monto específico a reembolsar'
    )
    
    reason = fields.Selection([
        ('duplicate', 'Cargo Duplicado'),
        ('fraudulent', 'Fraudulento'),
        ('subscription_canceled', 'Suscripción Cancelada'),
        ('product_unacceptable', 'Producto Inaceptable'),
        ('product_not_received', 'Producto No Recibido'),
        ('unrecognized', 'No Reconocido'),
        ('credit_not_processed', 'Crédito No Procesado'),
        ('general', 'Razón General'),
        ('refund_expired', 'Reembolso Expirado'),
        ('other', 'Otro'),
    ], string='Motivo', required=True, default='general')
    
    reason_description = fields.Text(
        string='Descripción del Motivo',
        help='Descripción detallada del motivo del reembolso'
    )
    
    # Configuraciones adicionales
    create_credit_note = fields.Boolean(
        string='Crear Nota de Crédito',
        default=True,
        help='Crear automáticamente una nota de crédito'
    )
    
    notify_customer = fields.Boolean(
        string='Notificar al Cliente',
        default=True,
        help='Enviar notificación por email al cliente'
    )
    
    process_immediately = fields.Boolean(
        string='Procesar Inmediatamente',
        default=True,
        help='Procesar el reembolso inmediatamente en Culqi'
    )
    
    # Información de validación
    can_refund = fields.Boolean(
        string='Puede Reembolsar',
        compute='_compute_can_refund',
        help='Indica si la transacción puede ser reembolsada'
    )
    
    validation_message = fields.Text(
        string='Mensaje de Validación',
        compute='_compute_can_refund',
        readonly=True
    )
    
    # Información de contexto
    show_invoice_section = fields.Boolean(
        string='Mostrar Sección de Factura',
        compute='_compute_show_sections'
    )
    
    show_subscription_section = fields.Boolean(
        string='Mostrar Sección de Suscripción',
        compute='_compute_show_sections'
    )
    
    subscription_id = fields.Many2one(
        'culqi.subscription',
        string='Suscripción Relacionada',
        compute='_compute_related_records'
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('transaction_id')
    def _compute_refund_amounts(self):
        """Computa los montos de reembolso."""
        for wizard in self:
            if wizard.transaction_id:
                wizard.already_refunded_amount = wizard.transaction_id.culqi_refunded_amount or 0
                wizard.available_amount = wizard.original_amount - wizard.already_refunded_amount
            else:
                wizard.already_refunded_amount = 0
                wizard.available_amount = 0
    
    @api.depends('transaction_id', 'available_amount')
    def _compute_can_refund(self):
        """Determina si se puede realizar el reembolso."""
        for wizard in self:
            messages = []
            can_refund = True
            
            if not wizard.transaction_id:
                can_refund = False
                messages.append('No hay transacción seleccionada.')
            else:
                # Verificar estado de la transacción
                if wizard.transaction_id.state not in ['done', 'authorized']:
                    can_refund = False
                    messages.append('La transacción debe estar completada o autorizada.')
                
                # Verificar que tenga charge_id
                if not wizard.transaction_id.culqi_charge_id:
                    can_refund = False
                    messages.append('La transacción no tiene un cargo asociado en Culqi.')
                
                # Verificar monto disponible
                if wizard.available_amount <= 0:
                    can_refund = False
                    messages.append('No hay monto disponible para reembolso.')
                
                # Verificar proveedor
                if wizard.transaction_id.provider_code != 'culqi':
                    can_refund = False
                    messages.append('Solo se pueden reembolsar transacciones de Culqi.')
            
            wizard.can_refund = can_refund
            wizard.validation_message = '\n'.join(messages) if messages else 'La transacción puede ser reembolsada.'
    
    @api.depends('transaction_id')
    def _compute_show_sections(self):
        """Determina qué secciones mostrar en el wizard."""
        for wizard in self:
            wizard.show_invoice_section = bool(wizard.invoice_id)
            wizard.show_subscription_section = bool(
                wizard.transaction_id and 
                hasattr(wizard.transaction_id, 'culqi_subscription_id') and
                wizard.transaction_id.culqi_subscription_id
            )
    
    @api.depends('transaction_id')
    def _compute_related_records(self):
        """Computa registros relacionados."""
        for wizard in self:
            if wizard.transaction_id:
                # Buscar suscripción relacionada
                subscription = self.env['culqi.subscription'].search([
                    ('transaction_ids', 'in', wizard.transaction_id.ids)
                ], limit=1)
                wizard.subscription_id = subscription
            else:
                wizard.subscription_id = False

    # ==========================================
    # MÉTODOS ONCHANGE
    # ==========================================
    
    @api.onchange('refund_type')
    def _onchange_refund_type(self):
        """Actualiza el monto cuando cambia el tipo."""
        if self.refund_type == 'full':
            self.refund_amount = self.available_amount
        else:
            self.refund_amount = 0
    
    @api.onchange('reason')
    def _onchange_reason(self):
        """Actualiza la descripción basada en el motivo."""
        reason_descriptions = {
            'duplicate': 'El cargo fue duplicado por error del sistema',
            'fraudulent': 'El cargo fue identificado como fraudulento',
            'subscription_canceled': 'La suscripción fue cancelada por el cliente',
            'product_unacceptable': 'El producto o servicio no cumple con las expectativas del cliente',
            'product_not_received': 'El cliente no recibió el producto o servicio',
            'unrecognized': 'El cliente no reconoce el cargo en su estado de cuenta',
            'credit_not_processed': 'Un crédito prometido no fue procesado correctamente',
            'general': 'Motivo general solicitado por el comercio',
            'refund_expired': 'El reembolso fue solicitado después del periodo permitido',
        }
        
        if self.reason in reason_descriptions:
            self.reason_description = reason_descriptions[self.reason]

    # ==========================================
    # VALIDACIONES
    # ==========================================
    
    @api.constrains('refund_amount', 'available_amount')
    def _check_refund_amount(self):
        """Valida el monto del reembolso."""
        for wizard in self:
            if wizard.refund_amount <= 0:
                raise ValidationError(_('El monto del reembolso debe ser mayor a cero.'))
            
            if float_compare(wizard.refund_amount, wizard.available_amount, precision_digits=2) > 0:
                raise ValidationError(_(
                    'El monto del reembolso (%.2f) no puede ser mayor al monto disponible (%.2f).'
                ) % (wizard.refund_amount, wizard.available_amount))
    
    @api.constrains('refund_type', 'refund_amount', 'available_amount')
    def _check_refund_type_consistency(self):
        """Valida la consistencia entre tipo y monto."""
        for wizard in self:
            if wizard.refund_type == 'full':
                if not float_is_zero(wizard.refund_amount - wizard.available_amount, precision_digits=2):
                    raise ValidationError(_(
                        'Para un reembolso total, el monto debe ser igual al monto disponible (%.2f).'
                    ) % wizard.available_amount)

    # ==========================================
    # MÉTODOS PRINCIPALES
    # ==========================================
    
    def action_create_refund(self):
        """Crea el reembolso en Odoo y opcionalmente en Culqi."""
        self.ensure_one()
        
        if not self.can_refund:
            raise UserError(_('No se puede procesar el reembolso: %s') % self.validation_message)
        
        # Crear registro de reembolso
        refund_vals = {
            'transaction_id': self.transaction_id.id,
            'amount': self.refund_amount,
            'reason': self.reason,
            'reason_description': self.reason_description,
            'refund_type': 'manual',
        }
        
        refund = self.env['culqi.refund'].create(refund_vals)
        
        try:
            # Procesar en Culqi si está configurado
            if self.process_immediately:
                refund.create_in_culqi()
            
            # Crear nota de crédito si está configurado
            if self.create_credit_note and self.invoice_id:
                self._create_credit_note(refund)
            
            # Enviar notificación al cliente si está configurado
            if self.notify_customer:
                self._send_customer_notification(refund)
            
            # Mensaje de éxito
            message = _('Reembolso creado exitosamente por %.2f %s') % (
                self.refund_amount, self.currency_id.symbol
            )
            
            if self.process_immediately:
                message += _('\nEl reembolso ha sido procesado en Culqi.')
            else:
                message += _('\nEl reembolso debe ser procesado manualmente en Culqi.')
            
            # Retornar acción de éxito
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reembolso Creado'),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                },
                'target': 'new',
            }
            
        except Exception as e:
            _logger.error('Error al crear reembolso: %s', str(e))
            
            # Si el reembolso se creó pero falló el procesamiento, mantenerlo pero marcarlo como fallido
            if refund.exists():
                refund.write({
                    'state': 'failed',
                    'error_message': str(e)
                })
            
            raise UserError(_('Error al procesar el reembolso: %s') % str(e))
    
    def action_preview_refund(self):
        """Muestra una vista previa del reembolso antes de crearlo."""
        self.ensure_one()
        
        if not self.can_refund:
            raise UserError(_('No se puede procesar el reembolso: %s') % self.validation_message)
        
        # Preparar información para la vista previa
        preview_data = {
            'wizard_id': self.id,
            'transaction_reference': self.transaction_id.reference,
            'customer_name': self.partner_id.name,
            'original_amount': self.original_amount,
            'refund_amount': self.refund_amount,
            'refund_type': dict(self._fields['refund_type'].selection)[self.refund_type],
            'reason': dict(self._fields['reason'].selection)[self.reason],
            'reason_description': self.reason_description,
            'will_create_credit_note': self.create_credit_note,
            'will_notify_customer': self.notify_customer,
            'will_process_immediately': self.process_immediately,
        }
        
        return {
            'name': _('Vista Previa del Reembolso'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.refund.preview.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_preview_data': preview_data},
        }
    
    def _create_credit_note(self, refund):
        """Crea una nota de crédito para el reembolso."""
        if not self.invoice_id:
            return False
        
        # Crear nota de crédito
        credit_note_vals = {
            'move_type': 'out_refund',
            'partner_id': self.partner_id.id,
            'company_id': self.invoice_id.company_id.id,
            'currency_id': self.currency_id.id,
            'payment_reference': refund.name,
            'ref': f'Reembolso Culqi {refund.name}',
            'invoice_origin': self.invoice_id.name,
            'reversed_entry_id': self.invoice_id.id,
        }
        
        # Crear líneas proporcionales
        invoice_lines = []
        total_invoice_amount = self.invoice_id.amount_total
        refund_proportion = self.refund_amount / total_invoice_amount
        
        for line in self.invoice_id.invoice_line_ids.filtered(lambda l: not l.display_type):
            refund_quantity = line.quantity * refund_proportion
            
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': f'Reembolso: {line.name}',
                'quantity': refund_quantity,
                'price_unit': line.price_unit,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
                'account_id': line.account_id.id,
            }))
        
        credit_note_vals['invoice_line_ids'] = invoice_lines
        
        credit_note = self.env['account.move'].create(credit_note_vals)
        credit_note.action_post()
        
        # Vincular con el reembolso
        refund.credit_note_id = credit_note
        
        return credit_note
    
    def _send_customer_notification(self, refund):
        """Envía notificación al cliente sobre el reembolso."""
        if not self.partner_id.email:
            return False
        
        template = self.env.ref(
            'payment_culqi.refund_notification_email_template',
            raise_if_not_found=False
        )
        
        if template:
            template.send_mail(refund.id, force_send=True)
            return True
        
        return False

    # ==========================================
    # MÉTODOS DE UTILIDAD
    # ==========================================
    
    @api.model
    def default_get(self, fields_list):
        """Configura valores por defecto basados en el contexto."""
        defaults = super().default_get(fields_list)
        
        # Configurar transacción desde el contexto
        transaction_id = self.env.context.get('default_transaction_id')
        invoice_id = self.env.context.get('default_invoice_id')
        
        if transaction_id:
            transaction = self.env['payment.transaction'].browse(transaction_id)
            defaults.update({
                'transaction_id': transaction_id,
                'refund_amount': transaction.amount - (transaction.culqi_refunded_amount or 0),
            })
            
            # Si viene de una factura
            if invoice_id:
                defaults['invoice_id'] = invoice_id
            elif transaction.invoice_ids:
                defaults['invoice_id'] = transaction.invoice_ids[0].id
        
        # Configurar monto por defecto desde el contexto
        amount = self.env.context.get('default_amount')
        if amount:
            defaults['refund_amount'] = amount
            defaults['refund_type'] = 'partial' if amount else 'full'
        
        return defaults
    
    def action_cancel(self):
        """Cancela el wizard sin crear el reembolso."""
        return {'type': 'ir.actions.act_window_close'}


class CulqiRefundPreviewWizard(models.TransientModel):
    """Wizard para mostrar vista previa del reembolso."""
    _name = 'culqi.refund.preview.wizard'
    _description = 'Vista Previa de Reembolso Culqi'

    # ==========================================
    # CAMPOS DE VISTA PREVIA
    # ==========================================
    
    preview_data = fields.Text(
        string='Datos de Vista Previa',
        readonly=True
    )
    
    wizard_id = fields.Integer(
        string='ID del Wizard Original',
        readonly=True
    )
    
    # Campos de solo lectura para mostrar información
    transaction_reference = fields.Char(
        string='Referencia de Transacción',
        readonly=True
    )
    
    customer_name = fields.Char(
        string='Cliente',
        readonly=True
    )
    
    original_amount = fields.Float(
        string='Monto Original',
        readonly=True
    )
    
    refund_amount = fields.Float(
        string='Monto a Reembolsar',
        readonly=True
    )
    
    refund_type = fields.Char(
        string='Tipo de Reembolso',
        readonly=True
    )
    
    reason = fields.Char(
        string='Motivo',
        readonly=True
    )
    
    reason_description = fields.Text(
        string='Descripción',
        readonly=True
    )
    
    will_create_credit_note = fields.Boolean(
        string='Creará Nota de Crédito',
        readonly=True
    )
    
    will_notify_customer = fields.Boolean(
        string='Notificará al Cliente',
        readonly=True
    )
    
    will_process_immediately = fields.Boolean(
        string='Procesará Inmediatamente',
        readonly=True
    )

    # ==========================================
    # MÉTODOS
    # ==========================================
    
    @api.model
    def default_get(self, fields_list):
        """Configura los datos de vista previa."""
        defaults = super().default_get(fields_list)
        
        preview_data = self.env.context.get('default_preview_data', {})
        defaults.update(preview_data)
        
        return defaults
    
    def action_confirm_refund(self):
        """Confirma y procesa el reembolso."""
        self.ensure_one()
        
        # Obtener el wizard original
        original_wizard = self.env['culqi.refund.wizard'].browse(self.wizard_id)
        
        if not original_wizard.exists():
            raise UserError(_('El wizard original no existe.'))
        
        # Procesar el reembolso
        return original_wizard.action_create_refund()
    
    def action_back_to_wizard(self):
        """Regresa al wizard original para hacer cambios."""
        self.ensure_one()
        
        return {
            'name': _('Crear Reembolso Culqi'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.refund.wizard',
            'res_id': self.wizard_id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_cancel(self):
        """Cancela el proceso de reembolso."""
        return {'type': 'ir.actions.act_window_close'}


class CulqiBulkRefundWizard(models.TransientModel):
    """Wizard para procesar múltiples reembolsos."""
    _name = 'culqi.bulk.refund.wizard'
    _description = 'Reembolsos Masivos Culqi'

    # ==========================================
    # CAMPOS
    # ==========================================
    
    transaction_ids = fields.Many2many(
        'payment.transaction',
        string='Transacciones a Reembolsar',
        required=True,
        domain=[('provider_code', '=', 'culqi'), ('state', '=', 'done')]
    )
    
    refund_type = fields.Selection([
        ('full', 'Reembolso Total'),
        ('percentage', 'Porcentaje'),
        ('fixed_amount', 'Monto Fijo'),
    ], string='Tipo de Reembolso', required=True, default='full')
    
    percentage = fields.Float(
        string='Porcentaje',
        help='Porcentaje del monto original a reembolsar'
    )
    
    fixed_amount = fields.Float(
        string='Monto Fijo',
        help='Monto fijo a reembolsar por transacción'
    )
    
    reason = fields.Selection([
        ('duplicate', 'Cargo Duplicado'),
        ('fraudulent', 'Fraudulento'),
        ('subscription_canceled', 'Suscripción Cancelada'),
        ('product_unacceptable', 'Producto Inaceptable'),
        ('product_not_received', 'Producto No Recibido'),
        ('general', 'Razón General'),
        ('other', 'Otro'),
    ], string='Motivo', required=True, default='general')
    
    reason_description = fields.Text(
        string='Descripción del Motivo',
        required=True
    )
    
    create_credit_notes = fields.Boolean(
        string='Crear Notas de Crédito',
        default=True
    )
    
    notify_customers = fields.Boolean(
        string='Notificar a Clientes',
        default=True
    )
    
    process_immediately = fields.Boolean(
        string='Procesar Inmediatamente',
        default=False,
        help='Procesar todos los reembolsos en Culqi inmediatamente'
    )

    # ==========================================
    # MÉTODOS
    # ==========================================
    
    def action_process_bulk_refunds(self):
        """Procesa todos los reembolsos seleccionados."""
        self.ensure_one()
        
        if not self.transaction_ids:
            raise UserError(_('Debe seleccionar al menos una transacción.'))
        
        created_refunds = self.env['culqi.refund']
        failed_transactions = []
        
        for transaction in self.transaction_ids:
            try:
                # Calcular monto del reembolso
                if self.refund_type == 'full':
                    refund_amount = transaction.amount - (transaction.culqi_refunded_amount or 0)
                elif self.refund_type == 'percentage':
                    refund_amount = transaction.amount * (self.percentage / 100)
                else:  # fixed_amount
                    refund_amount = self.fixed_amount
                
                # Validar monto disponible
                available_amount = transaction.amount - (transaction.culqi_refunded_amount or 0)
                if refund_amount > available_amount:
                    failed_transactions.append(f"{transaction.reference}: Monto excede disponible")
                    continue
                
                # Crear reembolso
                refund = self.env['culqi.refund'].create({
                    'transaction_id': transaction.id,
                    'amount': refund_amount,
                    'reason': self.reason,
                    'reason_description': self.reason_description,
                    'refund_type': 'manual',
                })
                
                # Procesar en Culqi si está configurado
                if self.process_immediately:
                    refund.create_in_culqi()
                
                created_refunds |= refund
                
            except Exception as e:
                failed_transactions.append(f"{transaction.reference}: {str(e)}")
        
        # Mensaje de resultado
        message = _('Procesados %d reembolsos exitosamente.') % len(created_refunds)
        
        if failed_transactions:
            message += _('\n\nTransacciones fallidas:\n%s') % '\n'.join(failed_transactions)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reembolsos Procesados'),
                'message': message,
                'type': 'warning' if failed_transactions else 'success',
                'sticky': True,
            }
        }