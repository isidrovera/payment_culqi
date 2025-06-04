# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    # Configuración específica para métodos de Culqi
    culqi_payment_type = fields.Selection([
        ('card', 'Tarjeta de Crédito/Débito'),
        ('yape', 'Yape'),
        ('pagoefectivo', 'PagoEfectivo'), 
        ('cuotealo', 'Cuotéalo'),
        ('billetera', 'Billetera Digital'),
    ], string="Tipo de Pago Culqi")
    
    culqi_card_brands = fields.Selection([
        ('visa', 'Visa'),
        ('mastercard', 'Mastercard'),
        ('amex', 'American Express'),
        ('diners', 'Diners Club'),
    ], string="Marcas de Tarjeta Soportadas")
    
    culqi_min_amount = fields.Float(
        string="Monto Mínimo",
        help="Monto mínimo para este método de pago en PEN",
        default=1.0
    )
    
    culqi_max_amount = fields.Float(
        string="Monto Máximo", 
        help="Monto máximo para este método de pago en PEN",
        default=10000.0
    )
    
    culqi_processing_time = fields.Selection([
        ('instant', 'Instantáneo'),
        ('1_hour', '1 hora'),
        ('24_hours', '24 horas'),
        ('3_days', '3 días hábiles'),
    ], string="Tiempo de Procesamiento", default='instant')
    
    culqi_description = fields.Text(
        string="Descripción del Método",
        help="Descripción que se mostrará al cliente"
    )
    
    culqi_instructions = fields.Html(
        string="Instrucciones",
        help="Instrucciones específicas para este método de pago"
    )
    
    culqi_enabled_currencies = fields.Many2many(
        'res.currency',
        'payment_method_culqi_currency_rel',  # Tabla de relación específica
        'method_id',  # Columna para payment.method
        'currency_id',  # Columna para res.currency
        string="Monedas Soportadas",
        help="Monedas que soporta este método de pago"
    )

    @api.model
    def _get_culqi_payment_methods(self):
        """Retorna los métodos de pago disponibles para Culqi"""
        return [
            {
                'code': 'card',
                'name': 'Tarjetas de Crédito/Débito',
                'culqi_payment_type': 'card',
                'culqi_description': 'Acepta Visa, Mastercard, American Express y Diners Club',
                'culqi_processing_time': 'instant',
                'culqi_min_amount': 1.0,
                'culqi_max_amount': 50000.0,
            },
            {
                'code': 'yape',
                'name': 'Yape',
                'culqi_payment_type': 'yape',
                'culqi_description': 'Billetera digital del BCP',
                'culqi_processing_time': 'instant',
                'culqi_min_amount': 1.0,
                'culqi_max_amount': 2000.0,
            },
            {
                'code': 'pagoefectivo',
                'name': 'PagoEfectivo',
                'culqi_payment_type': 'pagoefectivo',
                'culqi_description': 'Paga en efectivo en agentes PagoEfectivo',
                'culqi_processing_time': '1_hour',
                'culqi_min_amount': 1.0,
                'culqi_max_amount': 10000.0,
            },
            {
                'code': 'cuotealo',
                'name': 'Cuotéalo',
                'culqi_payment_type': 'cuotealo',
                'culqi_description': 'Paga en cuotas sin tarjeta de crédito',
                'culqi_processing_time': 'instant',
                'culqi_min_amount': 50.0,
                'culqi_max_amount': 15000.0,
            },
        ]

    def _is_compatible_provider(self, provider):
        """Verifica si el método es compatible con el proveedor"""
        res = super()._is_compatible_provider(provider)
        
        if provider.code == 'culqi' and self.culqi_payment_type:
            # Verificar si el proveedor tiene habilitado este método
            if self.culqi_payment_type == 'card':
                return provider.culqi_enable_cards
            elif self.culqi_payment_type == 'yape':
                return provider.culqi_enable_yape
            elif self.culqi_payment_type == 'pagoefectivo':
                return provider.culqi_enable_pagoefectivo
            elif self.culqi_payment_type == 'cuotealo':
                return provider.culqi_enable_cuotealo
        
        return res

    def _get_culqi_payment_form_data(self, amount, currency):
        """Obtiene datos específicos para el formulario de pago"""
        self.ensure_one()
        
        if not self.culqi_payment_type:
            return {}
        
        # Validar monto
        if currency.name == 'PEN':
            amount_pen = amount
        elif currency.name == 'USD':
            # Convertir USD a PEN (aproximado)
            amount_pen = amount * 3.8  # Tasa aproximada, idealmente usar API
        else:
            raise UserError(_("Moneda no soportada para Culqi: %s") % currency.name)
        
        if amount_pen < self.culqi_min_amount:
            raise UserError(_(
                "El monto mínimo para %s es %s PEN"
            ) % (self.name, self.culqi_min_amount))
            
        if amount_pen > self.culqi_max_amount:
            raise UserError(_(
                "El monto máximo para %s es %s PEN"
            ) % (self.name, self.culqi_max_amount))
        
        return {
            'payment_type': self.culqi_payment_type,
            'description': self.culqi_description,
            'processing_time': dict(self._fields['culqi_processing_time'].selection).get(
                self.culqi_processing_time, 'Instantáneo'
            ),
            'instructions': self.culqi_instructions,
            'min_amount': self.culqi_min_amount,
            'max_amount': self.culqi_max_amount,
        }

    @api.model
    def create_culqi_payment_methods(self, provider_id):
        """Crea los métodos de pago por defecto para Culqi"""
        provider = self.env['payment.provider'].browse(provider_id)
        if provider.code != 'culqi':
            return
        
        methods_data = self._get_culqi_payment_methods()
        pen_currency = self.env['res.currency'].search([('name', '=', 'PEN')], limit=1)
        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        
        for method_data in methods_data:
            # Verificar si el método ya existe
            existing_method = self.search([
                ('code', '=', method_data['code']),
                ('provider_ids', 'in', provider_id)
            ])
            
            if not existing_method:
                # Crear nuevo método
                method_vals = {
                    'name': method_data['name'],
                    'code': method_data['code'],
                    'provider_ids': [(4, provider_id)],
                    'culqi_payment_type': method_data['culqi_payment_type'],
                    'culqi_description': method_data['culqi_description'],
                    'culqi_processing_time': method_data['culqi_processing_time'],
                    'culqi_min_amount': method_data['culqi_min_amount'],
                    'culqi_max_amount': method_data['culqi_max_amount'],
                    'culqi_enabled_currencies': [(6, 0, [pen_currency.id, usd_currency.id])],
                }
                
                # Instrucciones específicas según el tipo
                if method_data['culqi_payment_type'] == 'card':
                    method_vals['culqi_instructions'] = """
                    <ul>
                        <li>Acepta Visa, Mastercard, American Express y Diners Club</li>
                        <li>Pago instantáneo y seguro</li>
                        <li>Protegido con tecnología 3D Secure</li>
                    </ul>
                    """
                elif method_data['culqi_payment_type'] == 'yape':
                    method_vals['culqi_instructions'] = """
                    <ul>
                        <li>Escanea el código QR desde tu app Yape</li>
                        <li>Confirma el pago en tu celular</li>
                        <li>Recibe confirmación inmediata</li>
                    </ul>
                    """
                elif method_data['culqi_payment_type'] == 'pagoefectivo':
                    method_vals['culqi_instructions'] = """
                    <ul>
                        <li>Genera tu código CIP</li>
                        <li>Acércate a cualquier agente PagoEfectivo</li>
                        <li>Presenta tu CIP y paga en efectivo</li>
                        <li>Tienes 24 horas para completar el pago</li>
                    </ul>
                    """
                elif method_data['culqi_payment_type'] == 'cuotealo':
                    method_vals['culqi_instructions'] = """
                    <ul>
                        <li>Financia tu compra sin tarjeta de crédito</li>
                        <li>Cuotas flexibles desde 2 hasta 24 meses</li>
                        <li>Aprobación inmediata</li>
                    </ul>
                    """
                
                self.create(method_vals)
                _logger.info("Método de pago Culqi creado: %s", method_data['name'])

    def get_culqi_icon_url(self):
        """Retorna la URL del ícono para este método de pago"""
        self.ensure_one()
        
        if not self.culqi_payment_type:
            return '/payment_culqi/static/src/img/culqi_icon.png'
        
        icon_mapping = {
            'card': '/payment_culqi/static/src/img/cards_icon.png',
            'yape': '/payment_culqi/static/src/img/yape_icon.png',
            'pagoefectivo': '/payment_culqi/static/src/img/pagoefectivo_icon.png',
            'cuotealo': '/payment_culqi/static/src/img/cuotealo_icon.png',
        }
        
        return icon_mapping.get(self.culqi_payment_type, 
                               '/payment_culqi/static/src/img/culqi_icon.png')

    @api.depends('culqi_payment_type')
    def _compute_display_name(self):
        """Computa el nombre a mostrar del método de pago"""
        super()._compute_display_name()
        
        for method in self:
            if method.culqi_payment_type and method.culqi_description:
                method.display_name = f"{method.name} - {method.culqi_description}"

    def action_test_culqi_method(self):
        """Acción para probar la configuración del método de pago"""
        self.ensure_one()
        
        if not self.culqi_payment_type:
            raise UserError(_("Este no es un método de pago de Culqi"))
        
        # Verificar configuración básica
        errors = []
        
        if not self.culqi_min_amount or self.culqi_min_amount <= 0:
            errors.append(_("El monto mínimo debe ser mayor a 0"))
            
        if not self.culqi_max_amount or self.culqi_max_amount <= self.culqi_min_amount:
            errors.append(_("El monto máximo debe ser mayor al mínimo"))
            
        if not self.culqi_enabled_currencies:
            errors.append(_("Debe especificar al menos una moneda soportada"))
        
        if errors:
            raise UserError(_("Errores de configuración:\n%s") % '\n'.join(errors))
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuración Válida'),
                'message': _('El método de pago %s está configurado correctamente') % self.name,
                'type': 'success',
                'sticky': False,
            }
        }