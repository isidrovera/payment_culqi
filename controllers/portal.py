# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import json
import logging
from datetime import datetime, timedelta

from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError, AccessError
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.addons.portal.controllers.mail import _message_post_helper
from odoo.tools import consteq

_logger = logging.getLogger(__name__)


class CulqiPortalController(CustomerPortal):
    """Controlador del portal del cliente para funcionalidades de Culqi."""

    def _prepare_home_portal_values(self, counters):
        """Agrega contadores de Culqi al portal home."""
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        
        if 'subscription_count' in counters:
            subscription_count = request.env['culqi.subscription'].search_count([
                ('partner_id', '=', partner.id)
            ])
            values['subscription_count'] = subscription_count
        
        if 'payment_method_count' in counters:
            customer = request.env['culqi.customer'].search([
                ('partner_id', '=', partner.id)
            ], limit=1)
            payment_method_count = len(customer.card_ids) if customer else 0
            values['payment_method_count'] = payment_method_count
        
        return values

    def _prepare_portal_layout_values(self):
        """Prepara valores para el layout del portal."""
        values = super()._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Agregar información de Culqi al layout
        customer = request.env['culqi.customer'].search([
            ('partner_id', '=', partner.id)
        ], limit=1)
        
        values.update({
            'culqi_customer': customer,
            'has_active_subscriptions': bool(
                request.env['culqi.subscription'].search_count([
                    ('partner_id', '=', partner.id),
                    ('state', '=', 'active')
                ])
            )
        })
        
        return values

    # ==========================================
    # GESTIÓN DE MÉTODOS DE PAGO
    # ==========================================

    @http.route(['/my/payment_methods', '/my/payment_methods/page/<int:page>'], 
                type='http', auth="user", website=True)
    def portal_my_payment_methods(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        """Página de métodos de pago del cliente."""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Obtener o crear cliente Culqi
        customer = request.env['culqi.customer'].search([
            ('partner_id', '=', partner.id)
        ], limit=1)
        
        if not customer:
            # Crear cliente automáticamente si no existe
            provider = request.env['payment.provider'].search([
                ('code', '=', 'culqi'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if provider:
                customer = request.env['culqi.customer'].create({
                    'partner_id': partner.id,
                    'provider_id': provider.id,
                    'name': partner.name,
                    'email': partner.email,
                })
        
        # Configurar domain y ordenamiento
        domain = [('customer_id', '=', customer.id)] if customer else []
        
        searchbar_sortings = {
            'date': {'label': _('Fecha más reciente'), 'order': 'create_date desc'},
            'name': {'label': _('Nombre'), 'order': 'name'},
            'brand': {'label': _('Marca'), 'order': 'card_brand'},
            'status': {'label': _('Estado'), 'order': 'state'},
        }
        
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']
        
        # Paginación
        card_count = request.env['culqi.card'].search_count(domain)
        pager = portal_pager(
            url="/my/payment_methods",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby},
            total=card_count,
            page=page,
            step=self._items_per_page
        )
        
        # Obtener tarjetas
        cards = request.env['culqi.card'].search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        
        values.update({
            'date': date_begin,
            'date_end': date_end,
            'cards': cards,
            'customer': customer,
            'page_name': 'payment_methods',
            'archive_groups': [],
            'default_url': '/my/payment_methods',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
        })
        
        return request.render("payment_culqi.portal_my_payment_methods", values)

    @http.route(['/my/payment_methods/<int:card_id>'], type='http', auth="user", website=True)
    def portal_payment_method_detail(self, card_id, access_token=None, **kw):
        """Detalle de un método de pago."""
        try:
            card_sudo = self._document_check_access('culqi.card', card_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        
        # Verificar que la tarjeta pertenece al usuario
        if card_sudo.partner_id != request.env.user.partner_id:
            return request.redirect('/my')
        
        values = {
            'card': card_sudo,
            'page_name': 'payment_method_detail',
        }
        
        return request.render("payment_culqi.portal_payment_method_detail", values)

    @http.route('/my/payment_methods/add', type='http', auth="user", website=True)
    def portal_add_payment_method(self, **kw):
        """Formulario para agregar nuevo método de pago."""
        partner = request.env.user.partner_id
        
        # Obtener o crear cliente Culqi
        customer = request.env['culqi.customer'].search([
            ('partner_id', '=', partner.id)
        ], limit=1)
        
        if not customer:
            provider = request.env['payment.provider'].search([
                ('code', '=', 'culqi'),
                ('state', 'in', ['enabled', 'test'])
            ], limit=1)
            
            if not provider:
                raise ValidationError(_('Servicio de pagos no disponible'))
            
            customer = request.env['culqi.customer'].create({
                'partner_id': partner.id,
                'provider_id': provider.id,
                'name': partner.name,
                'email': partner.email,
            })
            
            # Crear cliente en Culqi si no existe
            if not customer.culqi_customer_id:
                customer.create_in_culqi()
        
        # Obtener configuración del proveedor
        provider = customer.provider_id
        rendering_values = {
            'public_key': provider.culqi_public_key,
            'customer': customer,
            'partner': partner,
        }
        
        values = {
            'customer': customer,
            'provider': provider,
            'rendering_values': rendering_values,
            'page_name': 'add_payment_method',
        }
        
        return request.render("payment_culqi.portal_add_payment_method", values)

    @http.route('/my/payment_methods/save', type='json', auth="user", methods=['POST'])
    def portal_save_payment_method(self, **kw):
        """Guarda un nuevo método de pago desde el portal."""
        try:
            partner = request.env.user.partner_id
            token_id = kw.get('token_id')
            card_name = kw.get('card_name', 'Mi Tarjeta')
            
            if not token_id:
                raise ValidationError(_('Token de tarjeta requerido'))
            
            # Obtener cliente
            customer = request.env['culqi.customer'].search([
                ('partner_id', '=', partner.id)
            ], limit=1)
            
            if not customer:
                raise ValidationError(_('Cliente no encontrado'))
            
            # Crear tarjeta
            card = request.env['culqi.card'].create({
                'customer_id': customer.id,
                'name': card_name,
            })
            
            # Crear en Culqi
            card.create_in_culqi(token_id)
            
            return {
                'success': True,
                'message': _('Método de pago agregado exitosamente'),
                'redirect_url': '/my/payment_methods'
            }
            
        except Exception as e:
            _logger.error('Error guardando método de pago: %s', str(e))
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/my/payment_methods/<int:card_id>/delete', type='json', auth="user", methods=['POST'])
    def portal_delete_payment_method(self, card_id, **kw):
        """Elimina un método de pago."""
        try:
            card = request.env['culqi.card'].browse(card_id)
            
            # Verificar acceso
            if card.partner_id != request.env.user.partner_id:
                raise AccessError(_('No tienes permiso para eliminar esta tarjeta'))
            
            # Verificar que no tenga suscripciones activas
            active_subscriptions = card.subscription_ids.filtered(lambda s: s.state == 'active')
            if active_subscriptions:
                return {
                    'success': False,
                    'error': _('No se puede eliminar una tarjeta con suscripciones activas')
                }
            
            # Eliminar de Culqi y Odoo
            if card.culqi_card_id:
                card.delete_from_culqi()
            card.unlink()
            
            return {
                'success': True,
                'message': _('Método de pago eliminado exitosamente')
            }
            
        except Exception as e:
            _logger.error('Error eliminando método de pago: %s', str(e))
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/my/payment_methods/<int:card_id>/set_default', type='json', auth="user", methods=['POST'])
    def portal_set_default_payment_method(self, card_id, **kw):
        """Establece una tarjeta como método de pago por defecto."""
        try:
            card = request.env['culqi.card'].browse(card_id)
            
            # Verificar acceso
            if card.partner_id != request.env.user.partner_id:
                raise AccessError(_('No tienes permiso para modificar esta tarjeta'))
            
            # Establecer como default
            card.action_set_as_default()
            
            return {
                'success': True,
                'message': _('Tarjeta establecida como método por defecto')
            }
            
        except Exception as e:
            _logger.error('Error estableciendo tarjeta por defecto: %s', str(e))
            return {
                'success': False,
                'error': str(e)
            }

    # ==========================================
    # GESTIÓN DE SUSCRIPCIONES
    # ==========================================

    @http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'], 
                type='http', auth="user", website=True)
    def portal_my_subscriptions(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        """Página de suscripciones del cliente."""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Configurar domain
        domain = [('partner_id', '=', partner.id)]
        
        # Filtros
        searchbar_filters = {
            'all': {'label': _('Todas'), 'domain': []},
            'active': {'label': _('Activas'), 'domain': [('state', '=', 'active')]},
            'trial': {'label': _('En Prueba'), 'domain': [('state', '=', 'trial')]},
            'past_due': {'label': _('Vencidas'), 'domain': [('state', '=', 'past_due')]},
            'cancelled': {'label': _('Canceladas'), 'domain': [('state', '=', 'cancelled')]},
        }
        
        if not filterby:
            filterby = 'all'
        domain += searchbar_filters[filterby]['domain']
        
        # Ordenamiento
        searchbar_sortings = {
            'date': {'label': _('Fecha más reciente'), 'order': 'create_date desc'},
            'name': {'label': _('Nombre'), 'order': 'name'},
            'plan': {'label': _('Plan'), 'order': 'plan_id'},
            'amount': {'label': _('Monto'), 'order': 'total_amount desc'},
            'status': {'label': _('Estado'), 'order': 'state'},
        }
        
        if not sortby:
            sortby = 'date'
        order = searchbar_sortings[sortby]['order']
        
        # Paginación
        subscription_count = request.env['culqi.subscription'].search_count(domain)
        pager = portal_pager(
            url="/my/subscriptions",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'filterby': filterby},
            total=subscription_count,
            page=page,
            step=self._items_per_page
        )
        
        # Obtener suscripciones
        subscriptions = request.env['culqi.subscription'].search(
            domain, order=order, limit=self._items_per_page, offset=pager['offset']
        )
        
        values.update({
            'date': date_begin,
            'date_end': date_end,
            'subscriptions': subscriptions,
            'page_name': 'subscriptions',
            'archive_groups': [],
            'default_url': '/my/subscriptions',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'sortby': sortby,
            'filterby': filterby,
        })
        
        return request.render("payment_culqi.portal_my_subscriptions", values)

    @http.route(['/my/subscriptions/<int:subscription_id>'], type='http', auth="user", website=True)
    def portal_subscription_detail(self, subscription_id, access_token=None, **kw):
        """Detalle de una suscripción."""
        try:
            subscription_sudo = self._document_check_access('culqi.subscription', subscription_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        
        # Verificar que la suscripción pertenece al usuario
        if subscription_sudo.partner_id != request.env.user.partner_id:
            return request.redirect('/my')
        
        # Obtener historial de transacciones
        transactions = subscription_sudo.transaction_ids.sorted('create_date', reverse=True)
        
        # Obtener facturas
        invoices = subscription_sudo.invoice_ids.sorted('create_date', reverse=True)
        
        values = {
            'subscription': subscription_sudo,
            'transactions': transactions,
            'invoices': invoices,
            'page_name': 'subscription_detail',
        }
        
        return request.render("payment_culqi.portal_subscription_detail", values)

    @http.route('/my/subscriptions/<int:subscription_id>/cancel', type='http', auth="user", website=True, methods=['GET', 'POST'])
    def portal_cancel_subscription(self, subscription_id, **kw):
        """Cancelar suscripción desde el portal."""
        try:
            subscription = request.env['culqi.subscription'].browse(subscription_id)
            
            # Verificar acceso
            if subscription.partner_id != request.env.user.partner_id:
                return request.redirect('/my')
            
            if subscription.state not in ['active', 'trial']:
                raise ValidationError(_('Solo se pueden cancelar suscripciones activas'))
            
            if request.httprequest.method == 'GET':
                # Mostrar formulario de confirmación
                values = {
                    'subscription': subscription,
                    'page_name': 'cancel_subscription',
                }
                return request.render("payment_culqi.portal_cancel_subscription", values)
            
            else:  # POST
                # Procesar cancelación
                cancel_reason = kw.get('cancel_reason', '')
                cancel_immediately = kw.get('cancel_immediately') == 'on'
                
                if cancel_immediately:
                    subscription.cancel_in_culqi()
                    subscription.cancellation_reason = cancel_reason
                    message = _('Su suscripción ha sido cancelada inmediatamente.')
                else:
                    subscription.cancel_at_period_end = True
                    subscription.cancellation_reason = cancel_reason
                    message = _('Su suscripción se cancelará al final del periodo actual (%s).') % subscription.current_period_end
                
                return request.render("payment_culqi.portal_subscription_cancelled", {
                    'subscription': subscription,
                    'message': message,
                    'page_name': 'subscription_cancelled',
                })
                
        except Exception as e:
            _logger.error('Error cancelando suscripción: %s', str(e))
            return request.render("payment_culqi.portal_error", {
                'error_message': str(e),
                'page_name': 'error',
            })

    @http.route('/my/subscriptions/<int:subscription_id>/reactivate', type='json', auth="user", methods=['POST'])
    def portal_reactivate_subscription(self, subscription_id, **kw):
        """Reactivar suscripción."""
        try:
            subscription = request.env['culqi.subscription'].browse(subscription_id)
            
            # Verificar acceso
            if subscription.partner_id != request.env.user.partner_id:
                raise AccessError(_('No tienes permiso para reactivar esta suscripción'))
            
            # Reactivar
            subscription.action_reactivate()
            
            return {
                'success': True,
                'message': _('Suscripción reactivada exitosamente')
            }
            
        except Exception as e:
            _logger.error('Error reactivando suscripción: %s', str(e))
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/my/subscriptions/<int:subscription_id>/change_card', type='http', auth="user", website=True, methods=['GET', 'POST'])
    def portal_change_subscription_card(self, subscription_id, **kw):
        """Cambiar tarjeta de una suscripción."""
        try:
            subscription = request.env['culqi.subscription'].browse(subscription_id)
            
            # Verificar acceso
            if subscription.partner_id != request.env.user.partner_id:
                return request.redirect('/my')
            
            if request.httprequest.method == 'GET':
                # Mostrar formulario para cambiar tarjeta
                available_cards = subscription.customer_id.card_ids.filtered(
                    lambda c: c.state == 'active' and not c.is_expired
                )
                
                values = {
                    'subscription': subscription,
                    'available_cards': available_cards,
                    'page_name': 'change_subscription_card',
                }
                return request.render("payment_culqi.portal_change_subscription_card", values)
            
            else:  # POST
                # Procesar cambio de tarjeta
                new_card_id = int(kw.get('card_id'))
                new_card = request.env['culqi.card'].browse(new_card_id)
                
                # Verificar que la tarjeta pertenece al mismo cliente
                if new_card.customer_id != subscription.customer_id:
                    raise ValidationError(_('La tarjeta seleccionada no pertenece al cliente'))
                
                # Actualizar suscripción
                subscription.card_id = new_card
                
                return request.render("payment_culqi.portal_subscription_card_changed", {
                    'subscription': subscription,
                    'new_card': new_card,
                    'page_name': 'subscription_card_changed',
                })
                
        except Exception as e:
            _logger.error('Error cambiando tarjeta de suscripción: %s', str(e))
            return request.render("payment_culqi.portal_error", {
                'error_message': str(e),
                'page_name': 'error',
            })

    # ==========================================
    # PÁGINAS DE SUSCRIPCIÓN PÚBLICA
    # ==========================================

    @http.route('/subscriptions', type='http', auth="public", website=True)
    def public_subscription_plans(self, **kw):
        """Página pública con planes de suscripción disponibles."""
        # Obtener planes publicados
        plans = request.env['culqi.plan'].sudo().get_published_plans()
        
        # Obtener proveedor Culqi
        provider = request.env['payment.provider'].sudo().search([
            ('code', '=', 'culqi'),
            ('state', 'in', ['enabled', 'test'])
        ], limit=1)
        
        values = {
            'plans': plans,
            'provider': provider,
            'page_name': 'subscription_plans',
        }
        
        return request.render("payment_culqi.public_subscription_plans", values)

    @http.route('/subscriptions/plan/<int:plan_id>', type='http', auth="public", website=True)
    def public_subscription_plan_detail(self, plan_id, **kw):
        """Detalle de un plan de suscripción."""
        plan = request.env['culqi.plan'].sudo().search([
            ('id', '=', plan_id),
            ('state', '=', 'active'),
            ('is_published', '=', True)
        ])
        
        if not plan:
            return request.not_found()
        
        # Obtener proveedor
        provider = plan.provider_id
        
        values = {
            'plan': plan,
            'provider': provider,
            'page_name': 'subscription_plan_detail',
        }
        
        return request.render("payment_culqi.public_subscription_plan_detail", values)

    @http.route('/subscriptions/subscribe/<int:plan_id>', type='http', auth="user", website=True)
    def subscribe_to_plan(self, plan_id, **kw):
        """Formulario para suscribirse a un plan."""
        plan = request.env['culqi.plan'].search([
            ('id', '=', plan_id),
            ('state', '=', 'active'),
            ('is_published', '=', True)
        ])
        
        if not plan:
            return request.not_found()
        
        partner = request.env.user.partner_id
        
        # Obtener o crear cliente Culqi
        customer = request.env['culqi.customer'].search([
            ('partner_id', '=', partner.id)
        ], limit=1)
        
        if not customer:
            customer = request.env['culqi.customer'].create({
                'partner_id': partner.id,
                'provider_id': plan.provider_id.id,
                'name': partner.name,
                'email': partner.email,
            })
            customer.create_in_culqi()
        
        # Obtener tarjetas disponibles
        available_cards = customer.card_ids.filtered(
            lambda c: c.state == 'active' and not c.is_expired
        )
        
        values = {
            'plan': plan,
            'customer': customer,
            'available_cards': available_cards,
            'provider': plan.provider_id,
            'page_name': 'subscribe_to_plan',
        }
        
        return request.render("payment_culqi.subscribe_to_plan", values)

    # ==========================================
    # UTILIDADES
    # ==========================================

    def _document_check_access(self, model_name, document_id, access_token=None):
        """Verifica acceso a documento con token opcional."""
        document = request.env[model_name].browse([document_id])
        document_sudo = document.with_user(request.env.ref('base.public_user').id).sudo()
        
        try:
            document.check_access_rights('read')
            document.check_access_rule('read')
        except AccessError:
            if access_token and document_sudo.access_token and consteq(document_sudo.access_token, access_token):
                return document_sudo
            else:
                raise
        return document