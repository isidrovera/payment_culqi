# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import json
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CulqiCard(models.Model):
    _name = 'culqi.card'
    _description = 'Tarjeta Culqi'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # ==========================================
    # CAMPOS BÁSICOS
    # ==========================================
    
    name = fields.Char(
        string='Nombre de la Tarjeta',
        help='Nombre personalizado para identificar la tarjeta',
        tracking=True
    )
    
    display_name = fields.Char(
        string='Nombre para Mostrar',
        compute='_compute_display_name',
        store=True
    )
    
    # Identificadores
    culqi_card_id = fields.Char(
        string='ID de Tarjeta Culqi',
        readonly=True,
        tracking=True,
        help='ID único de la tarjeta en Culqi'
    )
    
    culqi_token_id = fields.Char(
        string='Token Original',
        readonly=True,
        help='ID del token usado para crear la tarjeta'
    )
    
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
    
    provider_id = fields.Many2one(
        'payment.provider',
        string='Proveedor de Pago',
        related='customer_id.provider_id',
        store=True,
        readonly=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='customer_id.company_id',
        store=True,
        readonly=True
    )
    
    # Información de la tarjeta (SIN datos sensibles)
    card_brand = fields.Selection([
        ('visa', 'Visa'),
        ('mastercard', 'Mastercard'),
        ('amex', 'American Express'),
        ('diners', 'Diners Club'),
        ('discover', 'Discover'),
        ('jcb', 'JCB'),
        ('maestro', 'Maestro'),
        ('other', 'Otra'),
    ], string='Marca', readonly=True, tracking=True)
    
    card_type = fields.Selection([
        ('credit', 'Crédito'),
        ('debit', 'Débito'),
        ('prepaid', 'Prepagada'),
        ('unknown', 'Desconocida'),
    ], string='Tipo', readonly=True, tracking=True)
    
    card_category = fields.Selection([
        ('classic', 'Clásica'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum'),
        ('black', 'Black'),
        ('signature', 'Signature'),
        ('infinite', 'Infinite'),
        ('business', 'Business'),
        ('corporate', 'Corporate'),
        ('other', 'Otra'),
    ], string='Categoría', readonly=True)
    
    last_four = fields.Char(
        string='Últimos 4 Dígitos',
        size=4,
        readonly=True,
        tracking=True
    )
    
    first_six = fields.Char(
        string='Primeros 6 Dígitos (BIN)',
        size=6,
        readonly=True,
        help='Bank Identification Number'
    )
    
    # Fechas de expiración
    expiry_month = fields.Selection([
        ('01', '01'), ('02', '02'), ('03', '03'), ('04', '04'),
        ('05', '05'), ('06', '06'), ('07', '07'), ('08', '08'),
        ('09', '09'), ('10', '10'), ('11', '11'), ('12', '12'),
    ], string='Mes de Expiración', readonly=True, tracking=True)
    
    expiry_year = fields.Char(
        string='Año de Expiración',
        size=4,
        readonly=True,
        tracking=True
    )
    
    is_expired = fields.Boolean(
        string='Expirada',
        compute='_compute_is_expired',
        store=True
    )
    
    # Estados
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('active', 'Activa'),
        ('inactive', 'Inactiva'),
        ('expired', 'Expirada'),
        ('blocked', 'Bloqueada'),
    ], string='Estado', default='draft', tracking=True)
    
    is_default = fields.Boolean(
        string='Tarjeta por Defecto',
        default=False,
        tracking=True,
        help='Tarjeta por defecto para pagos del cliente'
    )
    
    is_verified = fields.Boolean(
        string='Verificada',
        default=False,
        readonly=True,
        help='Indica si la tarjeta ha sido verificada por el banco'
    )
    
    # Información del banco emisor
    issuer_name = fields.Char(
        string='Banco Emisor',
        readonly=True
    )
    
    issuer_country = fields.Many2one(
        'res.country',
        string='País del Emisor',
        readonly=True
    )
    
    issuer_website = fields.Char(
        string='Sitio Web del Emisor',
        readonly=True
    )
    
    issuer_phone = fields.Char(
        string='Teléfono del Emisor',
        readonly=True
    )
    
    # Información de seguridad
    secure_verified = fields.Boolean(
        string='3D Secure Verificado',
        default=False,
        readonly=True
    )
    
    risk_score = fields.Integer(
        string='Puntaje de Riesgo',
        readonly=True,
        help='Puntaje de riesgo asignado por Culqi (0-100)'
    )
    
    # Metadatos y respuestas
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
    
    last_used_date = fields.Datetime(
        string='Última Vez Usada',
        readonly=True
    )
    
    # Relaciones
    transaction_ids = fields.One2many(
        'payment.transaction',
        'culqi_card_id',
        string='Transacciones',
        help='Transacciones realizadas con esta tarjeta'
    )
    
    subscription_ids = fields.One2many(
        'culqi.subscription',
        'card_id',
        string='Suscripciones',
        help='Suscripciones asociadas a esta tarjeta'
    )
    
    # Campos computados
    transaction_count = fields.Integer(
        string='Número de Transacciones',
        compute='_compute_counts'
    )
    
    subscription_count = fields.Integer(
        string='Número de Suscripciones',
        compute='_compute_counts'
    )
    
    total_spent = fields.Monetary(
        string='Total Gastado',
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
    
    @api.depends('name', 'card_brand', 'last_four')
    def _compute_display_name(self):
        """Computa el nombre para mostrar."""
        for card in self:
            if card.name:
                card.display_name = card.name
            elif card.card_brand and card.last_four:
                brand_name = dict(card._fields['card_brand'].selection).get(card.card_brand, card.card_brand)
                card.display_name = f"{brand_name} ****{card.last_four}"
            elif card.last_four:
                card.display_name = f"****{card.last_four}"
            else:
                card.display_name = 'Tarjeta sin identificar'
    
    @api.depends('expiry_month', 'expiry_year')
    def _compute_is_expired(self):
        """Computa si la tarjeta está expirada."""
        now = datetime.now()
        current_year = now.year
        current_month = now.month
        
        for card in self:
            if card.expiry_year and card.expiry_month:
                try:
                    exp_year = int(card.expiry_year)
                    exp_month = int(card.expiry_month)
                    
                    # La tarjeta expira al final del mes
                    card.is_expired = (exp_year < current_year) or (exp_year == current_year and exp_month < current_month)
                except ValueError:
                    card.is_expired = False
            else:
                card.is_expired = False
    
    @api.depends('transaction_ids', 'subscription_ids')
    def _compute_counts(self):
        """Computa los contadores de relaciones."""
        for card in self:
            card.transaction_count = len(card.transaction_ids)
            card.subscription_count = len(card.subscription_ids)
    
    @api.depends('transaction_ids.amount', 'transaction_ids.state')
    def _compute_amounts(self):
        """Computa los montos totales."""
        for card in self:
            paid_transactions = card.transaction_ids.filtered(
                lambda tx: tx.state == 'done'
            )
            card.total_spent = sum(paid_transactions.mapped('amount'))

    # ==========================================
    # VALIDACIONES Y CONSTRAINS
    # ==========================================
    
    @api.constrains('last_four')
    def _check_last_four(self):
        """Valida que los últimos 4 dígitos sean numéricos."""
        for card in self:
            if card.last_four and not card.last_four.isdigit():
                raise ValidationError(_('Los últimos 4 dígitos deben ser numéricos.'))
    
    @api.constrains('first_six')
    def _check_first_six(self):
        """Valida que los primeros 6 dígitos sean numéricos."""
        for card in self:
            if card.first_six and not card.first_six.isdigit():
                raise ValidationError(_('Los primeros 6 dígitos deben ser numéricos.'))
    
    @api.constrains('expiry_year')
    def _check_expiry_year(self):
        """Valida el año de expiración."""
        for card in self:
            if card.expiry_year:
                try:
                    year = int(card.expiry_year)
                    current_year = datetime.now().year
                    if year < current_year or year > current_year + 20:
                        raise ValidationError(_('El año de expiración debe estar entre %d y %d.') % (current_year, current_year + 20))
                except ValueError:
                    raise ValidationError(_('El año de expiración debe ser un número válido.'))
    
    @api.constrains('is_default', 'customer_id')
    def _check_single_default(self):
        """Asegura que solo haya una tarjeta por defecto por cliente."""
        for card in self:
            if card.is_default:
                other_defaults = self.search([
                    ('customer_id', '=', card.customer_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', card.id)
                ])
                if other_defaults:
                    raise ValidationError(_('Solo puede haber una tarjeta por defecto por cliente.'))

    # ==========================================
    # MÉTODOS DE CULQI API
    # ==========================================
    
    def _get_culqi_client(self):
        """Obtiene el cliente Culqi configurado."""
        self.ensure_one()
        return self.customer_id._get_culqi_client()
    
    def _prepare_culqi_card_data(self, token_id):
        """Prepara los datos para crear una tarjeta en Culqi."""
        self.ensure_one()
        
        card_data = {
            'customer_id': self.customer_id.culqi_customer_id,
            'token_id': token_id,
        }
        
        # Metadatos
        metadata = {
            'odoo_card_id': self.id,
            'odoo_partner_id': self.partner_id.id,
            'created_from': 'odoo',
            'name': self.name or '',
        }
        
        # Agregar metadatos personalizados si existen
        if self.culqi_metadata:
            try:
                custom_metadata = json.loads(self.culqi_metadata)
                metadata.update(custom_metadata)
            except json.JSONDecodeError:
                _logger.warning('Metadatos JSON inválidos para tarjeta %s', self.id)
        
        card_data['metadata'] = metadata
        
        return card_data
    
    def create_in_culqi(self, token_id):
        """Crea la tarjeta en Culqi usando un token."""
        self.ensure_one()
        
        if self.culqi_card_id:
            raise UserError(_('La tarjeta ya está creada en Culqi: %s') % self.culqi_card_id)
        
        if not self.customer_id.culqi_customer_id:
            raise UserError(_('El cliente debe estar creado en Culqi primero.'))
        
        try:
            client = self._get_culqi_client()
            card_data = self._prepare_culqi_card_data(token_id)
            
            _logger.info('Creando tarjeta en Culqi para cliente: %s', self.customer_id.culqi_customer_id)
            
            response = client.card.create(data=card_data)
            
            if response.get('object') == 'card':
                self._process_culqi_response(response)
                self.culqi_token_id = token_id
                self.state = 'active'
                
                self.message_post(
                    body=_('Tarjeta creada exitosamente en Culqi: %s') % response['id']
                )
                
                _logger.info('Tarjeta creada en Culqi: %s', response['id'])
                return response
            else:
                raise UserError(_('Error al crear tarjeta: %s') % response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al crear tarjeta en Culqi: %s', str(e))
            self.message_post(
                body=_('Error al crear tarjeta en Culqi: %s') % str(e)
            )
            raise UserError(_('Error al crear tarjeta en Culqi: %s') % str(e))
    
    def retrieve_from_culqi(self):
        """Obtiene la información de la tarjeta desde Culqi."""
        self.ensure_one()
        
        if not self.culqi_card_id:
            raise UserError(_('No hay ID de tarjeta en Culqi para sincronizar.'))
        
        try:
            client = self._get_culqi_client()
            
            _logger.info('Obteniendo tarjeta desde Culqi: %s', self.culqi_card_id)
            
            response = client.card.read(self.culqi_card_id)
            
            if response.get('object') == 'card':
                self._process_culqi_response(response)
                
                self.message_post(
                    body=_('Tarjeta sincronizada exitosamente desde Culqi')
                )
                
                _logger.info('Tarjeta sincronizada desde Culqi: %s', self.culqi_card_id)
                return response
            else:
                raise UserError(_('Error al obtener tarjeta: %s') % response.get('user_message', 'Tarjeta no encontrada'))
                
        except Exception as e:
            _logger.error('Error al obtener tarjeta desde Culqi: %s', str(e))
            self.message_post(
                body=_('Error al sincronizar tarjeta desde Culqi: %s') % str(e)
            )
            raise UserError(_('Error al sincronizar tarjeta desde Culqi: %s') % str(e))
    
    def delete_from_culqi(self):
        """Elimina la tarjeta de Culqi."""
        self.ensure_one()
        
        if not self.culqi_card_id:
            raise UserError(_('La tarjeta no está creada en Culqi.'))
        
        # Verificar que no tenga suscripciones activas
        active_subscriptions = self.subscription_ids.filtered(lambda s: s.state == 'active')
        if active_subscriptions:
            raise UserError(_('No se puede eliminar una tarjeta con suscripciones activas.'))
        
        try:
            client = self._get_culqi_client()
            
            _logger.info('Eliminando tarjeta de Culqi: %s', self.culqi_card_id)
            
            response = client.card.delete(self.culqi_card_id)
            
            if response.get('deleted'):
                self.state = 'inactive'
                self.message_post(
                    body=_('Tarjeta eliminada exitosamente de Culqi')
                )
                
                _logger.info('Tarjeta eliminada de Culqi: %s', self.culqi_card_id)
                return response
            else:
                raise UserError(_('Error al eliminar tarjeta: %s') % response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al eliminar tarjeta de Culqi: %s', str(e))
            self.message_post(
                body=_('Error al eliminar tarjeta de Culqi: %s') % str(e)
            )
            raise UserError(_('Error al eliminar tarjeta de Culqi: %s') % str(e))
    
    def _process_culqi_response(self, response):
        """Procesa la respuesta de Culqi y actualiza los campos."""
        self.ensure_one()
        
        # Actualizar ID si es necesario
        if response.get('id') and not self.culqi_card_id:
            self.culqi_card_id = response['id']
        
        # Información básica de la tarjeta
        if response.get('brand'):
            brand_mapping = {
                'Visa': 'visa',
                'Mastercard': 'mastercard',
                'American Express': 'amex',
                'Diners Club': 'diners',
                'Discover': 'discover',
                'JCB': 'jcb',
                'Maestro': 'maestro',
            }
            self.card_brand = brand_mapping.get(response['brand'], 'other')
        
        if response.get('type'):
            type_mapping = {
                'credito': 'credit',
                'debito': 'debit',
                'prepago': 'prepaid',
            }
            self.card_type = type_mapping.get(response['type'], 'unknown')
        
        if response.get('last_four'):
            self.last_four = response['last_four']
        
        if response.get('bin'):
            self.first_six = response['bin']
        
        # Fechas de expiración
        if response.get('expiry_month'):
            self.expiry_month = str(response['expiry_month']).zfill(2)
        
        if response.get('expiry_year'):
            self.expiry_year = str(response['expiry_year'])
        
        # Información del emisor
        if response.get('issuer'):
            issuer = response['issuer']
            self.issuer_name = issuer.get('name')
            self.issuer_website = issuer.get('website')
            self.issuer_phone = issuer.get('phone')
            
            if issuer.get('country_code'):
                country = self.env['res.country'].search([
                    ('code', '=', issuer['country_code'])
                ], limit=1)
                if country:
                    self.issuer_country = country
        
        # Fechas
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
    
    def action_sync_from_culqi(self):
        """Acción para sincronizar la tarjeta desde Culqi."""
        self.retrieve_from_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tarjeta Sincronizada'),
                'message': _('La tarjeta ha sido sincronizada exitosamente desde Culqi.'),
                'type': 'success',
            }
        }
    
    def action_set_as_default(self):
        """Acción para establecer como tarjeta por defecto."""
        self.ensure_one()
        
        # Quitar el default de otras tarjetas del mismo cliente
        other_cards = self.search([
            ('customer_id', '=', self.customer_id.id),
            ('id', '!=', self.id)
        ])
        other_cards.write({'is_default': False})
        
        # Establecer esta como default
        self.is_default = True
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tarjeta por Defecto'),
                'message': _('La tarjeta ha sido establecida como por defecto.'),
                'type': 'success',
            }
        }
    
    def action_deactivate(self):
        """Acción para desactivar la tarjeta."""
        self.ensure_one()
        
        # Verificar suscripciones activas
        active_subscriptions = self.subscription_ids.filtered(lambda s: s.state == 'active')
        if active_subscriptions:
            raise UserError(_('No se puede desactivar una tarjeta con suscripciones activas.'))
        
        self.state = 'inactive'
        self.is_default = False
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tarjeta Desactivada'),
                'message': _('La tarjeta ha sido desactivada exitosamente.'),
                'type': 'success',
            }
        }
    
    def action_delete_from_culqi(self):
        """Acción para eliminar la tarjeta de Culqi."""
        self.delete_from_culqi()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tarjeta Eliminada'),
                'message': _('La tarjeta ha sido eliminada exitosamente de Culqi.'),
                'type': 'success',
            }
        }
    
    def action_view_transactions(self):
        """Acción para ver las transacciones de la tarjeta."""
        self.ensure_one()
        return {
            'name': _('Transacciones de %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'view_mode': 'tree,form',
            'domain': [('culqi_card_id', '=', self.id)],
            'context': {'default_culqi_card_id': self.id},
        }
    
    def action_view_subscriptions(self):
        """Acción para ver las suscripciones de la tarjeta."""
        self.ensure_one()
        return {
            'name': _('Suscripciones de %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'culqi.subscription',
            'view_mode': 'tree,form',
            'domain': [('card_id', '=', self.id)],
            'context': {'default_card_id': self.id},
        }

    # ==========================================
    # MÉTODOS DE MODELO
    # ==========================================
    
    @api.model
    def create_from_token(self, customer_id, token_id, token_data=None):
        """Crea una tarjeta desde un token de Culqi."""
        customer = self.env['culqi.customer'].browse(customer_id)
        if not customer.exists():
            raise UserError(_('Cliente no encontrado.'))
        
        # Crear registro de tarjeta
        card_vals = {
            'customer_id': customer_id,
            'state': 'draft',
        }
        
        # Si tenemos datos del token, usarlos para prellenar
        if token_data:
            card_vals.update({
                'card_brand': token_data.get('brand', '').lower(),
                'card_type': token_data.get('type', '').lower(),
                'last_four': token_data.get('last_four', ''),
                'first_six': token_data.get('bin', ''),
            })
        
        card = self.create(card_vals)
        
        # Crear en Culqi
        card.create_in_culqi(token_id)
        
        return card
    
    def write(self, vals):
        """Override write para validaciones especiales."""
        # Si se marca como default, quitar default de otras
        if vals.get('is_default'):
            for card in self:
                other_cards = self.search([
                    ('customer_id', '=', card.customer_id.id),
                    ('id', '!=', card.id)
                ])
                other_cards.write({'is_default': False})
        
        return super().write(vals)
    
    def unlink(self):
        """Override unlink para validaciones."""
        for card in self:
            # Verificar suscripciones activas
            active_subscriptions = card.subscription_ids.filtered(lambda s: s.state == 'active')
            if active_subscriptions:
                raise UserError(_('No se puede eliminar una tarjeta con suscripciones activas.'))
            
            # Eliminar de Culqi si existe
            if card.culqi_card_id and card.state != 'inactive':
                try:
                    card.delete_from_culqi()
                except Exception as e:
                    _logger.warning('No se pudo eliminar tarjeta %s de Culqi: %s', card.culqi_card_id, str(e))
        
        return super().unlink()
    
    @api.model
    def cleanup_expired_cards(self):
        """Limpia tarjetas expiradas marcándolas como tal."""
        expired_cards = self.search([
            ('is_expired', '=', True),
            ('state', 'not in', ['expired', 'inactive'])
        ])
        
        for card in expired_cards:
            # Solo marcar como expiradas si no tienen suscripciones activas
            active_subscriptions = card.subscription_ids.filtered(lambda s: s.state == 'active')
            if not active_subscriptions:
                card.state = 'expired'
                card.is_default = False
        
        _logger.info('Marcadas %d tarjetas como expiradas', len(expired_cards))
        return len(expired_cards)