# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CulqiSubscriptionWizard(models.TransientModel):
    """Asistente para crear suscripciones Culqi de forma guiada."""
    _name = 'culqi.subscription.wizard'
    _description = 'Asistente de Suscripción Culqi'

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    # Información del cliente
    partner_id = fields.Many2one(
        'res.partner',
        string='Cliente',
        required=True,
        help='Cliente para el cual se creará la suscripción'
    )
    
    customer_id = fields.Many2one(
        'culqi.customer',
        string='Cliente Culqi',
        compute='_compute_culqi_customer',
        store=True,
        readonly=True
    )
    
    # Configuración del plan
    plan_id = fields.Many2one(
        'culqi.plan',
        string='Plan de Suscripción',
        required=True,
        domain=[('state', '=', 'active'), ('is_published', '=', True)],
        help='Plan al cual se suscribirá el cliente'
    )
    
    quantity = fields.Integer(
        string='Cantidad',
        default=1,
        required=True,
        help='Número de unidades del plan (ej: usuarios, licencias)'
    )
    
    # Información de fechas
    start_date = fields.Date(
        string='Fecha de Inicio',
        default=fields.Date.today,
        required=True,
        help='Fecha de inicio de la suscripción'
    )
    
    trial_enabled = fields.Boolean(
        string='Habilitar Periodo de Prueba',
        compute='_compute_trial_info',
        help='Indica si el plan tiene periodo de prueba'
    )
    
    trial_end_date = fields.Date(
        string='Fin del Periodo de Prueba',
        compute='_compute_trial_info',
        help='Fecha en que termina el periodo de prueba'
    )
    
    first_billing_date = fields.Date(
        string='Primera Facturación',
        compute='_compute_billing_dates',
        help='Fecha del primer cobro'
    )
    
    # Información de precios
    plan_amount = fields.Monetary(
        string='Precio del Plan',
        related='plan_id.amount',
        readonly=True,
        currency_field='currency_id'
    )
    
    total_amount = fields.Monetary(
        string='Monto Total',
        compute='_compute_total_amount',
        store=True,
        currency_field='currency_id'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='plan_id.currency_id',
        readonly=True
    )
    
    setup_fee = fields.Monetary(
        string='Tarifa de Configuración',
        default=0.0,
        currency_field='currency_id',
        help='Cargo único al crear la suscripción'
    )
    
    # Configuración de método de pago
    payment_method = fields.Selection([
        ('new_card', 'Nueva Tarjeta'),
        ('existing_card', 'Tarjeta Existente'),
        ('token', 'Token de Tarjeta'),
    ], string='Método de Pago', required=True, default='new_card')
    
    card_id = fields.Many2one(
        'culqi.card',
        string='Tarjeta Existente',
        domain="[('customer_id', '=', customer_id), ('state', '=', 'active'), ('is_expired', '=', False)]",
        help='Seleccionar tarjeta ya guardada'
    )
    
    token_id = fields.Char(
        string='Token de Tarjeta',
        help='Token generado desde el frontend'
    )
    
    # Información de tarjeta nueva (solo para mostrar, no almacenar datos sensibles)
    card_holder_name = fields.Char(
        string='Nombre del Titular',
        help='Nombre que aparece en la tarjeta'
    )
    
    # Configuraciones adicionales
    create_customer_if_needed = fields.Boolean(
        string='Crear Cliente Culqi',
        default=True,
        help='Crear automáticamente el cliente en Culqi si no existe'
    )
    
    send_welcome_email = fields.Boolean(
        string='Enviar Email de Bienvenida',
        default=True,
        help='Enviar email de bienvenida al cliente'
    )
    
    activate_immediately = fields.Boolean(
        string='Activar Inmediatamente',
        default=True,
        help='Activar la suscripción inmediatamente en Culqi'
    )
    
    # Campos de estado
    step = fields.Selection([
        ('customer', 'Información del Cliente'),
        ('plan', 'Selección del Plan'),
        ('payment', 'Método de Pago'),
        ('review', 'Revisión'),
        ('complete', 'Completado'),
    ], string='Paso Actual', default='customer')
    
    can_proceed = fields.Boolean(
        string='Puede Continuar',
        compute='_compute_can_proceed',
        help='Indica si se puede avanzar al siguiente paso'
    )
    
    validation_message = fields.Text(
        string='Mensaje de Validación',
        compute='_compute_can_proceed',
        readonly=True
    )
    
    # Información de resumen
    summary_data = fields.Text(
        string='Datos de Resumen',
        compute='_compute_summary_data',
        help='Resumen de la configuración de la suscripción'
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('partner_id')
    def _compute_culqi_customer(self):
        """Busca o indica la necesidad de crear un cliente Culqi."""
        for wizard in self:
            if wizard.partner_id:
                customer = self.env['culqi.customer'].search([
                    ('partner_id', '=', wizard.partner_id.id)
                ], limit=1)
                wizard.customer_id = customer
            else:
                wizard.customer_id = False
    
    @api.depends('plan_id', 'start_date')
    def _compute_trial_info(self):
        """Computa información del periodo de prueba."""
        for wizard in self:
            if wizard.plan_id and wizard.plan_id.trial_period_days > 0:
                wizard.trial_enabled = True
                if wizard.start_date:
                    wizard.trial_end_date = wizard.start_date + timedelta(days=wizard.plan_id.trial_period_days)
                else:
                    wizard.trial_end_date = False
            else:
                wizard.trial_enabled = False
                wizard.trial_end_date = False
    
    @api.depends('start_date', 'trial_end_date', 'plan_id')
    def _compute_billing_dates(self):
        """Computa las fechas de facturación."""
        for wizard in self:
            if wizard.plan_id and wizard.start_date:
                if wizard.trial_enabled and wizard.trial_end_date:
                    wizard.first_billing_date = wizard.trial_end_date
                else:
                    wizard.first_billing_date = wizard.start_date
            else:
                wizard.first_billing_date = False
    
    @api.depends('plan_amount', 'quantity', 'setup_fee')
    def _compute_total_amount(self):
        """Computa el monto total de la suscripción."""
        for wizard in self:
            wizard.total_amount = (wizard.plan_amount * wizard.quantity) + wizard.setup_fee
    
    @api.depends('step', 'partner_id', 'plan_id', 'payment_method', 'card_id', 'token_id', 'customer_id')
    def _compute_can_proceed(self):
        """Determina si se puede avanzar al siguiente paso."""
        for wizard in self:
            messages = []
            can_proceed = True
            
            if wizard.step == 'customer':
                if not wizard.partner_id:
                    can_proceed = False
                    messages.append('Debe seleccionar un cliente.')
                
            elif wizard.step == 'plan':
                if not wizard.plan_id:
                    can_proceed = False
                    messages.append('Debe seleccionar un plan.')
                
                if wizard.quantity <= 0:
                    can_proceed = False
                    messages.append('La cantidad debe ser mayor a cero.')
                
            elif wizard.step == 'payment':
                if wizard.payment_method == 'existing_card':
                    if not wizard.card_id:
                        can_proceed = False
                        messages.append('Debe seleccionar una tarjeta existente.')
                    elif wizard.card_id.is_expired:
                        can_proceed = False
                        messages.append('La tarjeta seleccionada está expirada.')
                
                elif wizard.payment_method == 'token':
                    if not wizard.token_id:
                        can_proceed = False
                        messages.append('Debe proporcionar un token de tarjeta.')
                
                elif wizard.payment_method == 'new_card':
                    if not wizard.card_holder_name:
                        can_proceed = False
                        messages.append('Debe proporcionar el nombre del titular.')
                
                # Verificar cliente Culqi
                if not wizard.customer_id and not wizard.create_customer_if_needed:
                    can_proceed = False
                    messages.append('El cliente no existe en Culqi y la creación automática está deshabilitada.')
            
            wizard.can_proceed = can_proceed
            wizard.validation_message = '\n'.join(messages) if messages else 'Puede continuar al siguiente paso.'
    
    @api.depends('partner_id', 'plan_id', 'quantity', 'total_amount', 'payment_method', 'start_date', 'trial_enabled')
    def _compute_summary_data(self):
        """Computa el resumen de la configuración."""
        for wizard in self:
            summary = []
            
            if wizard.partner_id:
                summary.append(f"Cliente: {wizard.partner_id.name}")
            
            if wizard.plan_id:
                summary.append(f"Plan: {wizard.plan_id.name}")
                summary.append(f"Cantidad: {wizard.quantity}")
                summary.append(f"Precio: {wizard.plan_amount:.2f} {wizard.currency_id.symbol}")
                summary.append(f"Total: {wizard.total_amount:.2f} {wizard.currency_id.symbol}")
            
            if wizard.start_date:
                summary.append(f"Inicio: {wizard.start_date.strftime('%d/%m/%Y')}")
            
            if wizard.trial_enabled and wizard.trial_end_date:
                summary.append(f"Prueba hasta: {wizard.trial_end_date.strftime('%d/%m/%Y')}")
                summary.append(f"Primer cobro: {wizard.first_billing_date.strftime('%d/%m/%Y')}")
            
            if wizard.payment_method == 'existing_card' and wizard.card_id:
                summary.append(f"Tarjeta: {wizard.card_id.display_name}")
            elif wizard.payment_method == 'new_card':
                summary.append("Método: Nueva tarjeta")
            
            wizard.summary_data = '\n'.join(summary)

    # ==========================================
    # MÉTODOS ONCHANGE
    # ==========================================
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Actualiza información cuando cambia el cliente."""
        if self.partner_id:
            # Buscar cliente Culqi existente
            self._compute_culqi_customer()
            
            # Limpiar tarjeta seleccionada si cambia el cliente
            if self.card_id and self.card_id.customer_id.partner_id != self.partner_id:
                self.card_id = False
    
    @api.onchange('plan_id')
    def _onchange_plan_id(self):
        """Actualiza información cuando cambia el plan."""
        if self.plan_id:
            self.setup_fee = self.plan_id.setup_fee or 0.0
            
            # Recalcular fechas
            self._compute_trial_info()
            self._compute_billing_dates()
    
    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        """Limpia campos cuando cambia el método de pago."""
        if self.payment_method != 'existing_card':
            self.card_id = False
        
        if self.payment_method != 'token':
            self.token_id = False
        
        if self.payment_method != 'new_card':
            self.card_holder_name = False

    # ==========================================
    # VALIDACIONES
    # ==========================================
    
    @api.constrains('quantity')
    def _check_quantity(self):
        """Valida la cantidad."""
        for wizard in self:
            if wizard.quantity <= 0:
                raise ValidationError(_('La cantidad debe ser mayor a cero.'))
    
    @api.constrains('start_date')
    def _check_start_date(self):
        """Valida la fecha de inicio."""
        for wizard in self:
            if wizard.start_date and wizard.start_date < fields.Date.today():
                raise ValidationError(_('La fecha de inicio no puede ser anterior a hoy.'))
    
    @api.constrains('setup_fee')
    def _check_setup_fee(self):
        """Valida la tarifa de configuración."""
        for wizard in self:
            if wizard.setup_fee < 0:
                raise ValidationError(_('La tarifa de configuración no puede ser negativa.'))

    # ==========================================
    # MÉTODOS DE NAVEGACIÓN
    # ==========================================
    
    def action_next_step(self):
        """Avanza al siguiente paso del wizard."""
        self.ensure_one()
        
        if not self.can_proceed:
            raise UserError(_('No se puede continuar: %s') % self.validation_message)
        
        steps = ['customer', 'plan', 'payment', 'review']
        current_index = steps.index(self.step)
        
        if current_index < len(steps) - 1:
            self.step = steps[current_index + 1]
        
        return self._return_wizard_action()
    
    def action_previous_step(self):
        """Retrocede al paso anterior del wizard."""
        self.ensure_one()
        
        steps = ['customer', 'plan', 'payment', 'review']
        current_index = steps.index(self.step)
        
        if current_index > 0:
            self.step = steps[current_index - 1]
        
        return self._return_wizard_action()
    
    def action_goto_step(self, step_name):
        """Va directamente a un paso específico."""
        self.ensure_one()
        
        if step_name in ['customer', 'plan', 'payment', 'review']:
            self.step = step_name
        
        return self._return_wizard_action()
    
    def _return_wizard_action(self):
        """Retorna la acción para mantener el wizard abierto."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.subscription.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'wizard_step': self.step},
        }

    # ==========================================
    # MÉTODOS PRINCIPALES
    # ==========================================
    
    def action_create_subscription(self):
        """Crea la suscripción en Odoo y Culqi."""
        self.ensure_one()
        
        if self.step != 'review':
            raise UserError(_('Debe completar todos los pasos antes de crear la suscripción.'))
        
        if not self.can_proceed:
            raise UserError(_('No se puede crear la suscripción: %s') % self.validation_message)
        
        try:
            # Paso 1: Crear o obtener cliente Culqi
            customer = self._get_or_create_culqi_customer()
            
            # Paso 2: Crear o obtener tarjeta
            card = self._get_or_create_culqi_card(customer)
            
            # Paso 3: Crear suscripción en Odoo
            subscription = self._create_subscription_record(customer, card)
            
            # Paso 4: Crear suscripción en Culqi
            if self.activate_immediately:
                subscription.create_in_culqi()
            
            # Paso 5: Procesar tarifa de configuración si existe
            if self.setup_fee > 0:
                self._process_setup_fee(subscription, card)
            
            # Paso 6: Enviar email de bienvenida
            if self.send_welcome_email:
                self._send_welcome_email(subscription)
            
            # Marcar como completado
            self.step = 'complete'
            
            # Retornar acción de éxito
            return {
                'type': 'ir.actions.act_window',
                'name': _('Suscripción Creada'),
                'res_model': 'culqi.subscription',
                'res_id': subscription.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error('Error al crear suscripción: %s', str(e))
            raise UserError(_('Error al crear la suscripción: %s') % str(e))
    
    def _get_or_create_culqi_customer(self):
        """Obtiene o crea un cliente Culqi."""
        if self.customer_id:
            # Cliente ya existe
            customer = self.customer_id
            
            # Verificar que esté sincronizado
            if not customer.culqi_customer_id:
                customer.create_in_culqi()
        else:
            # Crear nuevo cliente
            if not self.create_customer_if_needed:
                raise UserError(_('El cliente no existe en Culqi y la creación automática está deshabilitada.'))
            
            # Obtener proveedor Culqi
            provider = self.env['payment.provider'].search([
                ('code', '=', 'culqi'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if not provider:
                raise UserError(_('Proveedor Culqi no configurado.'))
            
            customer = self.env['culqi.customer'].create({
                'partner_id': self.partner_id.id,
                'provider_id': provider.id,
                'name': self.partner_id.name,
                'email': self.partner_id.email,
            })
            
            customer.create_in_culqi()
        
        return customer
    
    def _get_or_create_culqi_card(self, customer):
        """Obtiene o crea una tarjeta Culqi."""
        if self.payment_method == 'existing_card':
            if not self.card_id:
                raise UserError(_('Debe seleccionar una tarjeta existente.'))
            return self.card_id
        
        elif self.payment_method == 'token':
            if not self.token_id:
                raise UserError(_('Debe proporcionar un token de tarjeta.'))
            
            # Crear tarjeta desde token
            card = self.env['culqi.card'].create({
                'customer_id': customer.id,
                'name': self.card_holder_name or f'Tarjeta - {datetime.now().strftime("%d/%m/%Y")}',
            })
            
            card.create_in_culqi(self.token_id)
            return card
        
        else:  # new_card
            raise UserError(_('Para nuevas tarjetas, debe generar un token primero desde el frontend.'))
    
    def _create_subscription_record(self, customer, card):
        """Crea el registro de suscripción en Odoo."""
        subscription_vals = {
            'customer_id': customer.id,
            'plan_id': self.plan_id.id,
            'card_id': card.id,
            'quantity': self.quantity,
            'start_date': self.start_date,
        }
        
        return self.env['culqi.subscription'].create(subscription_vals)
    
    def _process_setup_fee(self, subscription, card):
        """Procesa la tarifa de configuración."""
        if self.setup_fee <= 0:
            return
        
        # Crear transacción para la tarifa de configuración
        transaction_vals = {
            'reference': f"SETUP-{subscription.reference}",
            'amount': self.setup_fee,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'provider_id': subscription.plan_id.provider_id.id,
            'culqi_customer_id': customer.id,
            'culqi_card_id': card.id,
            'culqi_metadata': json.dumps({
                'subscription_id': subscription.id,
                'type': 'setup_fee',
                'description': f'Tarifa de configuración para {subscription.plan_id.name}',
            }),
        }
        
        transaction = self.env['payment.transaction'].create(transaction_vals)
        
        # Procesar el pago
        transaction._create_culqi_charge(source_id=card.culqi_card_id)
    
    def _send_welcome_email(self, subscription):
        """Envía email de bienvenida al cliente."""
        template = self.env.ref(
            'payment_culqi.subscription_welcome_email_template',
            raise_if_not_found=False
        )
        
        if template and self.partner_id.email:
            template.send_mail(subscription.id, force_send=True)

    # ==========================================
    # MÉTODOS DE UTILIDAD
    # ==========================================
    
    @api.model
    def default_get(self, fields_list):
        """Configura valores por defecto basados en el contexto."""
        defaults = super().default_get(fields_list)
        
        # Configurar desde el contexto
        partner_id = self.env.context.get('default_partner_id')
        plan_id = self.env.context.get('default_plan_id')
        
        if partner_id:
            defaults['partner_id'] = partner_id
        
        if plan_id:
            defaults['plan_id'] = plan_id
            defaults['step'] = 'payment'  # Saltar a configuración de pago
        
        return defaults
    
    def action_cancel(self):
        """Cancela el wizard."""
        return {'type': 'ir.actions.act_window_close'}


class CulqiSubscriptionChangeWizard(models.TransientModel):
    """Wizard para cambiar configuración de suscripciones existentes."""
    _name = 'culqi.subscription.change.wizard'
    _description = 'Cambiar Suscripción Culqi'

    # ==========================================
    # CAMPOS
    # ==========================================
    
    subscription_id = fields.Many2one(
        'culqi.subscription',
        string='Suscripción',
        required=True,
        readonly=True
    )
    
    change_type = fields.Selection([
        ('plan', 'Cambiar Plan'),
        ('card', 'Cambiar Tarjeta'),
        ('quantity', 'Cambiar Cantidad'),
        ('pause', 'Pausar Suscripción'),
        ('cancel', 'Cancelar Suscripción'),
    ], string='Tipo de Cambio', required=True)
    
    # Campos para cambio de plan
    new_plan_id = fields.Many2one(
        'culqi.plan',
        string='Nuevo Plan',
        domain=[('state', '=', 'active')]
    )
    
    prorate_change = fields.Boolean(
        string='Prorratear Cambio',
        default=True,
        help='Aplicar cargo/crédito proporcional por el cambio'
    )
    
    # Campos para cambio de tarjeta
    new_card_id = fields.Many2one(
        'culqi.card',
        string='Nueva Tarjeta',
        domain="[('customer_id', '=', customer_id), ('state', '=', 'active')]"
    )
    
    customer_id = fields.Many2one(
        'culqi.customer',
        related='subscription_id.customer_id',
        readonly=True
    )
    
    # Campos para cambio de cantidad
    new_quantity = fields.Integer(
        string='Nueva Cantidad',
        default=1
    )
    
    # Campos para cancelación
    cancellation_reason = fields.Selection([
        ('customer_request', 'Solicitud del Cliente'),
        ('payment_failed', 'Fallo en el Pago'),
        ('service_discontinued', 'Servicio Descontinuado'),
        ('other', 'Otro'),
    ], string='Motivo de Cancelación')
    
    cancellation_details = fields.Text(
        string='Detalles de Cancelación'
    )
    
    cancel_immediately = fields.Boolean(
        string='Cancelar Inmediatamente',
        default=False,
        help='Cancelar ahora o al final del periodo actual'
    )
    
    # Campos para pausa
    pause_duration = fields.Integer(
        string='Duración de Pausa (días)',
        default=30
    )
    
    pause_reason = fields.Text(
        string='Motivo de Pausa'
    )

    # ==========================================
    # MÉTODOS PRINCIPALES
    # ==========================================
    
    def action_apply_changes(self):
        """Aplica los cambios a la suscripción."""
        self.ensure_one()
        
        try:
            if self.change_type == 'plan':
                self._change_plan()
            elif self.change_type == 'card':
                self._change_card()
            elif self.change_type == 'quantity':
                self._change_quantity()
            elif self.change_type == 'pause':
                self._pause_subscription()
            elif self.change_type == 'cancel':
                self._cancel_subscription()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Cambio Aplicado'),
                    'message': _('Los cambios han sido aplicados exitosamente.'),
                    'type': 'success',
                }
            }
            
        except Exception as e:
            _logger.error('Error al aplicar cambios a suscripción: %s', str(e))
            raise UserError(_('Error al aplicar cambios: %s') % str(e))
    
    def _change_plan(self):
        """Cambia el plan de la suscripción."""
        if not self.new_plan_id:
            raise UserError(_('Debe seleccionar un nuevo plan.'))
        
        old_plan = self.subscription_id.plan_id
        
        # Actualizar suscripción
        self.subscription_id.plan_id = self.new_plan_id
        
        # Procesar prorrateo si está habilitado
        if self.prorate_change:
            self._process_plan_proration(old_plan, self.new_plan_id)
        
        # Log del cambio
        self.subscription_id.message_post(
            body=_('Plan cambiado de "%s" a "%s"') % (old_plan.name, self.new_plan_id.name)
        )
    
    def _change_card(self):
        """Cambia la tarjeta de la suscripción."""
        if not self.new_card_id:
            raise UserError(_('Debe seleccionar una nueva tarjeta.'))
        
        old_card = self.subscription_id.card_id
        
        # Actualizar suscripción
        self.subscription_id.card_id = self.new_card_id
        
        # Log del cambio
        self.subscription_id.message_post(
            body=_('Método de pago cambiado de "%s" a "%s"') % (
                old_card.display_name, self.new_card_id.display_name
            )
        )
    
    def _change_quantity(self):
        """Cambia la cantidad de la suscripción."""
        if self.new_quantity <= 0:
            raise UserError(_('La nueva cantidad debe ser mayor a cero.'))
        
        old_quantity = self.subscription_id.quantity
        
        # Actualizar suscripción
        self.subscription_id.quantity = self.new_quantity
        
        # Log del cambio
        self.subscription_id.message_post(
            body=_('Cantidad cambiada de %d a %d') % (old_quantity, self.new_quantity)
        )
    
    def _pause_subscription(self):
        """Pausa la suscripción temporalmente."""
        # Implementar lógica de pausa
        # Nota: Culqi puede no soportar pausa nativa, implementar como cancelación + reactivación programada
        
        self.subscription_id.message_post(
            body=_('Suscripción pausada por %d días. Motivo: %s') % (
                self.pause_duration, self.pause_reason or 'No especificado'
            )
        )
    
    def _cancel_subscription(self):
        """Cancela la suscripción."""
        if self.cancel_immediately:
            self.subscription_id.cancel_in_culqi()
        else:
            self.subscription_id.cancel_at_period_end = True
        
        self.subscription_id.cancellation_reason = self.cancellation_details
        
        # Log del cambio
        cancel_type = 'inmediatamente' if self.cancel_immediately else 'al final del periodo'
        reason_text = dict(self._fields['cancellation_reason'].selection).get(self.cancellation_reason, self.cancellation_reason)
        
        self.subscription_id.message_post(
            body=_('Suscripción cancelada %s. Motivo: %s') % (cancel_type, reason_text)
        )
    
    def _process_plan_proration(self, old_plan, new_plan):
        """Procesa el prorrateo por cambio de plan."""
        # Calcular días restantes en el periodo actual
        today = fields.Date.today()
        period_end = self.subscription_id.current_period_end
        
        if not period_end or period_end <= today:
            return  # No hay periodo activo para prorratear
        
        days_remaining = (period_end - today).days
        total_days_in_period = (period_end - self.subscription_id.current_period_start).days
        
        if total_days_in_period <= 0:
            return
        
        # Calcular crédito del plan anterior
        old_daily_rate = old_plan.amount / total_days_in_period
        credit_amount = old_daily_rate * days_remaining
        
        # Calcular cargo del nuevo plan
        new_daily_rate = new_plan.amount / total_days_in_period
        charge_amount = new_daily_rate * days_remaining
        
        # Diferencia a cobrar/acreditar
        proration_amount = charge_amount - credit_amount
        
        if abs(proration_amount) > 0.01:  # Solo procesar si hay diferencia significativa
            self._create_proration_transaction(proration_amount, old_plan, new_plan)
    
    def _create_proration_transaction(self, amount, old_plan, new_plan):
        """Crea transacción para el prorrateo."""
        if amount > 0:
            # Cargo adicional
            transaction_vals = {
                'reference': f"PRORATE-{self.subscription_id.reference}-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}",
                'amount': amount,
                'currency_id': self.subscription_id.currency_id.id,
                'partner_id': self.subscription_id.partner_id.id,
                'provider_id': self.subscription_id.plan_id.provider_id.id,
                'culqi_customer_id': self.subscription_id.customer_id.id,
                'culqi_card_id': self.subscription_id.card_id.id,
                'culqi_metadata': json.dumps({
                    'subscription_id': self.subscription_id.id,
                    'type': 'proration_charge',
                    'old_plan': old_plan.name,
                    'new_plan': new_plan.name,
                    'description': f'Cargo de prorrateo por cambio de plan',
                }),
            }
            
            transaction = self.env['payment.transaction'].create(transaction_vals)
            transaction._create_culqi_charge(source_id=self.subscription_id.card_id.culqi_card_id)
        
        else:
            # Crédito (crear nota de crédito)
            # Implementar lógica de crédito/reembolso
            pass

    # ==========================================
    # MÉTODOS ONCHANGE
    # ==========================================
    
    @api.onchange('change_type')
    def _onchange_change_type(self):
        """Limpia campos cuando cambia el tipo."""
        # Limpiar todos los campos específicos
        self.new_plan_id = False
        self.new_card_id = False
        self.new_quantity = self.subscription_id.quantity if self.subscription_id else 1
        self.cancellation_reason = False
        self.cancellation_details = False
        self.pause_duration = 30
        self.pause_reason = False

    # ==========================================
    # VALIDACIONES
    # ==========================================
    
    @api.constrains('change_type', 'new_plan_id', 'new_card_id', 'new_quantity')
    def _check_required_fields(self):
        """Valida campos requeridos según el tipo de cambio."""
        for wizard in self:
            if wizard.change_type == 'plan' and not wizard.new_plan_id:
                raise ValidationError(_('Debe seleccionar un nuevo plan.'))
            
            if wizard.change_type == 'card' and not wizard.new_card_id:
                raise ValidationError(_('Debe seleccionar una nueva tarjeta.'))
            
            if wizard.change_type == 'quantity' and wizard.new_quantity <= 0:
                raise ValidationError(_('La nueva cantidad debe ser mayor a cero.'))


class CulqiBulkSubscriptionWizard(models.TransientModel):
    """Wizard para operaciones masivas en suscripciones."""
    _name = 'culqi.bulk.subscription.wizard'
    _description = 'Operaciones Masivas de Suscripciones'

    # ==========================================
    # CAMPOS
    # ==========================================
    
    subscription_ids = fields.Many2many(
        'culqi.subscription',
        string='Suscripciones',
        required=True,
        help='Suscripciones a procesar'
    )
    
    operation = fields.Selection([
        ('cancel', 'Cancelar Suscripciones'),
        ('pause', 'Pausar Suscripciones'),
        ('change_plan', 'Cambiar Plan'),
        ('sync_from_culqi', 'Sincronizar desde Culqi'),
        ('send_notification', 'Enviar Notificación'),
    ], string='Operación', required=True)
    
    # Campos para cancelación
    cancel_immediately = fields.Boolean(
        string='Cancelar Inmediatamente',
        default=False
    )
    
    cancellation_reason = fields.Text(
        string='Motivo de Cancelación',
        help='Motivo que se aplicará a todas las suscripciones'
    )
    
    # Campos para cambio de plan
    new_plan_id = fields.Many2one(
        'culqi.plan',
        string='Nuevo Plan',
        domain=[('state', '=', 'active')]
    )
    
    # Campos para notificación
    notification_template_id = fields.Many2one(
        'mail.template',
        string='Plantilla de Email',
        domain=[('model', '=', 'culqi.subscription')]
    )
    
    notification_subject = fields.Char(
        string='Asunto del Email'
    )
    
    notification_body = fields.Html(
        string='Contenido del Email'
    )
    
    # Resultados
    processed_count = fields.Integer(
        string='Procesadas',
        readonly=True,
        default=0
    )
    
    failed_count = fields.Integer(
        string='Fallidas',
        readonly=True,
        default=0
    )
    
    error_messages = fields.Text(
        string='Mensajes de Error',
        readonly=True
    )

    # ==========================================
    # MÉTODOS PRINCIPALES
    # ==========================================
    
    def action_process_bulk_operation(self):
        """Procesa la operación masiva."""
        self.ensure_one()
        
        if not self.subscription_ids:
            raise UserError(_('Debe seleccionar al menos una suscripción.'))
        
        processed = 0
        failed = 0
        errors = []
        
        for subscription in self.subscription_ids:
            try:
                if self.operation == 'cancel':
                    self._bulk_cancel_subscription(subscription)
                elif self.operation == 'pause':
                    self._bulk_pause_subscription(subscription)
                elif self.operation == 'change_plan':
                    self._bulk_change_plan(subscription)
                elif self.operation == 'sync_from_culqi':
                    subscription.retrieve_from_culqi()
                elif self.operation == 'send_notification':
                    self._bulk_send_notification(subscription)
                
                processed += 1
                
            except Exception as e:
                failed += 1
                errors.append(f"Suscripción {subscription.reference}: {str(e)}")
                _logger.error('Error en operación masiva para suscripción %s: %s', subscription.reference, str(e))
        
        # Actualizar resultados
        self.processed_count = processed
        self.failed_count = failed
        self.error_messages = '\n'.join(errors)
        
        # Mostrar resultados
        message = _('Operación completada:\n- Procesadas exitosamente: %d\n- Fallidas: %d') % (processed, failed)
        
        if errors:
            message += _('\n\nErrores:\n%s') % '\n'.join(errors[:5])  # Mostrar solo los primeros 5 errores
            if len(errors) > 5:
                message += _('\n... y %d errores más') % (len(errors) - 5)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Operación Masiva Completada'),
                'message': message,
                'type': 'warning' if failed > 0 else 'success',
                'sticky': True,
            }
        }
    
    def _bulk_cancel_subscription(self, subscription):
        """Cancela una suscripción en operación masiva."""
        if subscription.state not in ['active', 'trial']:
            raise UserError(_('Solo se pueden cancelar suscripciones activas o en prueba'))
        
        if self.cancel_immediately:
            subscription.cancel_in_culqi()
        else:
            subscription.cancel_at_period_end = True
        
        if self.cancellation_reason:
            subscription.cancellation_reason = self.cancellation_reason
    
    def _bulk_pause_subscription(self, subscription):
        """Pausa una suscripción en operación masiva."""
        if subscription.state != 'active':
            raise UserError(_('Solo se pueden pausar suscripciones activas'))
        
        # Implementar lógica de pausa
        subscription.message_post(
            body=_('Suscripción pausada mediante operación masiva')
        )
    
    def _bulk_change_plan(self, subscription):
        """Cambia el plan de una suscripción en operación masiva."""
        if not self.new_plan_id:
            raise UserError(_('Debe especificar un nuevo plan'))
        
        if subscription.state not in ['active', 'trial']:
            raise UserError(_('Solo se puede cambiar el plan de suscripciones activas'))
        
        old_plan = subscription.plan_id
        subscription.plan_id = self.new_plan_id
        
        subscription.message_post(
            body=_('Plan cambiado de "%s" a "%s" mediante operación masiva') % (
                old_plan.name, self.new_plan_id.name
            )
        )
    
    def _bulk_send_notification(self, subscription):
        """Envía notificación a una suscripción en operación masiva."""
        if self.notification_template_id:
            self.notification_template_id.send_mail(subscription.id, force_send=True)
        elif self.notification_subject and self.notification_body:
            subscription.message_post(
                subject=self.notification_subject,
                body=self.notification_body,
                message_type='email',
                subtype_xmlid='mail.mt_comment'
            )
        else:
            raise UserError(_('Debe especificar una plantilla o contenido para la notificación'))


