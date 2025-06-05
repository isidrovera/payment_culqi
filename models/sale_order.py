# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import json
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """Extensión del modelo sale.order para integrar con Culqi."""
    _inherit = 'sale.order'

    # ==========================================
    # CAMPOS ESPECÍFICOS DE CULQI
    # ==========================================
    
    # Información de pago Culqi
    culqi_payment_method = fields.Selection([
        ('card', 'Tarjeta de Crédito/Débito'),
        ('pagoefectivo', 'PagoEfectivo'),
        ('yape', 'Yape'),
        ('billetera', 'Billetera Digital'),
    ], string='Método de Pago Culqi', help='Método de pago seleccionado en Culqi')
    
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
    
    # Estado de pago específico de Culqi
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
    
    # Configuración de pagos
    culqi_enable_online_payment = fields.Boolean(
        string='Habilitar Pago Online',
        default=True,
        help='Permite que esta orden sea pagada online con Culqi'
    )
    
    culqi_payment_url = fields.Char(
        string='URL de Pago',
        compute='_compute_culqi_payment_url',
        help='URL para pagar esta orden online'
    )
    
    # Configuración de suscripciones
    culqi_has_subscription_products = fields.Boolean(
        string='Tiene Productos de Suscripción',
        compute='_compute_subscription_info',
        store=True,
        help='Indica si la orden contiene productos de suscripción'
    )
    
    culqi_subscription_ids = fields.One2many(
        'culqi.subscription',
        compute='_compute_subscription_info',
        string='Suscripciones Generadas',
        help='Suscripciones creadas a partir de esta orden'
    )
    
    culqi_subscription_count = fields.Integer(
        string='Número de Suscripciones',
        compute='_compute_subscription_info'
    )
    
    # Información del cliente Culqi
    culqi_customer_id = fields.Many2one(
        'culqi.customer',
        string='Cliente Culqi',
        compute='_compute_culqi_customer',
        store=True,
        help='Cliente Culqi asociado'
    )
    
    # Configuración de entrega
    culqi_requires_shipping = fields.Boolean(
        string='Requiere Envío',
        compute='_compute_shipping_info',
        help='Indica si la orden requiere información de envío'
    )
    
    # Campos de seguimiento
    culqi_payment_deadline = fields.Datetime(
        string='Fecha Límite de Pago',
        compute='_compute_culqi_payment_deadline',
        store=True,
        help='Fecha límite para completar el pago'
    )
    
    # Configuración de carrello abandonado
    culqi_cart_abandoned = fields.Boolean(
        string='Carrito Abandonado',
        default=False,
        help='Indica si este carrito fue abandonado'
    )
    
    culqi_cart_reminder_sent = fields.Boolean(
        string='Recordatorio Enviado',
        default=False,
        help='Indica si se envió recordatorio de carrito abandonado'
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('transaction_ids')
    def _compute_culqi_transaction(self):
        """Computa la transacción Culqi asociada."""
        for order in self:
            culqi_tx = order.transaction_ids.filtered(
                lambda tx: tx.provider_code == 'culqi' and tx.state in ['done', 'authorized']
            )
            order.culqi_transaction_id = culqi_tx[0] if culqi_tx else False
    
    @api.depends('culqi_transaction_id.state', 'culqi_transaction_id.culqi_refunded_amount')
    def _compute_culqi_payment_state(self):
        """Computa el estado de pago específico de Culqi."""
        for order in self:
            if not order.culqi_transaction_id:
                order.culqi_payment_state = 'not_applicable'
                continue
            
            tx = order.culqi_transaction_id
            
            # Verificar reembolsos
            refunded_amount = tx.culqi_refunded_amount or 0
            
            if refunded_amount > 0:
                if float_compare(refunded_amount, order.amount_total, precision_digits=2) >= 0:
                    order.culqi_payment_state = 'refunded'
                else:
                    order.culqi_payment_state = 'partially_refunded'
            elif tx.state == 'done':
                order.culqi_payment_state = 'paid'
            elif tx.state == 'authorized':
                order.culqi_payment_state = 'processing'
            elif tx.state == 'pending':
                order.culqi_payment_state = 'pending'
            elif tx.state in ['error', 'cancel']:
                order.culqi_payment_state = 'failed'
            else:
                order.culqi_payment_state = 'pending'
    
    @api.depends('partner_id')
    def _compute_culqi_customer(self):
        """Computa el cliente Culqi asociado."""
        for order in self:
            if order.partner_id:
                customer = self.env['culqi.customer'].search([
                    ('partner_id', '=', order.partner_id.id)
                ], limit=1)
                order.culqi_customer_id = customer
            else:
                order.culqi_customer_id = False
    
    @api.depends('order_line.product_id')
    def _compute_subscription_info(self):
        """Computa información de suscripciones."""
        for order in self:
            # Verificar si tiene productos de suscripción
            subscription_lines = order.order_line.filtered(
                lambda line: line.product_id.culqi_is_subscription_product
            )
            order.culqi_has_subscription_products = bool(subscription_lines)
            
            # Buscar suscripciones creadas desde esta orden
            subscriptions = self.env['culqi.subscription'].search([
                ('partner_id', '=', order.partner_id.id),
                ('plan_id.product_id', 'in', order.order_line.product_id.ids)
            ])
            order.culqi_subscription_ids = subscriptions
            order.culqi_subscription_count = len(subscriptions)
    
    @api.depends('order_line.product_id.type')
    def _compute_shipping_info(self):
        """Computa información de envío."""
        for order in self:
            # Requiere envío si tiene productos físicos
            physical_products = order.order_line.filtered(
                lambda line: line.product_id.type in ['product', 'consu']
            )
            order.culqi_requires_shipping = bool(physical_products)
    
    @api.depends('name', 'access_token', 'state')
    def _compute_culqi_payment_url(self):
        """Computa la URL de pago online."""
        for order in self:
            if (order.state in ['draft', 'sent'] and 
                order.culqi_enable_online_payment and
                order.amount_total > 0):
                
                base_url = order.get_base_url()
                order.culqi_payment_url = f"{base_url}/shop/payment?order_id={order.id}"
            else:
                order.culqi_payment_url = False
    
    @api.depends('date_order')
    def _compute_culqi_payment_deadline(self):
        """Computa la fecha límite de pago."""
        for order in self:
            if order.state in ['draft', 'sent']:
                # 24 horas para completar el pago desde la creación
                order.culqi_payment_deadline = order.date_order + timedelta(hours=24)
            else:
                order.culqi_payment_deadline = False

    # ==========================================
    # VALIDACIONES Y CONSTRAINS
    # ==========================================
    
    @api.constrains('culqi_has_subscription_products', 'order_line')
    def _check_subscription_product_mix(self):
        """Valida que no se mezclen productos de suscripción con productos normales."""
        for order in self:
            if order.culqi_has_subscription_products:
                subscription_lines = order.order_line.filtered(
                    lambda line: line.product_id.culqi_is_subscription_product
                )
                normal_lines = order.order_line.filtered(
                    lambda line: not line.product_id.culqi_is_subscription_product
                )
                
                # Permitir mezcla solo si los productos normales son gratuitos (setup fees, etc.)
                if subscription_lines and normal_lines:
                    paid_normal_lines = normal_lines.filtered(lambda line: line.price_total > 0)
                    if paid_normal_lines:
                        raise ValidationError(_(
                            'No se pueden mezclar productos de suscripción con productos regulares de pago en la misma orden. '
                            'Cree órdenes separadas.'
                        ))

    # ==========================================
    # MÉTODOS DE PAGO CULQI
    # ==========================================
    
    def action_pay_with_culqi(self):
        """Acción para pagar la orden con Culqi."""
        self.ensure_one()
        
        if self.state not in ['draft', 'sent']:
            raise UserError(_('Solo se pueden pagar órdenes en borrador o enviadas.'))
        
        if self.amount_total <= 0:
            raise UserError(_('No se puede pagar una orden sin monto.'))
        
        # Confirmar la orden si está en borrador
        if self.state == 'draft':
            self.action_confirm()
        
        # Obtener proveedor Culqi
        provider = self.env['payment.provider'].search([
            ('code', '=', 'culqi'),
            ('state', 'in', ['enabled', 'test'])
        ], limit=1)
        
        if not provider:
            raise UserError(_('El proveedor de pago Culqi no está disponible.'))
        
        # Crear transacción de pago
        transaction = self._create_culqi_payment_transaction(provider)
        
        # Redireccionar al checkout de Culqi
        return {
            'type': 'ir.actions.act_url',
            'url': f'/shop/payment/culqi?order_id={self.id}&tx_ref={transaction.reference}',
            'target': 'self',
        }
    
    def _create_culqi_payment_transaction(self, provider):
        """Crea una transacción de pago Culqi para la orden."""
        self.ensure_one()
        
        transaction_vals = {
            'reference': f"SO-{self.name}-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}",
            'amount': self.amount_total,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'provider_id': provider.id,
            'sale_order_ids': [(4, self.id)],
            'operation': 'online_direct',
        }
        
        # Agregar metadatos específicos
        metadata = {
            'order_id': self.id,
            'order_name': self.name,
            'customer_email': self.partner_id.email,
            'requires_shipping': self.culqi_requires_shipping,
            'has_subscriptions': self.culqi_has_subscription_products,
            'order_lines': [
                {
                    'product_name': line.product_id.name,
                    'quantity': line.product_uom_qty,
                    'price_unit': line.price_unit,
                } for line in self.order_line
            ]
        }
        
        transaction_vals['culqi_metadata'] = json.dumps(metadata)
        
        return self.env['payment.transaction'].create(transaction_vals)
    
    def action_create_subscriptions(self):
        """Crea suscripciones a partir de productos de suscripción en la orden."""
        self.ensure_one()
        
        if not self.culqi_has_subscription_products:
            raise UserError(_('Esta orden no contiene productos de suscripción.'))
        
        if self.state not in ['sale', 'done']:
            raise UserError(_('La orden debe estar confirmada para crear suscripciones.'))
        
        if not self.culqi_transaction_id or self.culqi_transaction_id.state != 'done':
            raise UserError(_('La orden debe estar pagada para crear suscripciones.'))
        
        # Obtener o crear cliente Culqi
        customer = self._get_or_create_culqi_customer()
        
        # Obtener o crear tarjeta desde la transacción
        card = self._get_or_create_culqi_card(customer)
        
        created_subscriptions = self.env['culqi.subscription']
        
        # Crear suscripción para cada línea de producto de suscripción
        subscription_lines = self.order_line.filtered(
            lambda line: line.product_id.culqi_is_subscription_product
        )
        
        for line in subscription_lines:
            # Buscar plan asociado al producto
            plan = self.env['culqi.plan'].search([
                ('product_id', '=', line.product_id.id)
            ], limit=1)
            
            if not plan:
                # Crear plan automáticamente si no existe
                plan = self._create_plan_from_product(line.product_id)
            
            # Crear suscripción
            subscription_vals = {
                'customer_id': customer.id,
                'plan_id': plan.id,
                'card_id': card.id,
                'quantity': int(line.product_uom_qty),
                'start_date': fields.Date.today(),
            }
            
            subscription = self.env['culqi.subscription'].create(subscription_vals)
            subscription.create_in_culqi()
            
            created_subscriptions |= subscription
        
        # Mensaje de confirmación
        self.message_post(
            body=_('Se crearon %d suscripciones a partir de esta orden') % len(created_subscriptions)
        )
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Suscripciones Creadas'),
            'res_model': 'culqi.subscription',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_subscriptions.ids)],
        }
    
    def _get_or_create_culqi_customer(self):
        """Obtiene o crea un cliente Culqi."""
        self.ensure_one()
        
        customer = self.culqi_customer_id
        
        if not customer:
            # Obtener proveedor Culqi
            provider = self.env['payment.provider'].search([
                ('code', '=', 'culqi'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if not provider:
                raise UserError(_('Proveedor Culqi no configurado.'))
            
            # Crear cliente
            customer = self.env['culqi.customer'].create({
                'partner_id': self.partner_id.id,
                'provider_id': provider.id,
                'name': self.partner_id.name,
                'email': self.partner_id.email,
            })
            
            customer.create_in_culqi()
        
        return customer
    
    def _get_or_create_culqi_card(self, customer):
        """Obtiene o crea una tarjeta Culqi desde la transacción."""
        self.ensure_one()
        
        if not self.culqi_transaction_id or not self.culqi_transaction_id.culqi_token_id:
            raise UserError(_('No hay información de tarjeta disponible en la transacción.'))
        
        # Buscar si ya existe una tarjeta con este token
        existing_card = customer.card_ids.filtered(
            lambda card: card.culqi_token_id == self.culqi_transaction_id.culqi_token_id
        )
        
        if existing_card:
            return existing_card[0]
        
        # Crear nueva tarjeta
        card = self.env['culqi.card'].create({
            'customer_id': customer.id,
            'name': f'Tarjeta desde orden {self.name}',
        })
        
        card.create_in_culqi(self.culqi_transaction_id.culqi_token_id)
        
        return card
    
    def _create_plan_from_product(self, product):
        """Crea un plan Culqi a partir de un producto."""
        # Obtener proveedor Culqi
        provider = self.env['payment.provider'].search([
            ('code', '=', 'culqi'),
            ('state', 'in', ['enabled', 'test'])
        ], limit=1)
        
        if not provider:
            raise UserError(_('Proveedor Culqi no configurado.'))
        
        # Configuración por defecto para el plan
        plan_vals = {
            'name': product.name,
            'description': product.description_sale or product.description,
            'amount': product.list_price,
            'currency_id': self.currency_id.id,
            'provider_id': provider.id,
            'product_id': product.id,
            'interval': 'months',  # Por defecto mensual
            'interval_count': 1,
            'trial_period_days': 0,
        }
        
        plan = self.env['culqi.plan'].create(plan_vals)
        plan.create_in_culqi()
        
        return plan

    # ==========================================
    # MÉTODOS DE CARRITO ABANDONADO
    # ==========================================
    
    def action_mark_cart_abandoned(self):
        """Marca el carrito como abandonado."""
        self.ensure_one()
        
        if self.state not in ['draft', 'sent']:
            return
        
        self.culqi_cart_abandoned = True
        
        # Programar envío de recordatorio
        self.with_delay(eta=timedelta(hours=1)).action_send_cart_reminder()
    
    def action_send_cart_reminder(self):
        """Envía recordatorio de carrito abandonado."""
        self.ensure_one()
        
        if (self.culqi_cart_abandoned and 
            not self.culqi_cart_reminder_sent and 
            self.state in ['draft', 'sent']):
            
            template = self.env.ref(
                'payment_culqi.cart_abandonment_email_template',
                raise_if_not_found=False
            )
            
            if template and self.partner_id.email:
                template.send_mail(self.id, force_send=True)
                self.culqi_cart_reminder_sent = True
                
                self.message_post(
                    body=_('Recordatorio de carrito abandonado enviado a %s') % self.partner_id.email
                )
    
    @api.model
    def _cron_process_abandoned_carts(self):
        """Procesa carritos abandonados automáticamente."""
        # Buscar órdenes en draft/sent sin actividad en las últimas 2 horas
        cutoff_time = fields.Datetime.now() - timedelta(hours=2)
        
        abandoned_orders = self.search([
            ('state', 'in', ['draft', 'sent']),
            ('write_date', '<', cutoff_time),
            ('culqi_cart_abandoned', '=', False),
            ('amount_total', '>', 0),
        ])
        
        for order in abandoned_orders:
            order.action_mark_cart_abandoned()
        
        _logger.info('Procesados %d carritos abandonados', len(abandoned_orders))
        return len(abandoned_orders)

    # ==========================================
    # MÉTODOS DE REPORTES
    # ==========================================
    
    def _get_culqi_order_summary(self):
        """Obtiene resumen de la orden para reportes."""
        self.ensure_one()
        
        summary = {
            'order_number': self.name,
            'partner_name': self.partner_id.name,
            'amount_total': self.amount_total,
            'state': self.state,
            'culqi_payment_state': self.culqi_payment_state,
            'payment_method': self.culqi_payment_method,
            'transaction_reference': self.culqi_transaction_id.reference if self.culqi_transaction_id else None,
            'charge_id': self.culqi_charge_id,
            'has_subscriptions': self.culqi_has_subscription_products,
            'subscription_count': self.culqi_subscription_count,
            'requires_shipping': self.culqi_requires_shipping,
            'cart_abandoned': self.culqi_cart_abandoned,
        }
        
        return summary
    
    @api.model
    def get_culqi_sales_report(self, date_from, date_to):
        """Genera reporte de ventas por Culqi."""
        domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to),
            ('culqi_transaction_id', '!=', False),
        ]
        
        orders = self.search(domain)
        
        # Estadísticas generales
        total_orders = len(orders)
        total_revenue = sum(orders.mapped('amount_total'))
        subscription_orders = orders.filtered('culqi_has_subscription_products')
        
        # Agrupar por método de pago
        payment_methods = {}
        for order in orders:
            method = order.culqi_payment_method or 'unknown'
            
            if method not in payment_methods:
                payment_methods[method] = {
                    'count': 0,
                    'revenue': 0,
                }
            
            payment_methods[method]['count'] += 1
            payment_methods[method]['revenue'] += order.amount_total
        
        # Análisis de carritos abandonados
        abandoned_carts = self.search([
            ('state', 'in', ['draft', 'sent']),
            ('create_date', '>=', date_from),
            ('create_date', '<=', date_to),
            ('culqi_cart_abandoned', '=', True),
        ])
        
        return {
            'period': {'from': date_from, 'to': date_to},
            'summary': {
                'total_orders': total_orders,
                'total_revenue': total_revenue,
                'subscription_orders': len(subscription_orders),
                'subscription_revenue': sum(subscription_orders.mapped('amount_total')),
                'abandoned_carts': len(abandoned_carts),
                'abandonment_rate': len(abandoned_carts) / (total_orders + len(abandoned_carts)) * 100 if (total_orders + len(abandoned_carts)) > 0 else 0,
            },
            'by_payment_method': payment_methods,
        }

    # ==========================================
    # MÉTODOS OVERRIDE
    # ==========================================
    
    def action_confirm(self):
        """Override para procesar órdenes con productos de suscripción."""
        result = super().action_confirm()
        
        # Procesar órdenes con productos de suscripción
        subscription_orders = self.filtered('culqi_has_subscription_products')
        
        for order in subscription_orders:
            # Marcar que requiere configuración de suscripción
            order.message_post(
                body=_('Esta orden contiene productos de suscripción. '
                      'Las suscripciones se crearán automáticamente después del pago.')
            )
        
        return result
    
    def _action_confirm(self):
        """Override interno para validaciones adicionales."""
        # Validar productos de suscripción
        for order in self:
            if order.culqi_has_subscription_products:
                subscription_lines = order.order_line.filtered(
                    lambda line: line.product_id.culqi_is_subscription_product
                )
                
                for line in subscription_lines:
                    if line.product_uom_qty != int(line.product_uom_qty):
                        raise ValidationError(_(
                            'Los productos de suscripción solo pueden venderse en cantidades enteras. '
                            'Producto: %s'
                        ) % line.product_id.name)
        
        return super()._action_confirm()
    
    def action_cancel(self):
        """Override para manejar cancelación de órdenes con suscripciones."""
        # Verificar suscripciones activas
        for order in self:
            active_subscriptions = order.culqi_subscription_ids.filtered(
                lambda s: s.state == 'active'
            )
            
            if active_subscriptions:
                raise UserError(_(
                    'No se puede cancelar una orden que tiene suscripciones activas. '
                    'Cancele primero las suscripciones: %s'
                ) % ', '.join(active_subscriptions.mapped('reference')))
        
        return super().action_cancel()
    
    def _get_portal_return_action(self):
        """Override para redireccionar según el tipo de orden."""
        result = super()._get_portal_return_action()
        
        # Si la orden tiene suscripciones, redireccionar al portal de suscripciones
        if self.culqi_has_subscription_products and self.culqi_subscription_count > 0:
            result = {
                'type': 'ir.actions.act_url',
                'url': '/my/subscriptions',
                'target': 'self',
            }
        
        return result

    # ==========================================
    # MÉTODOS DE AUTOMATIZACIÓN
    # ==========================================
    
    @api.model
    def _cron_expire_unpaid_orders(self):
        """Expira órdenes sin pagar después del deadline."""
        expired_orders = self.search([
            ('state', 'in', ['draft', 'sent']),
            ('culqi_payment_deadline', '<', fields.Datetime.now()),
            ('culqi_enable_online_payment', '=', True),
        ])
        
        for order in expired_orders:
            order.action_cancel()
            order.message_post(
                body=_('Orden cancelada automáticamente por vencimiento del plazo de pago')
            )
        
        _logger.info('Expiradas %d órdenes sin pagar', len(expired_orders))
        return len(expired_orders)
    
    @api.model
    def _cron_create_pending_subscriptions(self):
        """Crea suscripciones pendientes de órdenes pagadas."""
        paid_orders = self.search([
            ('state', 'in', ['sale', 'done']),
            ('culqi_has_subscription_products', '=', True),
            ('culqi_payment_state', '=', 'paid'),
            ('culqi_subscription_count', '=', 0),  # Sin suscripciones creadas
        ])
        
        created_count = 0
        for order in paid_orders:
            try:
                order.action_create_subscriptions()
                created_count += 1
            except Exception as e:
                _logger.error('Error creando suscripciones para orden %s: %s', order.name, str(e))
        
        _logger.info('Creadas suscripciones para %d órdenes', created_count)
        return created_count


class SaleOrderLine(models.Model):
    """Extensión de líneas de orden para productos de suscripción."""
    _inherit = 'sale.order.line'

    # ==========================================
    # CAMPOS ESPECÍFICOS DE CULQI
    # ==========================================
    
    culqi_is_subscription_line = fields.Boolean(
        string='Línea de Suscripción',
        compute='_compute_subscription_info',
        store=True,
        help='Indica si esta línea contiene un producto de suscripción'
    )
    
    culqi_plan_id = fields.Many2one(
        'culqi.plan',
        string='Plan de Suscripción',
        compute='_compute_subscription_info',
        store=True,
        help='Plan de suscripción asociado al producto'
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('product_id')
    def _compute_subscription_info(self):
        """Computa información de suscripción."""
        for line in self:
            if line.product_id and hasattr(line.product_id, 'culqi_is_subscription_product'):
                line.culqi_is_subscription_line = line.product_id.culqi_is_subscription_product
                
                # Buscar plan asociado
                if line.culqi_is_subscription_line:
                    plan = self.env['culqi.plan'].search([
                        ('product_id', '=', line.product_id.id)
                    ], limit=1)
                    line.culqi_plan_id = plan