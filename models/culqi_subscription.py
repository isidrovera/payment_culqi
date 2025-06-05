# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CulqiSubscription(models.Model):
    _name = 'culqi.subscription'
    _description = 'Suscripción Culqi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    name = fields.Char(
        string='Nombre de Suscripción',
        compute='_compute_name',
        store=True,
        tracking=True
    )
    
    display_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_display_name',
        store=True
    )
    
    # Identificadores
    culqi_subscription_id = fields.Char(
        string='ID de Suscripción Culqi',
        readonly=True,
        tracking=True,
        help='ID único de la suscripción en Culqi'
    )
    
    reference = fields.Char(
        string='Referencia',
        required=True,
        copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('culqi.subscription') or '/',
        tracking=True
    )
    
    # Relaciones principales
    customer_id = fields.Many2one(
        'culqi.customer',
        string='Cliente',
        required=True,
        ondelete='cascade',
        tracking=True
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto',
        related='customer_id.partner_id',
        store=True,
        readonly=True
    )
    
    plan_id = fields.Many2one(
        'culqi.plan',
        string='Plan',
        required=True,
        tracking=True
    )
    
    card_id = fields.Many2one(
        'culqi.card',
        string='Tarjeta',
        required=True,
        domain="[('customer_id', '=', customer_id), ('state', '=', 'active')]",
        tracking=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='customer_id.company_id',
        store=True,
        readonly=True
    )
    
    provider_id = fields.Many2one(
        'payment.provider',
        string='Proveedor de Pago',
        related='customer_id.provider_id',
        store=True,
        readonly=True
    )
    
    # Estados
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('trial', 'Periodo de Prueba'),
        ('active', 'Activa'),
        ('past_due', 'Vencida'),
        ('cancelled', 'Cancelada'),
        ('unpaid', 'Impaga'),
        ('expired', 'Expirada'),
    ], string='Estado', default='draft', tracking=True)
    
    # Fechas importantes
    start_date = fields.Date(
        string='Fecha de Inicio',
        default=fields.Date.today,
        required=True,
        tracking=True
    )
    
    trial_end_date = fields.Date(
        string='Fin del Periodo de Prueba',
        compute='_compute_trial_end_date',
        store=True
    )
    
    current_period_start = fields.Date(
        string='Inicio del Periodo Actual',
        tracking=True
    )
    
    current_period_end = fields.Date(
        string='Fin del Periodo Actual',
        tracking=True
    )
    
    next_billing_date = fields.Date(
        string='Próxima Fecha de Facturación',
        compute='_compute_next_billing_date',
        store=True,
        tracking=True
    )
    
    cancelled_date = fields.Date(
        string='Fecha de Cancelación',
        readonly=True,
        tracking=True
    )
    
    # Información de facturación
    amount = fields.Monetary(
        string='Monto',
        related='plan_id.amount',
        store=True,
        readonly=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='plan_id.currency_id',
        store=True,
        readonly=True
    )
    
    # Configuración de la suscripción
    quantity = fields.Integer(
        string='Cantidad',
        default=1,
        tracking=True,
        help='Múltiplo del plan (ej: 3 usuarios)'
    )
    
    total_amount = fields.Monetary(
        string='Monto Total',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id'
    )
    
    # Información de trial
    in_trial = fields.Boolean(
        string='En Periodo de Prueba',
        compute='_compute_trial_status',
        store=True
    )
    
    trial_days_remaining = fields.Integer(
        string='Días de Prueba Restantes',
        compute='_compute_trial_status'
    )
    
    # Contadores y estadísticas
    billing_cycle_count = fields.Integer(
        string='Ciclos de Facturación',
        default=0,
        readonly=True,
        help='Número de veces que se ha facturado'
    )
    
    successful_charges = fields.Integer(
        string='Cargos Exitosos',
        default=0,
        readonly=True
    )
    
    failed_charges = fields.Integer(
        string='Cargos Fallidos',
        default=0,
        readonly=True
    )
    
    total_paid = fields.Monetary(
        string='Total Pagado',
        default=0.0,
        readonly=True,
        currency_field='currency_id'
    )
    
    # Configuración de cancelación
    cancel_at_period_end = fields.Boolean(
        string='Cancelar al Final del Periodo',
        default=False,
        tracking=True,
        help='La suscripción se cancelará automáticamente al final del periodo actual'
    )
    
    cancellation_reason = fields.Text(
        string='Razón de Cancelación',
        tracking=True
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
    
    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True
    )
    
    # Relaciones
    transaction_ids = fields.One2many(
        'payment.transaction',
        compute='_compute_transactions',
        string='Transacciones',
        help='Transacciones relacionadas con esta suscripción'
    )
    
    invoice_ids = fields.One2many(
        'account.move',
        'culqi_subscription_id',
        string='Facturas',
        help='Facturas generadas por esta suscripción'
    )
    
    # Campos computados adicionales
    transaction_count = fields.Integer(
        string='Número de Transacciones',
        compute='_compute_counts'
    )
    
    invoice_count = fields.Integer(
        string='Número de Facturas',
        compute='_compute_counts'
    )
    
    days_until_next_billing = fields.Integer(
        string='Días hasta Próxima Facturación',
        compute='_compute_billing_info'
    )
    
    is_overdue = fields.Boolean(
        string='Vencida',
        compute='_compute_billing_info'
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('customer_id', 'plan_id', 'reference')
    def _compute_name(self):
        """Computa el nombre de la suscripción."""
        for subscription in self:
            if subscription.customer_id and subscription.plan_id:
                subscription.name = f"{subscription.customer_id.display_name} - {subscription.plan_id.name}"
            elif subscription.reference and subscription.reference != '/':
                subscription.name = subscription.reference
            else:
                subscription.name = 'Nueva Suscripción'
    
    @api.depends('name', 'state', 'total_amount', 'currency_id')
    def _compute_display_name(self):
        """Computa el nombre para mostrar."""
        for subscription in self:
            if subscription.name and subscription.total_amount:
                state_name = dict(subscription._fields['state'].selection).get(subscription.state, subscription.state)
                subscription.display_name = f"{subscription.name} - {subscription.total_amount:.2f} {subscription.currency_id.symbol} ({state_name})"
            elif subscription.name:
                subscription.display_name = subscription.name
            else:
                subscription.display_name = 'Suscripción'
    
    @api.depends('start_date', 'plan_id')
    def _compute_trial_end_date(self):
        """Computa la fecha de fin del periodo de prueba."""
        for subscription in self:
            if subscription.start_date and subscription.plan_id and subscription.plan_id.trial_period_days > 0:
                subscription.trial_end_date = subscription.start_date + timedelta(days=subscription.plan_id.trial_period_days)
            else:
                subscription.trial_end_date = False
    
    @api.depends('trial_end_date')
    def _compute_trial_status(self):
        """Computa el estado del periodo de prueba."""
        today = fields.Date.today()
        for subscription in self:
            if subscription.trial_end_date:
                subscription.in_trial = subscription.trial_end_date >= today
                if subscription.in_trial:
                    subscription.trial_days_remaining = (subscription.trial_end_date - today).days
                else:
                    subscription.trial_days_remaining = 0
            else:
                subscription.in_trial = False
                subscription.trial_days_remaining = 0
    
    @api.depends('current_period_end', 'plan_id', 'start_date', 'trial_end_date')
    def _compute_next_billing_date(self):
        """Computa la próxima fecha de facturación."""
        for subscription in self:
            if subscription.state in ['cancelled', 'expired']:
                subscription.next_billing_date = False
            elif subscription.in_trial and subscription.trial_end_date:
                subscription.next_billing_date = subscription.trial_end_date
            elif subscription.current_period_end:
                subscription.next_billing_date = subscription.current_period_end
            elif subscription.plan_id and subscription.start_date:
                # Calcular primera fecha de facturación
                if subscription.trial_end_date:
                    start_date = subscription.trial_end_date
                else:
                    start_date = subscription.start_date
                subscription.next_billing_date = subscription.plan_id.get_next_billing_date(start_date)
            else:
                subscription.next_billing_date = False
    
    @api.depends('amount', 'quantity')
    def _compute_total_amount(self):
        """Computa el monto total basado en cantidad."""
        for subscription in self:
            subscription.total_amount = subscription.amount * subscription.quantity
    
    @api.depends('next_billing_date')
    def _compute_billing_info(self):
        """Computa información de facturación."""
        today = fields.Date.today()
        for subscription in self:
            if subscription.next_billing_date:
                days_diff = (subscription.next_billing_date - today).days
                subscription.days_until_next_billing = days_diff
                subscription.is_overdue = days_diff < 0
            else:
                subscription.days_until_next_billing = 0
                subscription.is_overdue = False
    
    def _compute_transactions(self):
        """Computa las transacciones relacionadas."""
        for subscription in self:
            # Buscar transacciones que tengan metadatos con este subscription_id
            transactions = self.env['payment.transaction'].search([
                ('culqi_metadata', 'ilike', f'"subscription_id": {subscription.id}')
            ])
            subscription.transaction_ids = transactions
    
    @api.depends('transaction_ids', 'invoice_ids')
    def _compute_counts(self):
        """Computa los contadores."""
        for subscription in self:
            subscription.transaction_count = len(subscription.transaction_ids)
            subscription.invoice_count = len(subscription.invoice_ids)

    # ==========================================
    # VALIDACIONES Y CONSTRAINS
    # ==========================================
    
    @api.constrains('start_date')
    def _check_start_date(self):
        """Valida la fecha de inicio."""
        for subscription in self:
            if subscription.start_date and subscription.start_date < fields.Date.today():
                if subscription.state == 'draft':
                    raise ValidationError(_('La fecha de inicio no puede ser anterior a hoy para una nueva suscripción.'))
    
    @api.constrains('quantity')
    def _check_quantity(self):
        """Valida la cantidad."""
        for subscription in self:
            if subscription.quantity <= 0:
                raise ValidationError(_('La cantidad debe ser mayor a cero.'))
    
    @api.constrains('customer_id', 'card_id')
    def _check_card_customer(self):
        """Valida que la tarjeta pertenezca al cliente."""
        for subscription in self:
            if subscription.card_id and subscription.card_id.customer_id != subscription.customer_id:
                raise ValidationError(_('La tarjeta seleccionada no pertenece al cliente.'))

    # ==========================================
    # MÉTODOS ONCHANGE
    # ==========================================
    
    @api.onchange('customer_id')
    def _onchange_customer_id(self):
        """Actualiza el dominio de tarjetas cuando cambia el cliente."""
        if self.customer_id:
            return {
                'domain': {
                    'card_id': [('customer_id', '=', self.customer_id.id), ('state', '=', 'active')]
                }
            }
        else:
            return {
                'domain': {
                    'card_id': [('id', '=', False)]
                }
            }
    
    @api.onchange('plan_id')
    def _onchange_plan_id(self):
        """Actualiza campos cuando cambia el plan."""
        if self.plan_id:
            # Si es una nueva suscripción, calcular fechas
            if self.state == 'draft' and self.start_date:
                self._compute_trial_end_date()
                self._compute_next_billing_date()

    # ==========================================
    # MÉTODOS DE CULQI API
    # ==========================================
    
    def _get_culqi_client(self):
        """Obtiene el cliente Culqi configurado."""
        self.ensure_one()
        return self.customer_id._get_culqi_client()
    
    def _prepare_culqi_subscription_data(self):
        """Prepara los datos para enviar a Culqi."""
        self.ensure_one()
        
        subscription_data = {
            'card_id': self.card_id.culqi_card_id,
            'plan_id': self.plan_id.culqi_plan_id,
        }
        
        # Agregar cantidad si es diferente de 1
        if self.quantity > 1:
            subscription_data['quantity'] = self.quantity
        
        # Metadatos
        metadata = {
            'odoo_subscription_id': self.id,
            'odoo_reference': self.reference,
            'odoo_customer_id': self.customer_id.id,
            'odoo_partner_id': self.partner_id.id,
            'created_from': 'odoo',
        }
        
        # Agregar metadatos personalizados si existen
        if self.culqi_metadata:
            try:
                custom_metadata = json.loads(self.culqi_metadata)
                metadata.update(custom_metadata)
            except json.JSONDecodeError:
                _logger.warning('Metadatos JSON inválidos para suscripción %s', self.id)
        
        subscription_data['metadata'] = metadata
        
        return subscription_data
    
    def create_in_culqi(self):
        """Crea la suscripción en Culqi."""
        self.ensure_one()
        
        if self.culqi_subscription_id:
            raise UserError(_('La suscripción ya está creada en Culqi: %s') % self.culqi_subscription_id)
        
        # Validar requisitos
        if not self.customer_id.culqi_customer_id:
            raise UserError(_('El cliente debe estar creado en Culqi primero.'))
        
        if not self.plan_id.culqi_plan_id:
            raise UserError(_('El plan debe estar creado en Culqi primero.'))
        
        if not self.card_id.culqi_card_id:
            raise UserError(_('La tarjeta debe estar creada en Culqi primero.'))
        
        try:
            client = self._get_culqi_client()
            subscription_data = self._prepare_culqi_subscription_data()
            
            _logger.info('Creando suscripción en Culqi para cliente: %s', self.customer_id.culqi_customer_id)
            
            response = client.subscription.create(data=subscription_data)
            
            if response.get('object') == 'subscription':
                self._process_culqi_response(response)
                self._update_subscription_state()
                
                self.message_post(
                    body=_('Suscripción creada exitosamente en Culqi: %s') % response['id']
                )
                
                _logger.info('Suscripción creada en Culqi: %s', response['id'])
                return response
            else:
                raise UserError(_('Error al crear suscripción: %s') % response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al crear suscripción en Culqi: %s', str(e))
            self.message_post(
                body=_('Error al crear suscripción en Culqi: %s') % str(e)
            )
            raise UserError(_('Error al crear suscripción en Culqi: %s') % str(e))
    
    def retrieve_from_culqi(self):
        """Obtiene la información de la suscripción desde Culqi."""
        self.ensure_one()
        
        if not self.culqi_subscription_id:
            raise UserError(_('No hay ID de suscripción en Culqi para sincronizar.'))
        
        try:
            client = self._get_culqi_client()
            
            _logger.info('Obteniendo suscripción desde Culqi: %s', self.culqi_subscription_id)
            
            response = client.subscription.read(self.culqi_subscription_id)
            
            if response.get('object') == 'subscription':
                self._process_culqi_response(response)
                self._update_subscription_state()
                self.last_sync_date = fields.Datetime.now()
                
                self.message_post(
                    body=_('Suscripción sincronizada exitosamente desde Culqi')
                )
                
                _logger.info('Suscripción sincronizada desde Culqi: %s', self.culqi_subscription_id)
                return response
            else:
                raise UserError(_('Error al obtener suscripción: %s') % response.get('user_message', 'Suscripción no encontrada'))
                
        except Exception as e:
            _logger.error('Error al obtener suscripción desde Culqi: %s', str(e))
            self.message_post(
                body=_('Error al sincronizar suscripción desde Culqi: %s') % str(e)
            )
            raise UserError(_('Error al sincronizar suscripción desde Culqi: %s') % str(e))
    
    def cancel_in_culqi(self):
        """Cancela la suscripción en Culqi."""
        self.ensure_one()
        
        if not self.culqi_subscription_id:
            raise UserError(_('La suscripción no está creada en Culqi.'))
        
        if self.state in ['cancelled', 'expired']:
            raise UserError(_('La suscripción ya está cancelada o expirada.'))
        
        try:
            client = self._get_culqi_client()
            
            _logger.info('Cancelando suscripción en Culqi: %s', self.culqi_subscription_id)
            
            response = client.subscription.delete(self.culqi_subscription_id)
            
            if response.get('deleted'):
                self.state = 'cancelled'
                self.cancelled_date = fields.Date.today()
                
                self.message_post(
                    body=_('Suscripción cancelada exitosamente en Culqi')
                )
                
                _logger.info('Suscripción cancelada en Culqi: %s', self.culqi_subscription_id)
                return response
            else:
                raise UserError(_('Error al cancelar suscripción: %s') % response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al cancelar suscripción en Culqi: %s', str(e))
            self.message_post(
                body=_('Error al cancelar suscripción en Culqi: %s') % str(e)
            )
            raise UserError(_('Error al cancelar suscripción en Culqi: %s') % str(e))
    
    def _process_culqi_response(self, response):
        """Procesa la respuesta de Culqi y actualiza los campos."""
        self.ensure_one()
        
        # Actualizar ID si es necesario
        if response.get('id') and not self.culqi_subscription_id:
            self.culqi_subscription_id = response['id']
        
        # Actualizar periodos de facturación
        if response.get('current_period_start'):
            try:
                self.current_period_start = datetime.fromtimestamp(response['current_period_start']).date()
            except (ValueError, TypeError):
                pass
        
        if response.get('current_period_end'):
            try:
                self.current_period_end = datetime.fromtimestamp(response['current_period_end']).date()
            except (ValueError, TypeError):
                pass
        
        # Actualizar contadores si están disponibles
        if 'billing_cycle_count' in response:
            self.billing_cycle_count = response['billing_cycle_count']
        
        # Actualizar fechas
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
    
    def _update_subscription_state(self):
        """Actualiza el estado de la suscripción basado en las fechas."""
        self.ensure_one()
        
        today = fields.Date.today()
        
        if self.state == 'cancelled':
            return
        
        # Si está en periodo de prueba
        if self.in_trial:
            self.state = 'trial'
        # Si ya pasó el periodo de prueba o no tiene periodo de prueba
        else:
            self.state = 'active'

    # ==========================================
    # MÉTODOS DE FACTURACIÓN
    # ==========================================
    
    def process_billing_cycle(self):
        """Procesa un ciclo de facturación."""
        self.ensure_one()
        
        if self.state not in ['active', 'trial', 'past_due']:
            return False
        
        try:
            # Crear transacción de pago para la suscripción
            transaction_vals = {
                'reference': f"{self.reference}-{self.billing_cycle_count + 1}",
                'amount': self.total_amount,
                'currency_id': self.currency_id.id,
                'partner_id': self.partner_id.id,
                'provider_id': self.provider_id.id,
                'culqi_customer_id': self.customer_id.id,
                'culqi_card_id': self.card_id.id,
                'culqi_metadata': json.dumps({
                    'subscription_id': self.id,
                    'billing_cycle': self.billing_cycle_count + 1,
                    'plan_id': self.plan_id.id,
                }),
            }
            
            transaction = self.env['payment.transaction'].create(transaction_vals)
            
            # Procesar el pago usando la tarjeta guardada
            charge_response = transaction._create_culqi_charge(
                source_id=self.card_id.culqi_card_id
            )
            
            if charge_response and transaction.state == 'done':
                # Pago exitoso
                self.successful_charges += 1
                self.total_paid += self.total_amount
                self.billing_cycle_count += 1
                
                # Actualizar periodo de facturación
                self._update_billing_period()
                
                # Crear factura si es necesario
                self._create_subscription_invoice(transaction)
                
                self.message_post(
                    body=_('Ciclo de facturación procesado exitosamente. Monto: %s %s') % (
                        self.total_amount, self.currency_id.symbol
                    )
                )
                
                return True
            else:
                # Pago fallido
                self.failed_charges += 1
                self.state = 'past_due'
                
                self.message_post(
                    body=_('Fallo en el ciclo de facturación. La suscripción está vencida.')
                )
                
                return False
                
        except Exception as e:
            _logger.error('Error al procesar ciclo de facturación para suscripción %s: %s', self.id, str(e))
            self.failed_charges += 1
            self.state = 'past_due'
            
            self.message_post(
                body=_('Error al procesar ciclo de facturación: %s') % str(e)
            )
            
            return False
    
    def _update_billing_period(self):
        """Actualiza el periodo de facturación."""
        self.ensure_one()
        
        if not self.current_period_end:
            # Primera facturación
            if self.trial_end_date and self.trial_end_date >= fields.Date.today():
                start_date = self.trial_end_date
            else:
                start_date = self.start_date
        else:
            start_date = self.current_period_end
        
        self.current_period_start = start_date
        self.current_period_end = self.plan_id.get_next_billing_date(start_date)
    
    def _create_subscription_invoice(self, transaction):
        """Crea una factura para el ciclo de facturación."""
        self.ensure_one()
        
        # Solo crear factura si hay un producto asociado al plan
        if not self.plan_id.product_id:
            return False
        
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'payment_reference': transaction.reference,
            'culqi_subscription_id': self.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.plan_id.product_id.id,
                'quantity': self.quantity,
                'price_unit': self.plan_id.amount,
                'name': f"{self.plan_id.name} - Periodo {self.current_period_start} a {self.current_period_end}",
            })],
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        invoice.action_post()
        
        # Vincular el pago con la factura
        if transaction.payment_id:
            invoice.js_assign_outstanding_line(transaction.payment_id.line_ids.id)
        
        return invoice

    # ==========================================
    # MÉTODOS DE ACCIÓN
    # ==========================================
    
    def action_create_in_culqi(self):
        """Acción para crear la suscripción en Culqi."""
        self.create_in_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Suscripción Creada'),
                'message': _('La suscripción ha sido creada exitosamente en Culqi.'),
                'type': 'success',
            }
        }
    
    def action_sync_from_culqi(self):
        """Acción para sincronizar la suscripción desde Culqi."""
        self.retrieve_from_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Suscripción Sincronizada'),
                'message': _('La suscripción ha sido sincronizada exitosamente desde Culqi.'),
                'type': 'success',
            }
        }
    
    def action_cancel(self):
        """Acción para cancelar la suscripción."""
        self.ensure_one()
        
        return {
            'name': _('Cancelar Suscripción'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.subscription.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }
    
    def action_cancel_immediate(self):
        """Cancela la suscripción inmediatamente."""
        self.ensure_one()
        
        self.cancel_in_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Suscripción Cancelada'),
                'message': _('La suscripción ha sido cancelada exitosamente.'),
                'type': 'success',
            }
        }
    
    def action_cancel_at_period_end(self):
        """Programa la cancelación al final del periodo."""
        self.ensure_one()
        
        self.cancel_at_period_end = True
        
        self.message_post(
            body=_('La suscripción se cancelará automáticamente el %s') % self.current_period_end
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cancelación Programada'),
                'message': _('La suscripción se cancelará al final del periodo actual (%s).') % self.current_period_end,
                'type': 'info',
            }
        }
    
    def action_reactivate(self):
        """Reactiva una suscripción cancelada o vencida."""
        self.ensure_one()
        
        if self.state not in ['past_due', 'cancelled', 'unpaid']:
            raise UserError(_('Solo se pueden reactivar suscripciones vencidas, canceladas o impagas.'))
        
        # Verificar que la tarjeta sigue siendo válida
        if self.card_id.state != 'active' or self.card_id.is_expired:
            raise UserError(_('No se puede reactivar: la tarjeta no está activa o está expirada.'))
        
        try:
            # Intentar procesar un pago para reactivar
            success = self.process_billing_cycle()
            
            if success:
                self.state = 'active'
                self.cancel_at_period_end = False
                
                self.message_post(
                    body=_('Suscripción reactivada exitosamente')
                )
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Suscripción Reactivada'),
                        'message': _('La suscripción ha sido reactivada exitosamente.'),
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_('No se pudo procesar el pago para reactivar la suscripción.'))
                
        except Exception as e:
            raise UserError(_('Error al reactivar la suscripción: %s') % str(e))
    
    def action_process_billing_cycle(self):
        """Acción manual para procesar un ciclo de facturación."""
        self.ensure_one()
        
        success = self.process_billing_cycle()
        
        if success:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Facturación Procesada'),
                    'message': _('El ciclo de facturación ha sido procesado exitosamente.'),
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error en Facturación'),
                    'message': _('No se pudo procesar el ciclo de facturación.'),
                    'type': 'danger',
                }
            }
    
    def action_view_transactions(self):
        """Acción para ver las transacciones de la suscripción."""
        self.ensure_one()
        return {
            'name': _('Transacciones de %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.transaction_ids.ids)],
            'context': {'default_culqi_customer_id': self.customer_id.id},
        }
    
    def action_view_invoices(self):
        """Acción para ver las facturas de la suscripción."""
        self.ensure_one()
        return {
            'name': _('Facturas de %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('culqi_subscription_id', '=', self.id)],
            'context': {'default_culqi_subscription_id': self.id},
        }
    
    def action_change_plan(self):
        """Acción para cambiar el plan de la suscripción."""
        self.ensure_one()
        
        return {
            'name': _('Cambiar Plan'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.subscription.change.plan.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }
    
    def action_change_card(self):
        """Acción para cambiar la tarjeta de la suscripción."""
        self.ensure_one()
        
        return {
            'name': _('Cambiar Tarjeta'),
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.subscription.change.card.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }

    # ==========================================
    # MÉTODOS DE MODELO
    # ==========================================
    
    @api.model
    def create(self, vals):
        """Override create para configuración inicial."""
        # Generar referencia si no existe
        if not vals.get('reference') or vals.get('reference') == '/':
            vals['reference'] = self.env['ir.sequence'].next_by_code('culqi.subscription') or '/'
        
        subscription = super().create(vals)
        
        # Configurar fechas iniciales
        subscription._update_billing_period()
        
        return subscription
    
    def write(self, vals):
        """Override write para validaciones y actualizaciones."""
        # Si se cambia el plan, recalcular fechas
        if 'plan_id' in vals:
            for subscription in self:
                if subscription.state == 'draft':
                    subscription._compute_next_billing_date()
        
        # Si se cambia la tarjeta, validar que pertenezca al cliente
        if 'card_id' in vals:
            for subscription in self:
                new_card = self.env['culqi.card'].browse(vals['card_id'])
                if new_card and new_card.customer_id != subscription.customer_id:
                    raise ValidationError(_('La nueva tarjeta debe pertenecer al mismo cliente.'))
        
        return super().write(vals)
    
    def unlink(self):
        """Override unlink para validaciones."""
        for subscription in self:
            if subscription.state == 'active':
                raise UserError(_('No se puede eliminar una suscripción activa. Cancélela primero.'))
            
            if subscription.culqi_subscription_id and subscription.state not in ['cancelled', 'expired']:
                try:
                    subscription.cancel_in_culqi()
                except Exception as e:
                    _logger.warning('No se pudo cancelar suscripción %s en Culqi: %s', subscription.culqi_subscription_id, str(e))
        
        return super().unlink()
    
    @api.model
    def process_scheduled_billing(self):
        """Procesa los ciclos de facturación programados."""
        today = fields.Date.today()
        
        # Buscar suscripciones que necesitan facturación
        subscriptions_to_bill = self.search([
            ('state', 'in', ['active', 'trial']),
            ('next_billing_date', '<=', today),
            ('cancel_at_period_end', '=', False),
        ])
        
        processed_count = 0
        failed_count = 0
        
        for subscription in subscriptions_to_bill:
            try:
                # Si está en trial y ya pasó el periodo, activar
                if subscription.state == 'trial' and not subscription.in_trial:
                    subscription.state = 'active'
                
                success = subscription.process_billing_cycle()
                if success:
                    processed_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                _logger.error('Error al procesar facturación de suscripción %s: %s', subscription.id, str(e))
                failed_count += 1
        
        # Procesar cancelaciones programadas
        subscriptions_to_cancel = self.search([
            ('cancel_at_period_end', '=', True),
            ('current_period_end', '<=', today),
        ])
        
        cancelled_count = 0
        for subscription in subscriptions_to_cancel:
            try:
                subscription.cancel_in_culqi()
                cancelled_count += 1
            except Exception as e:
                _logger.error('Error al cancelar suscripción %s: %s', subscription.id, str(e))
        
        _logger.info(
            'Facturación programada completada: %d procesadas, %d fallidas, %d canceladas',
            processed_count, failed_count, cancelled_count
        )
        
        return {
            'processed': processed_count,
            'failed': failed_count,
            'cancelled': cancelled_count,
        }
    
    @api.model
    def cleanup_failed_subscriptions(self):
        """Limpia suscripciones con múltiples fallos."""
        # Buscar suscripciones con más de 3 fallos consecutivos
        failed_subscriptions = self.search([
            ('state', '=', 'past_due'),
            ('failed_charges', '>=', 3),
        ])
        
        expired_count = 0
        for subscription in failed_subscriptions:
            # Si han pasado más de 30 días desde el último intento, marcar como expirada
            if subscription.next_billing_date and subscription.next_billing_date < fields.Date.today() - timedelta(days=30):
                subscription.state = 'expired'
                subscription.message_post(
                    body=_('Suscripción expirada automáticamente por múltiples fallos de pago')
                )
                expired_count += 1
        
        _logger.info('Limpieza completada: %d suscripciones marcadas como expiradas', expired_count)
        return expired_count
    
    @api.model
    def get_subscription_stats(self):
        """Obtiene estadísticas de suscripciones para dashboard."""
        stats = {}
        
        # Contadores por estado
        for state in self._fields['state'].selection:
            state_code = state[0]
            stats[f'{state_code}_count'] = self.search_count([('state', '=', state_code)])
        
        # Ingresos
        active_subscriptions = self.search([('state', '=', 'active')])
        stats['total_mrr'] = sum(active_subscriptions.mapped(lambda s: s.total_amount * (
            1 if s.plan_id.interval == 'months' and s.plan_id.interval_count == 1
            else s.total_amount / s.plan_id.interval_count if s.plan_id.interval == 'months'
            else s.total_amount / (s.plan_id.interval_count * 12) if s.plan_id.interval == 'years'
            else s.total_amount * 4.33 / s.plan_id.interval_count if s.plan_id.interval == 'weeks'
            else s.total_amount * 30.44 / s.plan_id.interval_count if s.plan_id.interval == 'days'
            else 0
        )))
        
        stats['total_revenue'] = sum(active_subscriptions.mapped('total_paid'))
        
        # Próximas facturaciones
        today = fields.Date.today()
        stats['due_today'] = self.search_count([
            ('state', 'in', ['active', 'trial']),
            ('next_billing_date', '=', today),
        ])
        
        stats['due_this_week'] = self.search_count([
            ('state', 'in', ['active', 'trial']),
            ('next_billing_date', '>=', today),
            ('next_billing_date', '<=', today + timedelta(days=7)),
        ])
        
        return stats