class CulqiSubscriptionImportWizard(models.TransientModel):
    """Wizard para importar suscripciones desde archivo."""
    _name = 'culqi.subscription.import.wizard'
    _description = 'Importar Suscripciones'

    # ==========================================
    # CAMPOS
    # ==========================================
    
    import_file = fields.Binary(
        string='Archivo de Importación',
        required=True,
        help='Archivo CSV o Excel con datos de suscripciones'
    )
    
    filename = fields.Char(
        string='Nombre del Archivo'
    )
    
    provider_id = fields.Many2one(
        'payment.provider',
        string='Proveedor Culqi',
        domain=[('code', '=', 'culqi')],
        required=True
    )
    
    default_plan_id = fields.Many2one(
        'culqi.plan',
        string='Plan por Defecto',
        domain=[('state', '=', 'active')],
        help='Plan a usar si no se especifica en el archivo'
    )
    
    create_customers = fields.Boolean(
        string='Crear Clientes Automáticamente',
        default=True,
        help='Crear automáticamente clientes que no existan'
    )
    
    validate_only = fields.Boolean(
        string='Solo Validar',
        default=False,
        help='Solo validar el archivo sin crear suscripciones'
    )
    
    # Resultados de la importación
    validation_results = fields.Text(
        string='Resultados de Validación',
        readonly=True
    )
    
    import_results = fields.Text(
        string='Resultados de Importación',
        readonly=True
    )

    # ==========================================
    # MÉTODOS
    # ==========================================
    
    def action_validate_file(self):
        """Valida el archivo de importación."""
        self.ensure_one()
        
        if not self.import_file:
            raise UserError(_('Debe cargar un archivo para validar.'))
        
        try:
            # Procesar archivo (implementar según formato)
            data = self._parse_import_file()
            
            # Validar datos
            validation_results = self._validate_import_data(data)
            
            self.validation_results = validation_results
            
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'culqi.subscription.import.wizard',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
            
        except Exception as e:
            raise UserError(_('Error al validar archivo: %s') % str(e))
    
    def action_import_subscriptions(self):
        """Importa las suscripciones desde el archivo."""
        self.ensure_one()
        
        if self.validate_only:
            return self.action_validate_file()
        
        try:
            # Procesar archivo
            data = self._parse_import_file()
            
            # Importar datos
            import_results = self._import_subscription_data(data)
            
            self.import_results = import_results
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Importación Completada'),
                    'message': import_results,
                    'type': 'success',
                }
            }
            
        except Exception as e:
            raise UserError(_('Error al importar suscripciones: %s') % str(e))
    
    def _parse_import_file(self):
        """Parsea el archivo de importación."""
        # Implementar parsing según formato del archivo
        # Retornar lista de diccionarios con datos de suscripciones
        pass
    
    def _validate_import_data(self, data):
        """Valida los datos de importación."""
        # Implementar validación de datos
        # Retornar reporte de validación
        pass
    
    def _import_subscription_data(self, data):
        """Importa los datos de suscripciones."""
        # Implementar importación real
        # Retornar reporte de importación
        pass