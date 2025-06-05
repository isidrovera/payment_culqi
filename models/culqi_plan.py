# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CulqiPlan(models.Model):
    _name = 'culqi.plan'
    _description = 'Plan de Suscripción Culqi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'
    _rec_name = 'display_name'

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    name = fields.Char(
        string='Nombre del Plan',
        required=True,
        tracking=True,
        help='Nombre identificativo del plan'
    )
    
    description = fields.Text(
        string='Descripción',
        tracking=True,
        help='Descripción detallada del plan'
    )
    
    display_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_display_name',
        store=True
    )
    
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
        help='Orden de visualización de los planes'
    )
    
    # Identificadores
    culqi_plan_id = fields.Char(
        string='ID de Plan Culqi',
        readonly=True,
        tracking=True,
        help='ID único del plan en Culqi'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True
    )
    
    provider_id = fields.Many2one(
        'payment.provider',
        string='Proveedor de Pago',
        domain=[('code', '=', 'culqi')],
        required=True
    )
    
    # Configuración de precios
    amount = fields.Monetary(
        string='Precio',
        required=True,
        tracking=True,
        help='Precio del plan por periodo'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True
    )
    
    # Configuración de facturación
    interval = fields.Selection([
        ('days', 'Días'),
        ('weeks', 'Semanas'),
        ('months', 'Meses'),
        ('years', 'Años'),
    ], string='Intervalo', required=True, default='months', tracking=True)
    
    interval_count = fields.Integer(
        string='Cada',
        required=True,
        default=1,
        tracking=True,
        help='Frecuencia del intervalo (ej: cada 2 meses)'
    )
    
    # Configuración de prueba
    trial_period_days = fields.Integer(
        string='Días de Prueba',
        default=0,
        tracking=True,
        help='Número de días de prueba gratuita'
    )
    
    # Configuración de límites
    max_charges = fields.Integer(
        string='Máximo de Cargos',
        default=0,
        help='Número máximo de cargos (0 = ilimitado)'
    )
    
    max_subscribers = fields.Integer(
        string='Máximo de Suscriptores',
        default=0,
        help='Número máximo de suscriptores (0 = ilimitado)'
    )
    
    # Estados
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activo'),
        ('inactive', 'Inactivo'),
        ('archived', 'Archivado'),
    ], string='Estado', default='draft', tracking=True)
    
    is_published = fields.Boolean(
        string='Publicado',
        default=False,
        tracking=True,
        help='Visible para los clientes'
    )
    
    is_synced = fields.Boolean(
        string='Sincronizado',
        default=False,
        tracking=True,
        help='Indica si el plan está sincronizado con Culqi'
    )
    
    # Configuración avanzada
    setup_fee = fields.Monetary(
        string='Tarifa de Configuración',
        default=0.0,
        currency_field='currency_id',
        help='Cargo único al suscribirse'
    )
    
    cancellation_fee = fields.Monetary(
        string='Tarifa de Cancelación',
        default=0.0,
        currency_field='currency_id',
        help='Cargo por cancelación anticipada'
    )
    
    # Configuración de producto (integración con Odoo)
    product_id = fields.Many2one(
        'product.product',
        string='Producto Relacionado',
        help='Producto de Odoo asociado al plan'
    )
    
    product_template_id = fields.Many2one(
        'product.template',
        string='Plantilla de Producto',
        related='product_id.product_tmpl_id',
        readonly=True
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
    
    # Fechas importantes
    culqi_creation_date = fields.Datetime(
        string='Fecha de Creación en Culqi',
        readonly=True
    )
    
    last_sync_date = fields.Datetime(
        string='Última Sincronización',
        readonly=True
    )
    
    # Relaciones
    subscription_ids = fields.One2many(
        'culqi.subscription',
        'plan_id',
        string='Suscripciones',
        help='Suscripciones a este plan'
    )
    
    # Campos computados
    subscription_count = fields.Integer(
        string='Número de Suscripciones',
        compute='_compute_counts'
    )
    
    active_subscription_count = fields.Integer(
        string='Suscripciones Activas',
        compute='_compute_counts'
    )
    
    total_revenue = fields.Monetary(
        string='Ingresos Totales',
        compute='_compute_amounts',
        currency_field='currency_id'
    )
    
    monthly_recurring_revenue = fields.Monetary(
        string='Ingresos Recurrentes Mensuales',
        compute='_compute_amounts',
        currency_field='currency_id',
        help='MRR - Monthly Recurring Revenue'
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('name', 'amount', 'interval', 'interval_count', 'currency_id')
    def _compute_display_name(self):
        """Computa el nombre para mostrar."""
        for plan in self:
            if plan.name and plan.amount and plan.interval:
                interval_text = dict(plan._fields['interval'].selection).get(plan.interval, plan.interval)
                if plan.interval_count > 1:
                    interval_text = f"{plan.interval_count} {interval_text}"
                
                plan.display_name = f"{plan.name} - {plan.amount:.2f} {plan.currency_id.symbol} / {interval_text}"
            elif plan.name:
                plan.display_name = plan.name
            else:
                plan.display_name = 'Plan sin nombre'
    
    @api.depends('subscription_ids', 'subscription_ids.state')
    def _compute_counts(self):
        """Computa los contadores de suscripciones."""
        for plan in self:
            plan.subscription_count = len(plan.subscription_ids)
            plan.active_subscription_count = len(plan.subscription_ids.filtered(
                lambda s: s.state == 'active'
            ))
    
    @api.depends('subscription_ids.total_paid', 'subscription_ids.state', 'amount', 'interval', 'interval_count')
    def _compute_amounts(self):
        """Computa los montos de ingresos."""
        for plan in self:
            # Ingresos totales de todas las suscripciones
            plan.total_revenue = sum(plan.subscription_ids.mapped('total_paid'))
            
            # MRR - Convertir el precio del plan a mensual
            if plan.interval == 'months':
                monthly_amount = plan.amount / plan.interval_count
            elif plan.interval == 'years':
                monthly_amount = plan.amount / (plan.interval_count * 12)
            elif plan.interval == 'weeks':
                monthly_amount = plan.amount * 4.33 / plan.interval_count  # 4.33 semanas promedio por mes
            elif plan.interval == 'days':
                monthly_amount = plan.amount * 30.44 / plan.interval_count  # 30.44 días promedio por mes
            else:
                monthly_amount = 0
            
            # MRR = precio mensual * suscripciones activas
            plan.monthly_recurring_revenue = monthly_amount * plan.active_subscription_count

    # ==========================================
    # VALIDACIONES Y CONSTRAINS
    # ==========================================
    
    @api.constrains('amount')
    def _check_amount(self):
        """Valida que el precio sea positivo."""
        for plan in self:
            if plan.amount <= 0:
                raise ValidationError(_('El precio del plan debe ser mayor a cero.'))
    
    @api.constrains('interval_count')
    def _check_interval_count(self):
        """Valida que el conteo de intervalo sea positivo."""
        for plan in self:
            if plan.interval_count <= 0:
                raise ValidationError(_('El intervalo debe ser mayor a cero.'))
    
    @api.constrains('trial_period_days')
    def _check_trial_period(self):
        """Valida el periodo de prueba."""
        for plan in self:
            if plan.trial_period_days < 0:
                raise ValidationError(_('El periodo de prueba no puede ser negativo.'))
    
    @api.constrains('max_charges', 'max_subscribers')
    def _check_limits(self):
        """Valida los límites del plan."""
        for plan in self:
            if plan.max_charges < 0:
                raise ValidationError(_('El máximo de cargos no puede ser negativo.'))
            if plan.max_subscribers < 0:
                raise ValidationError(_('El máximo de suscriptores no puede ser negativo.'))
    
    @api.constrains('currency_id', 'provider_id')
    def _check_currency_support(self):
        """Valida que la moneda sea soportada por Culqi."""
        for plan in self:
            if plan.provider_id and plan.currency_id:
                supported_currencies = plan.provider_id._get_supported_currencies()
                if plan.currency_id not in supported_currencies:
                    raise ValidationError(_(
                        'La moneda %s no es soportada por el proveedor %s.'
                    ) % (plan.currency_id.name, plan.provider_id.name))

    # ==========================================
    # MÉTODOS ONCHANGE
    # ==========================================
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Actualiza campos cuando cambia el producto."""
        if self.product_id:
            self.name = self.product_id.name
            self.description = self.product_id.description_sale or self.product_id.description
            self.amount = self.product_id.list_price
            
            # Si el producto tiene impuestos, mostrar advertencia
            if self.product_id.taxes_id:
                return {
                    'warning': {
                        'title': _('Impuestos del Producto'),
                        'message': _('El producto seleccionado tiene impuestos configurados. '
                                   'Asegúrese de que el precio del plan incluya todos los impuestos aplicables.')
                    }
                }

    # ==========================================
    # MÉTODOS DE CULQI API
    # ==========================================
    
    def _get_culqi_client(self):
        """Obtiene el cliente Culqi configurado."""
        self.ensure_one()
        if not self.provider_id:
            raise UserError(_('No hay proveedor de pago configurado.'))
        return self.provider_id._get_culqi_client()
    
    def _prepare_culqi_plan_data(self):
        """Prepara los datos para enviar a Culqi."""
        self.ensure_one()
        
        # Convertir el precio a centavos
        amount_in_cents = int(self.amount * 100)
        
        # Mapear intervalo a formato Culqi
        interval_mapping = {
            'days': 'days',
            'weeks': 'weeks', 
            'months': 'months',
            'years': 'years'
        }
        
        plan_data = {
            'name': self.name,
            'amount': amount_in_cents,
            'currency_code': self.currency_id.name,
            'interval': interval_mapping[self.interval],
            'interval_count': self.interval_count,
        }
        
        # Campos opcionales
        if self.description:
            plan_data['description'] = self.description
        
        if self.trial_period_days > 0:
            plan_data['trial_period_days'] = self.trial_period_days
        
        if self.max_charges > 0:
            plan_data['max_charges'] = self.max_charges
        
        # Metadatos
        metadata = {
            'odoo_plan_id': self.id,
            'odoo_company_id': self.company_id.id,
            'created_from': 'odoo',
        }
        
        if self.product_id:
            metadata.update({
                'product_id': self.product_id.id,
                'product_name': self.product_id.name,
            })
        
        # Agregar metadatos personalizados si existen
        if self.culqi_metadata:
            try:
                custom_metadata = json.loads(self.culqi_metadata)
                metadata.update(custom_metadata)
            except json.JSONDecodeError:
                _logger.warning('Metadatos JSON inválidos para plan %s', self.id)
        
        plan_data['metadata'] = metadata
        
        return plan_data
    
    def create_in_culqi(self):
        """Crea el plan en Culqi."""
        self.ensure_one()
        
        if self.culqi_plan_id:
            raise UserError(_('El plan ya está creado en Culqi: %s') % self.culqi_plan_id)
        
        try:
            client = self._get_culqi_client()
            plan_data = self._prepare_culqi_plan_data()
            
            _logger.info('Creando plan en Culqi: %s', self.name)
            
            response = client.plan.create(data=plan_data)
            
            if response.get('object') == 'plan':
                self._process_culqi_response(response)
                self.state = 'active'
                self.is_synced = True
                self.last_sync_date = fields.Datetime.now()
                
                self.message_post(
                    body=_('Plan creado exitosamente en Culqi: %s') % response['id']
                )
                
                _logger.info('Plan creado en Culqi: %s', response['id'])
                return response
            else:
                raise UserError(_('Error al crear plan: %s') % response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al crear plan en Culqi: %s', str(e))
            self.message_post(
                body=_('Error al crear plan en Culqi: %s') % str(e)
            )
            raise UserError(_('Error al crear plan en Culqi: %s') % str(e))
    
    def update_in_culqi(self):
        """Actualiza el plan en Culqi."""
        self.ensure_one()
        
        if not self.culqi_plan_id:
            raise UserError(_('El plan no está creado en Culqi. Use "Crear en Culqi" primero.'))
        
        try:
            client = self._get_culqi_client()
            plan_data = self._prepare_culqi_plan_data()
            
            # Remover campos que no se pueden actualizar
            update_data = {
                'name': plan_data['name'],
                'metadata': plan_data['metadata']
            }
            
            if 'description' in plan_data:
                update_data['description'] = plan_data['description']
            
            _logger.info('Actualizando plan en Culqi: %s', self.culqi_plan_id)
            
            response = client.plan.update(id_=self.culqi_plan_id, data=update_data)
            
            if response.get('object') == 'plan':
                self._process_culqi_response(response)
                self.is_synced = True
                self.last_sync_date = fields.Datetime.now()
                
                self.message_post(
                    body=_('Plan actualizado exitosamente en Culqi')
                )
                
                _logger.info('Plan actualizado en Culqi: %s', self.culqi_plan_id)
                return response
            else:
                raise UserError(_('Error al actualizar plan: %s') % response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al actualizar plan en Culqi: %s', str(e))
            self.message_post(
                body=_('Error al actualizar plan en Culqi: %s') % str(e)
            )
            raise UserError(_('Error al actualizar plan en Culqi: %s') % str(e))
    
    def retrieve_from_culqi(self):
        """Obtiene la información del plan desde Culqi."""
        self.ensure_one()
        
        if not self.culqi_plan_id:
            raise UserError(_('No hay ID de plan en Culqi para sincronizar.'))
        
        try:
            client = self._get_culqi_client()
            
            _logger.info('Obteniendo plan desde Culqi: %s', self.culqi_plan_id)
            
            response = client.plan.read(self.culqi_plan_id)
            
            if response.get('object') == 'plan':
                self._process_culqi_response(response)
                self.is_synced = True
                self.last_sync_date = fields.Datetime.now()
                
                self.message_post(
                    body=_('Plan sincronizado exitosamente desde Culqi')
                )
                
                _logger.info('Plan sincronizado desde Culqi: %s', self.culqi_plan_id)
                return response
            else:
                raise UserError(_('Error al obtener plan: %s') % response.get('user_message', 'Plan no encontrado'))
                
        except Exception as e:
            _logger.error('Error al obtener plan desde Culqi: %s', str(e))
            self.message_post(
                body=_('Error al sincronizar plan desde Culqi: %s') % str(e)
            )
            raise UserError(_('Error al sincronizar plan desde Culqi: %s') % str(e))
    
    def _process_culqi_response(self, response):
        """Procesa la respuesta de Culqi y actualiza los campos."""
        self.ensure_one()
        
        # Actualizar ID si es necesario
        if response.get('id') and not self.culqi_plan_id:
            self.culqi_plan_id = response['id']
        
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

    # ==========================================
    # MÉTODOS DE ACCIÓN
    # ==========================================
    
    def action_create_in_culqi(self):
        """Acción para crear el plan en Culqi."""
        self.create_in_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plan Creado'),
                'message': _('El plan ha sido creado exitosamente en Culqi.'),
                'type': 'success',
            }
        }
    
    def action_update_in_culqi(self):
        """Acción para actualizar el plan en Culqi."""
        self.update_in_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plan Actualizado'),
                'message': _('El plan ha sido actualizado exitosamente en Culqi.'),
                'type': 'success',
            }
        }
    
    def action_sync_from_culqi(self):
        """Acción para sincronizar el plan desde Culqi."""
        self.retrieve_from_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plan Sincronizado'),
                'message': _('El plan ha sido sincronizado exitosamente desde Culqi.'),
                'type': 'success',
            }
        }
    
    def action_archive(self):
        """Acción para archivar el plan."""
        self.ensure_one()
        
        # Verificar que no tenga suscripciones activas
        active_subscriptions = self.subscription_ids.filtered(lambda s: s.state == 'active')
        if active_subscriptions:
            raise UserError(_('No se puede archivar un plan con suscripciones activas.'))
        
        self.state = 'archived'
        self.is_published = False
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plan Archivado'),
                'message': _('El plan ha sido archivado exitosamente.'),
                'type': 'success',
            }
        }
    
    def action_publish(self):
        """Acción para publicar el plan."""
        self.ensure_one()
        
        if self.state != 'active':
            raise UserError(_('Solo se pueden publicar planes activos.'))
        
        if not self.culqi_plan_id:
            raise UserError(_('El plan debe estar creado en Culqi antes de publicarlo.'))
        
        self.is_published = True
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Plan Publicado'),
                'message': _('El plan ha sido publicado y está disponible para suscripciones.'),
                'type': 'success',
            }
        }
    
    def action_view_subscriptions(self):
        """Acción para ver las suscripciones del plan."""
        self.ensure_one()
        return {
            'name': _('Suscripciones de %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.subscription',
            'view_mode': 'tree,form',
            'domain': [('plan_id', '=', self.id)],
            'context': {'default_plan_id': self.id},
        }
    
    def action_create_product(self):
        """Acción para crear un producto asociado al plan."""
        self.ensure_one()
        
        if self.product_id:
            raise UserError(_('El plan ya tiene un producto asociado.'))
        
        # Crear producto
        product_vals = {
            'name': self.name,
            'type': 'service',
            'list_price': self.amount,
            'standard_price': 0.0,  # Servicio sin costo
            'description_sale': self.description,
            'sale_ok': True,
            'purchase_ok': False,
            'invoice_policy': 'order',
            'default_code': f'PLAN-{self.id}',
            'categ_id': self.env.ref('product.product_category_all').id,
        }
        
        product = self.env['product.product'].create(product_vals)
        self.product_id = product.id
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Producto Creado'),
                'message': _('Se ha creado el producto "%s" asociado al plan.') % product.name,
                'type': 'success',
            }
        }

    # ==========================================
    # MÉTODOS DE MODELO
    # ==========================================
    
    def write(self, vals):
        """Override write para mantener sincronización."""
        result = super().write(vals)
        
        # Marcar como no sincronizado si se modifican campos importantes
        sync_fields = ['name', 'description', 'amount']
        if any(field in vals for field in sync_fields):
            self.write({'is_synced': False})
        
        return result
    
    def unlink(self):
        """Override unlink para validaciones."""
        for plan in self:
            if plan.subscription_ids:
                raise UserError(_('No se puede eliminar un plan que tiene suscripciones.'))
        
        return super().unlink()
    
    @api.model
    def get_published_plans(self):
        """Obtiene los planes publicados para mostrar a los clientes."""
        return self.search([
            ('state', '=', 'active'),
            ('is_published', '=', True),
        ], order='sequence, amount')
    
    def get_next_billing_date(self, start_date=None):
        """Calcula la próxima fecha de facturación basada en el intervalo del plan."""
        self.ensure_one()
        
        if not start_date:
            start_date = fields.Date.today()
        
        if isinstance(start_date, str):
            start_date = fields.Date.from_string(start_date)
        
        if self.interval == 'days':
            return start_date + timedelta(days=self.interval_count)
        elif self.interval == 'weeks':
            return start_date + timedelta(weeks=self.interval_count)
        elif self.interval == 'months':
            return start_date + relativedelta(months=self.interval_count)
        elif self.interval == 'years':
            return start_date + relativedelta(years=self.interval_count)
        
        return start_date