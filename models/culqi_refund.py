# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import json
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CulqiRefund(models.Model):
    _name = 'culqi.refund'
    _description = 'Reembolso Culqi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    name = fields.Char(
        string='Número de Reembolso',
        required=True,
        copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('culqi.refund') or '/',
        tracking=True
    )
    
    display_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_display_name',
        store=True
    )
    
    # Identificadores
    culqi_refund_id = fields.Char(
        string='ID de Reembolso Culqi',
        readonly=True,
        tracking=True,
        help='ID único del reembolso en Culqi'
    )
    
    culqi_charge_id = fields.Char(
        string='ID de Cargo Culqi',
        readonly=True,
        help='ID del cargo original que se está reembolsando'
    )
    
    # Relaciones principales
    transaction_id = fields.Many2one(
        'payment.transaction',
        string='Transacción Original',
        required=True,
        ondelete='cascade',
        tracking=True,
        help='Transacción original que se está reembolsando'
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        related='transaction_id.partner_id',
        store=True,
        readonly=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='transaction_id.company_id',
        store=True,
        readonly=True
    )
    
    provider_id = fields.Many2one(
        'payment.provider',
        string='Proveedor de Pago',
        related='transaction_id.provider_id',
        store=True,
        readonly=True
    )
    
    # Información del reembolso
    amount = fields.Monetary(
        string='Monto a Reembolsar',
        required=True,
        tracking=True,
        currency_field='currency_id'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='transaction_id.currency_id',
        store=True,
        readonly=True
    )
    
    amount_cents = fields.Integer(
        string='Monto en Centavos',
        compute='_compute_amount_cents',
        store=True,
        help='Monto en centavos para enviar a Culqi'
    )
    
    original_amount = fields.Monetary(
        string='Monto Original',
        related='transaction_id.amount',
        readonly=True,
        currency_field='currency_id'
    )
    
    remaining_amount = fields.Monetary(
        string='Monto Disponible para Reembolso',
        compute='_compute_remaining_amount',
        currency_field='currency_id'
    )
    
    # Motivo del reembolso
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
    ], string='Motivo', required=True, tracking=True)
    
    reason_description = fields.Text(
        string='Descripción del Motivo',
        tracking=True,
        help='Descripción detallada del motivo del reembolso'
    )
    
    # Estados
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('succeeded', 'Exitoso'),
        ('failed', 'Fallido'),
        ('canceled', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True)
    
    # Información de procesamiento
    processed_date = fields.Datetime(
        string='Fecha de Procesamiento',
        readonly=True,
        tracking=True
    )
    
    completion_date = fields.Datetime(
        string='Fecha de Finalización',
        readonly=True,
        help='Fecha en que el reembolso fue completado'
    )
    
    expected_completion_date = fields.Date(
        string='Fecha Estimada de Finalización',
        compute='_compute_expected_completion_date',
        help='Fecha estimada cuando el dinero estará disponible en la cuenta del cliente'
    )
    
    # Información adicional
    is_partial = fields.Boolean(
        string='Reembolso Parcial',
        compute='_compute_is_partial',
        store=True
    )
    
    refund_type = fields.Selection([
        ('automatic', 'Automático'),
        ('manual', 'Manual'),
        ('webhook', 'Por Webhook'),
    ], string='Tipo de Reembolso', default='manual')
    
    # Información bancaria (para seguimiento)
    bank_processing_days = fields.Integer(
        string='Días de Procesamiento Bancario',
        default=7,
        help='Días estimados para que el banco procese el reembolso'
    )
    
    # Metadatos de Culqi
    culqi_metadata = fields.Text(
        string='Metadatos Culqi',
        help='Metadatos adicionales almacenados en Culqi (formato JSON)'
    )
    
    culqi_response_data = fields.Text(
        string='Respuesta Completa de Culqi',
        readonly=True,
        help='Respuesta completa de la API de Culqi'
    )
    
    # Fechas de Culqi
    culqi_creation_date = fields.Datetime(
        string='Fecha de Creación en Culqi',
        readonly=True
    )
    
    # Relación con facturas de crédito
    credit_note_id = fields.Many2one(
        'account.move',
        string='Nota de Crédito',
        readonly=True,
        help='Nota de crédito generada para este reembolso'
    )
    
    # Información de error
    error_message = fields.Text(
        string='Mensaje de Error',
        readonly=True,
        help='Mensaje de error si el reembolso falló'
    )
    
    # Campos de seguimiento
    requested_by = fields.Many2one(
        'res.users',
        string='Solicitado Por',
        default=lambda self: self.env.user,
        tracking=True
    )
    
    approved_by = fields.Many2one(
        'res.users',
        string='Aprobado Por',
        tracking=True
    )
    
    approval_date = fields.Datetime(
        string='Fecha de Aprobación',
        tracking=True
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('name', 'amount', 'currency_id', 'state')
    def _compute_display_name(self):
        """Computa el nombre para mostrar."""
        for refund in self:
            if refund.name and refund.amount:
                state_name = dict(refund._fields['state'].selection).get(refund.state, refund.state)
                refund.display_name = f"{refund.name} - {refund.amount:.2f} {refund.currency_id.symbol} ({state_name})"
            elif refund.name:
                refund.display_name = refund.name
            else:
                refund.display_name = 'Reembolso'
    
    @api.depends('amount')
    def _compute_amount_cents(self):
        """Convierte el monto a centavos."""
        for refund in self:
            refund.amount_cents = int(refund.amount * 100) if refund.amount else 0
    
    @api.depends('transaction_id.amount', 'transaction_id.culqi_refunded_amount')
    def _compute_remaining_amount(self):
        """Computa el monto disponible para reembolso."""
        for refund in self:
            if refund.transaction_id:
                refunded_amount = refund.transaction_id.culqi_refunded_amount or 0
                refund.remaining_amount = refund.transaction_id.amount - refunded_amount
            else:
                refund.remaining_amount = 0
    
    @api.depends('amount', 'original_amount')
    def _compute_is_partial(self):
        """Determina si es un reembolso parcial."""
        for refund in self:
            refund.is_partial = refund.amount < refund.original_amount if refund.original_amount else False
    
    @api.depends('processed_date', 'bank_processing_days')
    def _compute_expected_completion_date(self):
        """Calcula la fecha estimada de finalización."""
        for refund in self:
            if refund.processed_date and refund.bank_processing_days:
                completion_date = refund.processed_date + timedelta(days=refund.bank_processing_days)
                refund.expected_completion_date = completion_date.date()
            else:
                refund.expected_completion_date = False

    # ==========================================
    # VALIDACIONES Y CONSTRAINS
    # ==========================================
    
    @api.constrains('amount', 'remaining_amount')
    def _check_refund_amount(self):
        """Valida que el monto del reembolso no exceda el disponible."""
        for refund in self:
            if refund.amount <= 0:
                raise ValidationError(_('El monto del reembolso debe ser mayor a cero.'))
            
            if refund.amount > refund.remaining_amount:
                raise ValidationError(_(
                    'El monto del reembolso (%.2f) no puede ser mayor al monto disponible (%.2f).'
                ) % (refund.amount, refund.remaining_amount))
    
    @api.constrains('transaction_id')
    def _check_transaction_state(self):
        """Valida que la transacción esté en estado válido para reembolso."""
        for refund in self:
            if refund.transaction_id.state not in ['done', 'authorized']:
                raise ValidationError(_(
                    'Solo se pueden reembolsar transacciones completadas o autorizadas.'
                ))
            
            if not refund.transaction_id.culqi_charge_id:
                raise ValidationError(_(
                    'La transacción debe tener un cargo asociado en Culqi para poder reembolsarla.'
                ))

    # ==========================================
    # MÉTODOS ONCHANGE
    # ==========================================
    
    @api.onchange('transaction_id')
    def _onchange_transaction_id(self):
        """Actualiza campos cuando cambia la transacción."""
        if self.transaction_id:
            self.culqi_charge_id = self.transaction_id.culqi_charge_id
            self.amount = self.remaining_amount
            
            # Sugerir motivo basado en el tipo de transacción
            if hasattr(self.transaction_id, 'culqi_subscription_id') and self.transaction_id.culqi_subscription_id:
                self.reason = 'subscription_canceled'
    
    @api.onchange('reason')
    def _onchange_reason(self):
        """Actualiza la descripción basada en el motivo."""
        reason_descriptions = {
            'duplicate': 'El cargo fue duplicado por error',
            'fraudulent': 'El cargo fue identificado como fraudulento',
            'subscription_canceled': 'La suscripción fue cancelada',
            'product_unacceptable': 'El producto o servicio no cumple con las expectativas',
            'product_not_received': 'El cliente no recibió el producto o servicio',
            'unrecognized': 'El cliente no reconoce el cargo',
            'credit_not_processed': 'Un crédito prometido no fue procesado',
            'general': 'Motivo general del comercio',
        }
        
        if self.reason in reason_descriptions:
            self.reason_description = reason_descriptions[self.reason]

    # ==========================================
    # MÉTODOS DE CULQI API
    # ==========================================
    
    def _get_culqi_client(self):
        """Obtiene el cliente Culqi configurado."""
        self.ensure_one()
        return self.transaction_id.provider_id._get_culqi_client()
    
    def _prepare_culqi_refund_data(self):
        """Prepara los datos para enviar a Culqi."""
        self.ensure_one()
        
        refund_data = {
            'amount': self.amount_cents,
            'charge_id': self.culqi_charge_id,
            'reason': self.reason,
        }
        
        # Metadatos
        metadata = {
            'odoo_refund_id': self.id,
            'odoo_refund_number': self.name,
            'odoo_transaction_id': self.transaction_id.id,
            'odoo_partner_id': self.partner_id.id,
            'requested_by': self.requested_by.name,
            'reason_description': self.reason_description or '',
            'created_from': 'odoo',
        }
        
        # Agregar metadatos personalizados si existen
        if self.culqi_metadata:
            try:
                custom_metadata = json.loads(self.culqi_metadata)
                metadata.update(custom_metadata)
            except json.JSONDecodeError:
                _logger.warning('Metadatos JSON inválidos para reembolso %s', self.id)
        
        refund_data['metadata'] = metadata
        
        return refund_data
    
    def create_in_culqi(self):
        """Crea el reembolso en Culqi."""
        self.ensure_one()
        
        if self.culqi_refund_id:
            raise UserError(_('El reembolso ya está creado en Culqi: %s') % self.culqi_refund_id)
        
        if self.state != 'draft':
            raise UserError(_('Solo se pueden procesar reembolsos en estado borrador.'))
        
        try:
            client = self._get_culqi_client()
            refund_data = self._prepare_culqi_refund_data()
            
            _logger.info('Creando reembolso en Culqi para cargo: %s', self.culqi_charge_id)
            
            self.state = 'pending'
            
            response = client.refund.create(data=refund_data)
            
            if response.get('object') == 'refund':
                self._process_culqi_response(response)
                
                self.message_post(
                    body=_('Reembolso creado exitosamente en Culqi: %s') % response['id']
                )
                
                _logger.info('Reembolso creado en Culqi: %s', response['id'])
                return response
            else:
                self.state = 'failed'
                error_msg = response.get('user_message', 'Error desconocido')
                self.error_message = error_msg
                raise UserError(_('Error al crear reembolso: %s') % error_msg)
                
        except Exception as e:
            _logger.error('Error al crear reembolso en Culqi: %s', str(e))
            self.state = 'failed'
            self.error_message = str(e)
            
            self.message_post(
                body=_('Error al crear reembolso en Culqi: %s') % str(e)
            )
            raise UserError(_('Error al crear reembolso en Culqi: %s') % str(e))
    
    def retrieve_from_culqi(self):
        """Obtiene la información del reembolso desde Culqi."""
        self.ensure_one()
        
        if not self.culqi_refund_id:
            raise UserError(_('No hay ID de reembolso en Culqi para sincronizar.'))
        
        try:
            client = self._get_culqi_client()
            
            _logger.info('Obteniendo reembolso desde Culqi: %s', self.culqi_refund_id)
            
            response = client.refund.read(self.culqi_refund_id)
            
            if response.get('object') == 'refund':
                self._process_culqi_response(response)
                
                self.message_post(
                    body=_('Reembolso sincronizado exitosamente desde Culqi')
                )
                
                _logger.info('Reembolso sincronizado desde Culqi: %s', self.culqi_refund_id)
                return response
            else:
                raise UserError(_('Error al obtener reembolso: %s') % response.get('user_message', 'Reembolso no encontrado'))
                
        except Exception as e:
            _logger.error('Error al obtener reembolso desde Culqi: %s', str(e))
            self.message_post(
                body=_('Error al sincronizar reembolso desde Culqi: %s') % str(e)
            )
            raise UserError(_('Error al sincronizar reembolso desde Culqi: %s') % str(e))
    
    def _process_culqi_response(self, response):
        """Procesa la respuesta de Culqi y actualiza los campos."""
        self.ensure_one()
        
        # Actualizar ID si es necesario
        if response.get('id') and not self.culqi_refund_id:
            self.culqi_refund_id = response['id']
        
        # Mapear estados de Culqi a estados de Odoo
        culqi_state = response.get('status', 'pending')
        state_mapping = {
            'pending': 'pending',
            'processing': 'processing',
            'succeeded': 'succeeded',
            'failed': 'failed',
            'canceled': 'canceled',
        }
        
        new_state = state_mapping.get(culqi_state, 'pending')
        if new_state != self.state:
            self.state = new_state
            
            # Actualizar fechas según el estado
            if new_state == 'processing' and not self.processed_date:
                self.processed_date = fields.Datetime.now()
            elif new_state == 'succeeded' and not self.completion_date:
                self.completion_date = fields.Datetime.now()
        
        # Actualizar fechas de Culqi
        if response.get('creation_date'):
            try:
                creation_timestamp = response['creation_date']
                self.culqi_creation_date = datetime.fromtimestamp(creation_timestamp)
            except (ValueError, TypeError):
                _logger.warning('Fecha de creación inválida recibida de Culqi: %s', response.get('creation_date'))
        
        # Guardar respuesta completa
        self.culqi_response_data = json.dumps(response, indent=2)
        
        # Actualizar metadatos si vienen en la respuesta
        if response.get('metadata'):
            self.culqi_metadata = json.dumps(response['metadata'], indent=2)
        
        # Actualizar transacción padre si el reembolso fue exitoso
        if new_state == 'succeeded':
            self._update_parent_transaction()

    def _update_parent_transaction(self):
        """Actualiza la transacción padre cuando el reembolso es exitoso."""
        self.ensure_one()
        
        if self.transaction_id:
            # Actualizar monto reembolsado
            current_refunded = self.transaction_id.culqi_refunded_amount or 0
            self.transaction_id.culqi_refunded_amount = current_refunded + self.amount
            
            # Crear nota de crédito si está configurado
            if self.transaction_id.invoice_ids and not self.credit_note_id:
                self._create_credit_note()

    # ==========================================
    # MÉTODOS DE CONTABILIDAD
    # ==========================================
    
    def _create_credit_note(self):
        """Crea una nota de crédito para el reembolso."""
        self.ensure_one()
        
        # Buscar la primera factura relacionada
        invoice = self.transaction_id.invoice_ids.filtered(lambda inv: inv.move_type == 'out_invoice')[:1]
        
        if not invoice:
            return False
        
        # Crear nota de crédito
        credit_note_vals = {
            'move_type': 'out_refund',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'payment_reference': self.name,
            'ref': f'Reembolso {self.name}',
            'invoice_origin': invoice.name,
            'reversed_entry_id': invoice.id,
        }
        
        # Calcular líneas proporcionales si es reembolso parcial
        invoice_lines = []
        for line in invoice.invoice_line_ids.filtered(lambda l: not l.display_type):
            if self.is_partial:
                # Calcular proporción del reembolso
                proportion = self.amount / self.original_amount
                refund_quantity = line.quantity * proportion
                refund_price = line.price_unit
            else:
                # Reembolso total
                refund_quantity = line.quantity
                refund_price = line.price_unit
            
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': f'Reembolso: {line.name}',
                'quantity': refund_quantity,
                'price_unit': refund_price,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
                'account_id': line.account_id.id,
            }))
        
        credit_note_vals['invoice_line_ids'] = invoice_lines
        
        credit_note = self.env['account.move'].create(credit_note_vals)
        credit_note.action_post()
        
        self.credit_note_id = credit_note
        
        return credit_note

    # ==========================================
    # MÉTODOS DE ACCIÓN
    # ==========================================
    
    def action_submit_for_approval(self):
        """Envía el reembolso para aprobación."""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_('Solo se pueden enviar reembolsos en borrador para aprobación.'))
        
        # TODO: Implementar workflow de aprobación si es necesario
        # Por ahora, procesar directamente
        return self.action_process_refund()
    
    def action_approve(self):
        """Aprueba el reembolso."""
        self.ensure_one()
        
        self.approved_by = self.env.user
        self.approval_date = fields.Datetime.now()
        
        self.message_post(
            body=_('Reembolso aprobado por %s') % self.env.user.name
        )
        
        return self.action_process_refund()
    
    def action_process_refund(self):
        """Procesa el reembolso en Culqi."""
        self.create_in_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reembolso Procesado'),
                'message': _('El reembolso ha sido enviado a Culqi para procesamiento.'),
                'type': 'success',
            }
        }
    
    def action_sync_from_culqi(self):
        """Sincroniza el reembolso desde Culqi."""
        self.retrieve_from_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reembolso Sincronizado'),
                'message': _('El reembolso ha sido sincronizado exitosamente desde Culqi.'),
                'type': 'success',
            }
        }
    
    def action_cancel(self):
        """Cancela el reembolso."""
        self.ensure_one()
        
        if self.state not in ['draft', 'pending']:
            raise UserError(_('Solo se pueden cancelar reembolsos en borrador o pendientes.'))
        
        self.state = 'canceled'
        
        self.message_post(
            body=_('Reembolso cancelado por %s') % self.env.user.name
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reembolso Cancelado'),
                'message': _('El reembolso ha sido cancelado.'),
                'type': 'info',
            }
        }
    
    def action_view_transaction(self):
        """Acción para ver la transacción original."""
        self.ensure_one()
        return {
            'name': _('Transacción Original'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'res_id': self.transaction_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_credit_note(self):
        """Acción para ver la nota de crédito."""
        self.ensure_one()
        if not self.credit_note_id:
            raise UserError(_('No hay nota de crédito asociada a este reembolso.'))
        
        return {
            'name': _('Nota de Crédito'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.credit_note_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==========================================
    # MÉTODOS DE MODELO
    # ==========================================
    
    @api.model
    def create(self, vals):
        """Override create para configuración inicial."""
        # Generar nombre si no existe
        if not vals.get('name') or vals.get('name') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('culqi.refund') or '/'
        
        refund = super().create(vals)
        
        # Enviar notificación al cliente si está configurado
        if refund.partner_id.email:
            refund._send_refund_notification()
        
        return refund
    
    def _send_refund_notification(self):
        """Envía notificación por email al cliente sobre el reembolso."""
        self.ensure_one()
        
        template = self.env.ref('payment_culqi.refund_notification_email_template', raise_if_not_found=False)
        if template and self.partner_id.email:
            template.send_mail(self.id, force_send=True)
    
    @api.model
    def handle_culqi_webhook_refund(self, webhook_data):
        """Maneja webhooks de reembolso desde Culqi."""
        refund_data = webhook_data.get('data', {})
        refund_id = refund_data.get('id')
        
        if not refund_id:
            _logger.warning('Webhook de reembolso sin ID: %s', webhook_data)
            return False
        
        # Buscar el reembolso por ID de Culqi
        refund = self.search([('culqi_refund_id', '=', refund_id)], limit=1)
        
        if refund:
            refund._process_culqi_response(refund_data)
            _logger.info('Reembolso %s actualizado vía webhook', refund_id)
        else:
            # Si no existe, crear uno nuevo (caso de reembolso creado externamente)
            charge_id = refund_data.get('charge_id')
            if charge_id:
                transaction = self.env['payment.transaction'].search([
                    ('culqi_charge_id', '=', charge_id)
                ], limit=1)
                
                if transaction:
                    refund_vals = {
                        'culqi_refund_id': refund_id,
                        'transaction_id': transaction.id,
                        'amount': refund_data.get('amount', 0) / 100.0,  # Convertir de centavos
                        'reason': refund_data.get('reason', 'other'),
                        'refund_type': 'webhook',
                        'state': 'pending',
                    }
                    
                    refund = self.create(refund_vals)
                    refund._process_culqi_response(refund_data)
                    
                    _logger.info('Reembolso %s creado vía webhook', refund_id)
        
        return refund
    
    @api.model
    def cleanup_failed_refunds(self):
        """Limpia reembolsos fallidos antiguos."""
        cutoff_date = fields.Datetime.now() - timedelta(days=30)
        
        failed_refunds = self.search([
            ('state', '=', 'failed'),
            ('create_date', '<', cutoff_date),
        ])
        
        for refund in failed_refunds:
            refund.message_post(
                body=_('Reembolso fallido archivado automáticamente después de 30 días')
            )
            refund.active = False
        
        _logger.info('Archivados %d reembolsos fallidos', len(failed_refunds))
        return len(failed_refunds)
    
    @api.model
    def get_refund_stats(self):
        """Obtiene estadísticas de reembolsos para dashboard."""
        stats = {}
        
        # Contadores por estado
        for state in self._fields['state'].selection:
            state_code = state[0]
            stats[f'{state_code}_count'] = self.search_count([('state', '=', state_code)])
        
        # Montos totales
        today = fields.Date.today()
        this_month_start = today.replace(day=1)
        
        # Reembolsos del mes actual
        monthly_refunds = self.search([
            ('create_date', '>=', this_month_start),
            ('state', '=', 'succeeded')
        ])
        stats['monthly_refund_amount'] = sum(monthly_refunds.mapped('amount'))
        stats['monthly_refund_count'] = len(monthly_refunds)
        
        # Reembolsos pendientes
        pending_refunds = self.search([('state', 'in', ['pending', 'processing'])])
        stats['pending_refund_amount'] = sum(pending_refunds.mapped('amount'))
        
        # Promedio de tiempo de procesamiento (en días)
        completed_refunds = self.search([
            ('state', '=', 'succeeded'),
            ('processed_date', '!=', False),
            ('completion_date', '!=', False)
        ])
        
        if completed_refunds:
            total_processing_time = sum([
                (refund.completion_date - refund.processed_date).days
                for refund in completed_refunds
                if refund.completion_date and refund.processed_date
            ])
            stats['avg_processing_days'] = total_processing_time / len(completed_refunds)
        else:
            stats['avg_processing_days'] = 0
        
        # Motivos más comunes
        reason_stats = {}
        for reason in self._fields['reason'].selection:
            reason_code = reason[0]
            count = self.search_count([('reason', '=', reason_code)])
            if count > 0:
                reason_stats[reason_code] = count
        
        stats['refund_reasons'] = reason_stats
        
        return stats
    
    @api.model
    def process_pending_refunds(self):
        """Procesa reembolsos pendientes automáticamente."""
        pending_refunds = self.search([
            ('state', '=', 'draft'),
            ('create_date', '<', fields.Datetime.now() - timedelta(hours=1))  # Esperar 1 hora antes de procesar automáticamente
        ])
        
        processed_count = 0
        failed_count = 0
        
        for refund in pending_refunds:
            try:
                refund.create_in_culqi()
                processed_count += 1
            except Exception as e:
                _logger.error('Error al procesar reembolso automático %s: %s', refund.id, str(e))
                failed_count += 1
        
        _logger.info('Procesamiento automático completado: %d exitosos, %d fallidos', processed_count, failed_count)
        
        return {
            'processed': processed_count,
            'failed': failed_count
        }


class PaymentTransaction(models.Model):
    """Extensión del modelo payment.transaction para reembolsos."""
    _inherit = 'payment.transaction'
    
    # Relación con reembolsos
    refund_ids = fields.One2many(
        'culqi.refund',
        'transaction_id',
        string='Reembolsos',
        help='Reembolsos asociados a esta transacción'
    )
    
    refund_count = fields.Integer(
        string='Número de Reembolsos',
        compute='_compute_refund_count'
    )
    
    can_be_refunded = fields.Boolean(
        string='Puede ser Reembolsada',
        compute='_compute_can_be_refunded'
    )
    
    @api.depends('refund_ids')
    def _compute_refund_count(self):
        """Computa el número de reembolsos."""
        for tx in self:
            tx.refund_count = len(tx.refund_ids)
    
    @api.depends('state', 'culqi_charge_id', 'amount', 'culqi_refunded_amount')
    def _compute_can_be_refunded(self):
        """Determina si la transacción puede ser reembolsada."""
        for tx in self:
            tx.can_be_refunded = (
                tx.state in ['done', 'authorized'] and
                tx.culqi_charge_id and
                tx.amount > (tx.culqi_refunded_amount or 0)
            )
    
    def action_create_refund(self, amount=None, reason=None):
        """Acción mejorada para crear reembolso."""
        self.ensure_one()
        
        if not self.can_be_refunded:
            raise UserError(_('Esta transacción no puede ser reembolsada.'))
        
        # Si no se especifica monto, usar el monto disponible
        if amount is None:
            amount = self.amount - (self.culqi_refunded_amount or 0)
        
        # Crear el reembolso
        refund_vals = {
            'transaction_id': self.id,
            'amount': amount,
            'reason': reason or 'general',
            'reason_description': f'Reembolso solicitado para transacción {self.reference}',
        }
        
        refund = self.env['culqi.refund'].create(refund_vals)
        
        # Abrir el formulario del reembolso
        return {
            'name': _('Nuevo Reembolso'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.refund',
            'res_id': refund.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_refunds(self):
        """Acción para ver los reembolsos de la transacción."""
        self.ensure_one()
        return {
            'name': _('Reembolsos de %s') % self.reference,
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.refund',
            'view_mode': 'tree,form',
            'domain': [('transaction_id', '=', self.id)],
            'context': {'default_transaction_id': self.id},
        }


class AccountMove(models.Model):
    """Extensión del modelo account.move para reembolsos."""
    _inherit = 'account.move'
    
    # Relación con suscripciones y reembolsos
    culqi_subscription_id = fields.Many2one(
        'culqi.subscription',
        string='Suscripción Culqi',
        help='Suscripción que generó esta factura'
    )
    
    culqi_refund_ids = fields.One2many(
        'culqi.refund',
        'credit_note_id',
        string='Reembolsos Culqi',
        help='Reembolsos asociados a esta nota de crédito'
    )
    
    def action_create_culqi_refund(self):
        """Crea un reembolso Culqi desde una factura."""
        self.ensure_one()
        
        if self.move_type != 'out_invoice':
            raise UserError(_('Solo se pueden reembolsar facturas de cliente.'))
        
        if self.payment_state != 'paid':
            raise UserError(_('Solo se pueden reembolsar facturas pagadas.'))
        
        # Buscar la transacción de pago relacionada
        payment_tx = self.env['payment.transaction'].search([
            ('invoice_ids', 'in', self.ids),
            ('state', '=', 'done'),
            ('provider_code', '=', 'culqi')
        ], limit=1)
        
        if not payment_tx:
            raise UserError(_('No se encontró una transacción de pago Culqi para esta factura.'))
        
        # Abrir wizard para crear reembolso
        return {
            'name': _('Crear Reembolso Culqi'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.refund.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': payment_tx.id,
                'default_invoice_id': self.id,
            },
        }