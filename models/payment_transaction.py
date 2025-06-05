# Copyright 2025 Tu Empresa
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
import uuid
from datetime import datetime, timedelta
from werkzeug.urls import url_join

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # ==========================================
    # CAMPOS ESPECÍFICOS DE CULQI
    # ==========================================
    
    # Identificadores de Culqi
    culqi_token_id = fields.Char(
        string='Token ID de Culqi',
        help='ID del token generado por Culqi para la transacción.',
        readonly=True
    )
    
    culqi_charge_id = fields.Char(
        string='Charge ID de Culqi',
        help='ID del cargo generado por Culqi.',
        readonly=True
    )
    
    culqi_order_id = fields.Char(
        string='Order ID de Culqi',
        help='ID de la orden generada por Culqi (para pagos diferidos).',
        readonly=True
    )
    
    culqi_source_id = fields.Char(
        string='Source ID',
        help='ID de la fuente de pago (token o tarjeta guardada).',
        readonly=True
    )
    
    # Estado específico de Culqi
    culqi_status = fields.Selection([
        ('pending', 'Pendiente'),
        ('reviewing', 'En Revisión'),
        ('authorized', 'Autorizado'),
        ('captured', 'Capturado'),
        ('paid', 'Pagado'),
        ('failed', 'Fallido'),
        ('expired', 'Expirado'),
        ('cancelled', 'Cancelado'),
        ('refunded', 'Reembolsado'),
        ('partially_refunded', 'Parcialmente Reembolsado'),
    ], string='Estado en Culqi', readonly=True)
    
    # Información adicional
    culqi_response_data = fields.Text(
        string='Datos de Respuesta Culqi',
        help='Respuesta completa de Culqi en formato JSON.',
        readonly=True
    )
    
    culqi_currency_code = fields.Char(
        string='Código de Moneda Culqi',
        help='Código de moneda usado en Culqi.',
        readonly=True
    )
    
    culqi_amount_cents = fields.Integer(
        string='Monto en Centavos',
        help='Monto de la transacción en centavos según Culqi.',
        readonly=True
    )
    
    # Información de tarjeta (sin datos sensibles)
    culqi_card_brand = fields.Char(
        string='Marca de Tarjeta',
        readonly=True
    )
    
    culqi_card_last4 = fields.Char(
        string='Últimos 4 Dígitos',
        readonly=True
    )
    
    culqi_card_type = fields.Char(
        string='Tipo de Tarjeta',
        readonly=True
    )
    
    # Información de 3D Secure
    culqi_3ds_authenticated = fields.Boolean(
        string='3DS Autenticado',
        readonly=True
    )
    
    culqi_3ds_version = fields.Char(
        string='Versión 3DS',
        readonly=True
    )
    
    # Información de cuotas
    culqi_installments = fields.Integer(
        string='Número de Cuotas',
        default=1,
        readonly=True
    )
    
    culqi_installment_amount = fields.Monetary(
        string='Monto por Cuota',
        readonly=True
    )
    
    # Fechas importantes
    culqi_authorization_code = fields.Char(
        string='Código de Autorización',
        readonly=True
    )
    
    culqi_capture_date = fields.Datetime(
        string='Fecha de Captura',
        readonly=True
    )
    
    culqi_expiration_date = fields.Datetime(
        string='Fecha de Expiración',
        readonly=True
    )
    
    # Información de devoluciones
    culqi_refunded_amount = fields.Monetary(
        string='Monto Reembolsado',
        readonly=True,
        default=0.0
    )
    
    culqi_refund_ids = fields.One2many(
        'culqi.refund',
        'transaction_id',
        string='Reembolsos',
        readonly=True
    )
    
    # Relaciones con otros modelos
    culqi_customer_id = fields.Many2one(
        'culqi.customer',
        string='Cliente Culqi',
        readonly=True
    )
    
    culqi_card_id = fields.Many2one(
        'culqi.card',
        string='Tarjeta Guardada',
        readonly=True
    )
    
    # Configuración de transacción
    culqi_antifraud_details = fields.Text(
        string='Detalles Antifraude',
        readonly=True
    )
    
    culqi_metadata = fields.Text(
        string='Metadatos',
        help='Metadatos adicionales enviados a Culqi.',
        readonly=True
    )

    # ==========================================
    # MÉTODOS COMPUTADOS
    # ==========================================
    
    @api.depends('culqi_refunded_amount', 'amount')
    def _compute_culqi_refund_status(self):
        """Computa el estado de reembolso."""
        for tx in self:
            if tx.culqi_refunded_amount == 0:
                tx.culqi_refund_status = 'none'
            elif tx.culqi_refunded_amount >= tx.amount:
                tx.culqi_refund_status = 'full'
            else:
                tx.culqi_refund_status = 'partial'
    
    culqi_refund_status = fields.Selection([
        ('none', 'Sin Reembolso'),
        ('partial', 'Reembolso Parcial'),
        ('full', 'Reembolso Total'),
    ], string='Estado de Reembolso', compute='_compute_culqi_refund_status', store=True)

    # ==========================================
    # MÉTODOS PRINCIPALES DE CULQI
    # ==========================================
    
    def _get_specific_rendering_values(self, processing_values):
        """Obtiene los valores específicos para renderizar el formulario de pago."""
        res = super()._get_specific_rendering_values(processing_values)
        
        if self.provider_code != 'culqi':
            return res
        
        # Generar valores específicos para Culqi
        base_url = self.provider_id.get_base_url()
        
        rendering_values = {
            'api_url': 'https://checkout.culqi.com/js/v4' if not self.provider_id.culqi_is_test_mode 
                      else 'https://checkout.culqi.com/js/v4',
            'public_key': self.provider_id.culqi_public_key,
            'currency': self.currency_id.name,
            'amount': int(self.amount * 100),  # Convertir a centavos
            'reference': self.reference,
            'return_url': url_join(base_url, '/payment/culqi/return'),
            'cancel_url': url_join(base_url, '/payment/culqi/cancel'),
            'webhook_url': self.provider_id.culqi_webhook_url,
            'customer_email': self.partner_email or self.partner_id.email,
            'enable_3ds': self.provider_id.culqi_enable_3ds,
            'installments': self.provider_id.culqi_installments,
            'max_installments': self.provider_id.culqi_max_installments if self.provider_id.culqi_installments else 1,
        }
        
        # Agregar metadatos
        metadata = {
            'odoo_tx_id': self.id,
            'odoo_reference': self.reference,
            'partner_id': self.partner_id.id,
            'invoice_ids': [inv.id for inv in self.invoice_ids] if self.invoice_ids else [],
            'sale_order_ids': [so.id for so in self.sale_order_ids] if self.sale_order_ids else [],
        }
        
        rendering_values['metadata'] = metadata
        
        return rendering_values
    
    def _create_culqi_token(self, card_data):
        """Crea un token en Culqi con los datos de la tarjeta."""
        self.ensure_one()
        
        if self.provider_code != 'culqi':
            return False
        
        try:
            client = self.provider_id._get_culqi_client()
            encryption_options = self.provider_id._get_culqi_encryption_options()
            
            # Preparar datos del token
            token_data = {
                'card_number': card_data.get('card_number'),
                'cvv': card_data.get('cvv'),
                'expiry_month': card_data.get('expiry_month'),
                'expiry_year': card_data.get('expiry_year'),
                'email': self.partner_email or self.partner_id.email,
            }
            
            # Crear token
            if encryption_options:
                token_response = client.token.create(data=token_data, **encryption_options)
            else:
                token_response = client.token.create(data=token_data)
            
            if token_response.get('object') == 'token':
                self.culqi_token_id = token_response['id']
                self.culqi_source_id = token_response['id']
                
                # Guardar información de la tarjeta (sin datos sensibles)
                card_info = token_response.get('card', {})
                self.culqi_card_brand = card_info.get('brand')
                self.culqi_card_last4 = card_info.get('last_four')
                self.culqi_card_type = card_info.get('type')
                
                _logger.info('Token creado exitosamente: %s', self.culqi_token_id)
                return token_response
            else:
                raise UserError(_('Error al crear token: %s') % token_response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al crear token Culqi: %s', str(e))
            self._set_error(_('Error al procesar los datos de la tarjeta: %s') % str(e))
            return False
    
    def _create_culqi_charge(self, source_id=None, capture=True):
        """Crea un cargo en Culqi."""
        self.ensure_one()
        
        if self.provider_code != 'culqi':
            return False
        
        try:
            client = self.provider_id._get_culqi_client()
            
            # Usar el source_id proporcionado o el token_id de la transacción
            source = source_id or self.culqi_source_id or self.culqi_token_id
            
            if not source:
                raise UserError(_('No se encontró una fuente de pago válida.'))
            
            # Preparar datos del cargo
            charge_data = {
                'amount': int(self.amount * 100),  # Convertir a centavos
                'currency_code': self.currency_id.name,
                'email': self.partner_email or self.partner_id.email,
                'source_id': source,
                'description': self.reference or f'Pago {self.id}',
                'capture': capture,
            }
            
            # Agregar metadatos
            if self.culqi_metadata:
                import json
                try:
                    metadata = json.loads(self.culqi_metadata)
                    charge_data['metadata'] = metadata
                except:
                    pass
            
            # Agregar información de cuotas si está habilitado
            if self.provider_id.culqi_installments and self.culqi_installments > 1:
                charge_data['installments'] = self.culqi_installments
            
            # Agregar configuración antifraude
            charge_data['antifraud_details'] = {
                'address': self.partner_address or '',
                'address_city': self.partner_city or '',
                'country_code': self.partner_country_id.code if self.partner_country_id else '',
                'first_name': self.partner_name.split(' ')[0] if self.partner_name else '',
                'last_name': ' '.join(self.partner_name.split(' ')[1:]) if self.partner_name else '',
                'phone_number': self.partner_phone or '',
            }
            
            # Crear cargo
            charge_response = client.charge.create(data=charge_data)
            
            if charge_response.get('object') == 'charge':
                self._process_culqi_charge_response(charge_response)
                return charge_response
            else:
                raise UserError(_('Error al crear cargo: %s') % charge_response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al crear cargo Culqi: %s', str(e))
            self._set_error(_('Error al procesar el pago: %s') % str(e))
            return False
    
    def _process_culqi_charge_response(self, charge_response):
        """Procesa la respuesta del cargo de Culqi."""
        self.ensure_one()
        
        # Guardar información básica del cargo
        self.culqi_charge_id = charge_response['id']
        self.culqi_currency_code = charge_response.get('currency_code')
        self.culqi_amount_cents = charge_response.get('amount')
        self.culqi_authorization_code = charge_response.get('reference_code')
        
        # Guardar respuesta completa
        import json
        self.culqi_response_data = json.dumps(charge_response, indent=2)
        
        # Procesar estado
        outcome = charge_response.get('outcome', {})
        self.culqi_status = outcome.get('type', 'pending')
        
        # Información de 3D Secure
        if 'three_d_secure' in charge_response:
            tds_info = charge_response['three_d_secure']
            self.culqi_3ds_authenticated = tds_info.get('authenticated', False)
            self.culqi_3ds_version = tds_info.get('version')
        
        # Información de tarjeta
        if 'source' in charge_response:
            source = charge_response['source']
            self.culqi_card_brand = source.get('brand')
            self.culqi_card_last4 = source.get('last_four')
            self.culqi_card_type = source.get('type')
        
        # Actualizar estado de la transacción según el resultado
        if self.culqi_status in ['paid', 'captured']:
            self._set_done()
            self.culqi_capture_date = fields.Datetime.now()
        elif self.culqi_status in ['authorized']:
            self._set_authorized()
        elif self.culqi_status in ['failed', 'expired', 'cancelled']:
            error_msg = outcome.get('merchant_message', 'Pago rechazado')
            self._set_error(error_msg)
        else:
            self._set_pending()
        
        _logger.info('Cargo procesado: %s - Estado: %s', self.culqi_charge_id, self.culqi_status)
    
    def _create_culqi_order(self):
        """Crea una orden en Culqi para pagos diferidos."""
        self.ensure_one()
        
        if self.provider_code != 'culqi':
            return False
        
        try:
            client = self.provider_id._get_culqi_client()
            
            # Calcular fecha de expiración (7 días por defecto)
            expiration_date = datetime.now() + timedelta(days=7)
            
            order_data = {
                'amount': int(self.amount * 100),
                'currency_code': self.currency_id.name,
                'description': self.reference or f'Orden {self.id}',
                'order_number': self.reference,
                'client_details': {
                    'first_name': self.partner_name.split(' ')[0] if self.partner_name else '',
                    'last_name': ' '.join(self.partner_name.split(' ')[1:]) if self.partner_name else '',
                    'email': self.partner_email or self.partner_id.email,
                    'phone_number': self.partner_phone or '',
                },
                'expiration_date': int(expiration_date.timestamp()),
                'confirm': True,
            }
            
            order_response = client.order.create(data=order_data)
            
            if order_response.get('object') == 'order':
                self.culqi_order_id = order_response['id']
                self.culqi_expiration_date = expiration_date
                
                _logger.info('Orden creada exitosamente: %s', self.culqi_order_id)
                return order_response
            else:
                raise UserError(_('Error al crear orden: %s') % order_response.get('message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al crear orden Culqi: %s', str(e))
            self._set_error(_('Error al crear la orden de pago: %s') % str(e))
            return False

    # ==========================================
    # MÉTODOS DE WEBHOOK Y NOTIFICACIONES
    # ==========================================
    
    def _handle_culqi_notification(self, notification_data):
        """Maneja las notificaciones de webhook de Culqi."""
        self.ensure_one()
        
        event_type = notification_data.get('type')
        event_data = notification_data.get('data', {})
        
        _logger.info('Procesando notificación Culqi: %s para transacción %s', event_type, self.reference)
        
        if event_type == 'charge.creation':
            self._handle_charge_creation(event_data)
        elif event_type == 'charge.success':
            self._handle_charge_success(event_data)
        elif event_type == 'charge.failed':
            self._handle_charge_failed(event_data)
        elif event_type == 'refund.creation':
            self._handle_refund_creation(event_data)
        else:
            _logger.warning('Tipo de evento no manejado: %s', event_type)
    
    def _handle_charge_creation(self, charge_data):
        """Maneja la creación de un cargo."""
        if charge_data.get('id') == self.culqi_charge_id:
            self._process_culqi_charge_response(charge_data)
    
    def _handle_charge_success(self, charge_data):
        """Maneja el éxito de un cargo."""
        if charge_data.get('id') == self.culqi_charge_id:
            self.culqi_status = 'paid'
            self._set_done()
            self.culqi_capture_date = fields.Datetime.now()
    
    def _handle_charge_failed(self, charge_data):
        """Maneja el fallo de un cargo."""
        if charge_data.get('id') == self.culqi_charge_id:
            self.culqi_status = 'failed'
            outcome = charge_data.get('outcome', {})
            error_msg = outcome.get('merchant_message', 'Pago fallido')
            self._set_error(error_msg)
    
    def _handle_refund_creation(self, refund_data):
        """Maneja la creación de un reembolso."""
        # Buscar o crear el registro de reembolso
        refund = self.env['culqi.refund'].search([
            ('culqi_refund_id', '=', refund_data.get('id'))
        ])
        
        if not refund:
            self.env['culqi.refund'].create({
                'transaction_id': self.id,
                'culqi_refund_id': refund_data.get('id'),
                'amount': refund_data.get('amount', 0) / 100.0,
                'reason': refund_data.get('reason', ''),
                'status': 'pending',
            })

    # ==========================================
    # MÉTODOS DE DEVOLUCIÓN
    # ==========================================
    
    def action_create_refund(self, amount=None, reason=None):
        """Crea un reembolso en Culqi."""
        self.ensure_one()
        
        if self.provider_code != 'culqi':
            return super().action_create_refund(amount, reason)
        
        if not self.culqi_charge_id:
            raise UserError(_('No se puede reembolsar: no hay un cargo asociado.'))
        
        if self.state not in ['done', 'authorized']:
            raise UserError(_('Solo se pueden reembolsar transacciones completadas o autorizadas.'))
        
        # Validar monto
        refund_amount = amount or self.amount
        max_refundable = self.amount - self.culqi_refunded_amount
        
        if refund_amount > max_refundable:
            raise UserError(_('El monto a reembolsar (%.2f) excede el máximo disponible (%.2f).') % (refund_amount, max_refundable))
        
        try:
            client = self.provider_id._get_culqi_client()
            
            refund_data = {
                'amount': int(refund_amount * 100),  # Convertir a centavos
                'charge_id': self.culqi_charge_id,
                'reason': reason or 'Solicitud del cliente',
            }
            
            refund_response = client.refund.create(data=refund_data)
            
            if refund_response.get('object') == 'refund':
                # Crear registro de reembolso
                refund_record = self.env['culqi.refund'].create({
                    'transaction_id': self.id,
                    'culqi_refund_id': refund_response['id'],
                    'amount': refund_amount,
                    'reason': reason or 'Solicitud del cliente',
                    'status': 'pending',
                })
                
                # Actualizar monto reembolsado
                self.culqi_refunded_amount += refund_amount
                
                _logger.info('Reembolso creado: %s por %.2f', refund_response['id'], refund_amount)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Reembolso Creado'),
                        'message': _('El reembolso por %.2f %s ha sido procesado exitosamente.') % (refund_amount, self.currency_id.name),
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_('Error al crear reembolso: %s') % refund_response.get('user_message', 'Error desconocido'))
                
        except Exception as e:
            _logger.error('Error al crear reembolso: %s', str(e))
            raise UserError(_('Error al procesar el reembolso: %s') % str(e))

    # ==========================================
    # MÉTODOS OVERRIDE
    # ==========================================
    
    def _send_payment_request(self):
        """Envía la solicitud de pago a Culqi."""
        if self.provider_code != 'culqi':
            return super()._send_payment_request()
        
        # Para Culqi, el pago se procesa en el frontend con JavaScript
        # Este método se ejecuta cuando se confirma el pago
        return self._set_pending()
    
    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """Obtiene la transacción desde los datos de notificación."""
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        
        if provider_code != 'culqi':
            return tx
        
        # Buscar por reference en los metadatos o en el charge
        reference = notification_data.get('data', {}).get('metadata', {}).get('odoo_reference')
        if reference:
            tx = self.search([('reference', '=', reference)], limit=1)
        
        return tx