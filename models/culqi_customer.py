# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import json
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CulqiCustomer(models.Model):
    _name = 'culqi.customer'
    _description = 'Cliente Culqi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True
    )
    
    email = fields.Char(
        string='Email',
        required=True,
        tracking=True
    )
    
    phone = fields.Char(
        string='Teléfono',
        tracking=True
    )
    
    display_name = fields.Char(
        string='Nombre Completo',
        compute='_compute_display_name',
        store=True
    )
    
    # Identificadores
    culqi_customer_id = fields.Char(
        string='ID de Cliente Culqi',
        readonly=True,
        tracking=True,
        help='ID único del cliente en Culqi'
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto Odoo',
        required=True,
        ondelete='cascade',
        tracking=True,
        help='Contacto relacionado en Odoo'
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
    
    # Estados
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activo'),
        ('inactive', 'Inactivo'),
        ('blocked', 'Bloqueado'),
    ], string='Estado', default='draft', tracking=True)
    
    is_synced = fields.Boolean(
        string='Sincronizado',
        default=False,
        tracking=True,
        help='Indica si el cliente está sincronizado con Culqi'
    )
    
    # Información adicional
    address = fields.Char(
        string='Dirección',
        tracking=True
    )
    
    address_city = fields.Char(
        string='Ciudad',
        tracking=True
    )
    
    country_id = fields.Many2one(
        'res.country',
        string='País',
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
    card_ids = fields.One2many(
        'culqi.card',
        'customer_id',
        string='Tarjetas',
        help='Tarjetas asociadas al cliente'
    )
    
    transaction_ids = fields.One2many(
        'payment.transaction',
        'culqi_customer_id',
        string='Transacciones',
        help='Transacciones realizadas por el cliente'
    )
    
    subscription_ids = fields.One2many(
        'culqi.subscription',
        'customer_id',
        string='Suscripciones',
        help='Suscripciones activas del cliente'
    )
    
    # Campos computados
    card_count = fields.Integer(
        string='Número de Tarjetas',
        compute='_compute_counts'
    )
    
    transaction_count = fields.Integer(
        string='Número de Transacciones',
        compute='_compute_counts'
    )
    
    subscription_count = fields.Integer(
        string='Número de Suscripciones',
        compute='_compute_counts'
    )
    
    total_paid = fields.Monetary(
        string='Total Pagado',
        compute='_compute_amounts',
        currency_field='currency_id'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('name', 'email')
    def _compute_display_name(self):
        """Computa el nombre para mostrar."""
        for customer in self:
            if customer.name and customer.email:
                customer.display_name = f"{customer.name} ({customer.email})"
            elif customer.name:
                customer.display_name = customer.name
            elif customer.email:
                customer.display_name = customer.email
            else:
                customer.display_name = 'Cliente sin nombre'
    
    @api.depends('card_ids', 'transaction_ids', 'subscription_ids')
    def _compute_counts(self):
        """Computa los contadores de relaciones."""
        for customer in self:
            customer.card_count = len(customer.card_ids)
            customer.transaction_count = len(customer.transaction_ids)
            customer.subscription_count = len(customer.subscription_ids)
    
    @api.depends('transaction_ids.amount', 'transaction_ids.state')
    def _compute_amounts(self):
        """Computa los montos totales."""
        for customer in self:
            paid_transactions = customer.transaction_ids.filtered(
                lambda tx: tx.state == 'done'
            )
            customer.total_paid = sum(paid_transactions.mapped('amount'))

    # ==========================================
    # VALIDACIONES Y CONSTRAINS
    # ==========================================
    
    @api.constrains('email')
    def _check_email_format(self):
        """Valida el formato del email."""
        for customer in self:
            if customer.email and '@' not in customer.email:
                raise ValidationError(_('El email debe tener un formato válido.'))
    
    @api.constrains('partner_id', 'provider_id')
    def _check_unique_partner_provider(self):
        """Valida que un partner solo tenga un cliente por proveedor."""
        for customer in self:
            existing = self.search([
                ('partner_id', '=', customer.partner_id.id),
                ('provider_id', '=', customer.provider_id.id),
                ('id', '!=', customer.id)
            ])
            if existing:
                raise ValidationError(_(
                    'El contacto %s ya tiene un cliente asociado para el proveedor %s.'
                ) % (customer.partner_id.name, customer.provider_id.name))

    # ==========================================
    # MÉTODOS ONCHANGE
    # ==========================================
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Actualiza los campos cuando cambia el partner."""
        if self.partner_id:
            self.name = self.partner_id.name or ''
            self.email = self.partner_id.email or ''
            self.phone = self.partner_id.phone or self.partner_id.mobile or ''
            self.address = self.partner_id.street or ''
            self.address_city = self.partner_id.city or ''
            self.country_id = self.partner_id.country_id

    # ==========================================
    # MÉTODOS DE CULQI API
    # ==========================================
    
    def _get_culqi_client(self):
        """Obtiene el cliente Culqi configurado."""
        self.ensure_one()
        if not self.provider_id:
            raise UserError(_('No hay proveedor de pago configurado.'))
        return self.provider_id._get_culqi_client()
    
    def _prepare_culqi_customer_data(self):
        """Prepara los datos para enviar a Culqi."""
        self.ensure_one()
        
        # Datos básicos requeridos
        customer_data = {
            'first_name': self.name.split(' ')[0] if self.name else '',
            'last_name': ' '.join(self.name.split(' ')[1:]) if self.name and ' ' in self.name else '',
            'email': self.email,
        }
        
        # Datos opcionales
        if self.phone:
            customer_data['phone_number'] = self.phone
        
        if self.address:
            customer_data['address'] = self.address
        
        if self.address_city:
            customer_data['address_city'] = self.address_city
        
        if self.country_id:
            customer_data['country_code'] = self.country_id.code
        
        # Metadatos
        metadata = {
            'odoo_partner_id': self.partner_id.id,
            'odoo_customer_id': self.id,
            'created_from': 'odoo',
            'company_name': self.company_id.name,
        }
        
        # Agregar metadatos personalizados si existen
        if self.culqi_metadata:
            try:
                custom_metadata = json.loads(self.culqi_metadata)
                metadata.update(custom_metadata)
            except json.JSONDecodeError:
                _logger.warning('Metadatos JSON inválidos para cliente %s', self.id)
        
        customer_data['metadata'] = metadata
        
        return customer_data
    
    def create_in_culqi(self):
        """Crea el cliente en Culqi."""
        self.ensure_one()
        
        if self.culqi_customer_id:
            raise UserError(_('El cliente ya está creado en Culqi: %s') % self.culqi_customer_id)
        
        try:
            client = self._get_culqi_client()
            customer_data = self._prepare_culqi_customer_data()
            
            _logger.info('Creando cliente en Culqi: %s', self.email)
            
            response = client.customer.create(data=customer_data)
            
            if response.get('object') == 'customer':
                self._process_culqi_response(response)
                self.state = 'active'
                self.is_synced = True
                self.last_sync_date = fields.Datetime.now()
                
                self.message_post(
                    body=_('Cliente creado exitosamente en Culqi: %s') % response['id']
                )
                
                _logger.info('Cliente creado en Culqi: %s', response['id'])
                return response
            else:
                raise UserError(_('Error al crear cliente: %s') % response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al crear cliente en Culqi: %s', str(e))
            self.message_post(
                body=_('Error al crear cliente en Culqi: %s') % str(e)
            )
            raise UserError(_('Error al crear cliente en Culqi: %s') % str(e))
    
    def update_in_culqi(self):
        """Actualiza el cliente en Culqi."""
        self.ensure_one()
        
        if not self.culqi_customer_id:
            raise UserError(_('El cliente no está creado en Culqi. Use "Crear en Culqi" primero.'))
        
        try:
            client = self._get_culqi_client()
            customer_data = self._prepare_culqi_customer_data()
            
            _logger.info('Actualizando cliente en Culqi: %s', self.culqi_customer_id)
            
            response = client.customer.update(id_=self.culqi_customer_id, data=customer_data)
            
            if response.get('object') == 'customer':
                self._process_culqi_response(response)
                self.is_synced = True
                self.last_sync_date = fields.Datetime.now()
                
                self.message_post(
                    body=_('Cliente actualizado exitosamente en Culqi')
                )
                
                _logger.info('Cliente actualizado en Culqi: %s', self.culqi_customer_id)
                return response
            else:
                raise UserError(_('Error al actualizar cliente: %s') % response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al actualizar cliente en Culqi: %s', str(e))
            self.message_post(
                body=_('Error al actualizar cliente en Culqi: %s') % str(e)
            )
            raise UserError(_('Error al actualizar cliente en Culqi: %s') % str(e))
    
    def retrieve_from_culqi(self):
        """Obtiene la información del cliente desde Culqi."""
        self.ensure_one()
        
        if not self.culqi_customer_id:
            raise UserError(_('No hay ID de cliente en Culqi para sincronizar.'))
        
        try:
            client = self._get_culqi_client()
            
            _logger.info('Obteniendo cliente desde Culqi: %s', self.culqi_customer_id)
            
            response = client.customer.read(self.culqi_customer_id)
            
            if response.get('object') == 'customer':
                self._process_culqi_response(response)
                self.is_synced = True
                self.last_sync_date = fields.Datetime.now()
                
                self.message_post(
                    body=_('Cliente sincronizado exitosamente desde Culqi')
                )
                
                _logger.info('Cliente sincronizado desde Culqi: %s', self.culqi_customer_id)
                return response
            else:
                raise UserError(_('Error al obtener cliente: %s') % response.get('user_message', 'Cliente no encontrado'))
                
        except Exception as e:
            _logger.error('Error al obtener cliente desde Culqi: %s', str(e))
            self.message_post(
                body=_('Error al sincronizar cliente desde Culqi: %s') % str(e)
            )
            raise UserError(_('Error al sincronizar cliente desde Culqi: %s') % str(e))
    
    def _process_culqi_response(self, response):
        """Procesa la respuesta de Culqi y actualiza los campos."""
        self.ensure_one()
        
        # Actualizar ID si es necesario
        if response.get('id') and not self.culqi_customer_id:
            self.culqi_customer_id = response['id']
        
        # Actualizar fechas
        if response.get('creation_date'):
            try:
                # Culqi devuelve timestamp en segundos
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
        """Acción para crear el cliente en Culqi."""
        self.create_in_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cliente Creado'),
                'message': _('El cliente ha sido creado exitosamente en Culqi.'),
                'type': 'success',
            }
        }
    
    def action_update_in_culqi(self):
        """Acción para actualizar el cliente en Culqi."""
        self.update_in_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cliente Actualizado'),
                'message': _('El cliente ha sido actualizado exitosamente en Culqi.'),
                'type': 'success',
            }
        }
    
    def action_sync_from_culqi(self):
        """Acción para sincronizar el cliente desde Culqi."""
        self.retrieve_from_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cliente Sincronizado'),
                'message': _('El cliente ha sido sincronizado exitosamente desde Culqi.'),
                'type': 'success',
            }
        }
    
    def action_view_cards(self):
        """Acción para ver las tarjetas del cliente."""
        self.ensure_one()
        return {
            'name': _('Tarjetas de %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.card',
            'view_mode': 'tree,form',
            'domain': [('customer_id', '=', self.id)],
            'context': {'default_customer_id': self.id},
        }
    
    def action_view_transactions(self):
        """Acción para ver las transacciones del cliente."""
        self.ensure_one()
        return {
            'name': _('Transacciones de %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'view_mode': 'tree,form',
            'domain': [('culqi_customer_id', '=', self.id)],
            'context': {'default_culqi_customer_id': self.id},
        }
    
    def action_view_subscriptions(self):
        """Acción para ver las suscripciones del cliente."""
        self.ensure_one()
        return {
            'name': _('Suscripciones de %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.subscription',
            'view_mode': 'tree,form',
            'domain': [('customer_id', '=', self.id)],
            'context': {'default_customer_id': self.id},
        }

    # ==========================================
    # MÉTODOS DE MODELO
    # ==========================================
    
    @api.model
    def create(self, vals):
        """Override create para sincronización automática opcional."""
        customer = super().create(vals)
        
        # Auto-sincronizar si está configurado en el proveedor
        if customer.provider_id and hasattr(customer.provider_id, 'culqi_auto_sync_customers'):
            if customer.provider_id.culqi_auto_sync_customers:
                try:
                    customer.create_in_culqi()
                except Exception as e:
                    _logger.warning('No se pudo auto-sincronizar cliente %s: %s', customer.id, str(e))
        
        return customer
    
    def write(self, vals):
        """Override write para mantener sincronización."""
        result = super().write(vals)
        
        # Marcar como no sincronizado si se modifican campos importantes
        sync_fields = ['name', 'email', 'phone', 'address', 'address_city', 'country_id']
        if any(field in vals for field in sync_fields):
            self.write({'is_synced': False})
        
        return result
    
    def unlink(self):
        """Override unlink para validaciones."""
        for customer in self:
            if customer.culqi_customer_id and customer.subscription_ids.filtered(lambda s: s.state == 'active'):
                raise UserError(_('No se puede eliminar un cliente con suscripciones activas en Culqi.'))
        
        return super().unlink()
    
    @api.model
    def sync_all_customers(self):
        """Sincroniza todos los clientes no sincronizados."""
        customers_to_sync = self.search([
            ('is_synced', '=', False),
            ('culqi_customer_id', '!=', False),
            ('state', '=', 'active')
        ])
        
        synced_count = 0
        for customer in customers_to_sync:
            try:
                customer.retrieve_from_culqi()
                synced_count += 1
            except Exception as e:
                _logger.error('Error al sincronizar cliente %s: %s', customer.id, str(e))
        
        _logger.info('Sincronizados %d de %d clientes', synced_count, len(customers_to_sync))
        return synced_count