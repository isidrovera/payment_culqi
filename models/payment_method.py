# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    # Campos específicos para Culqi (SIMPLIFICADOS)
    culqi_payment_type = fields.Selection([
        ('card', 'Tarjeta de Crédito/Débito'),
        ('yape', 'Yape'),
        ('pagoefectivo', 'PagoEfectivo'), 
        ('cuotealo', 'Cuotéalo'),
    ], string="Tipo de Pago Culqi")
    
    culqi_description = fields.Text(
        string="Descripción del Método",
        help="Descripción que se mostrará al cliente"
    )
    
    # Campo para integración con journals contables (COMO MOLLIE)
    journal_id = fields.Many2one(
        'account.journal', 
        string="Journal",
        compute='_compute_journal_id', 
        inverse='_inverse_journal_id',
        domain="[('type', '=', 'bank')]"
    )

    def _compute_journal_id(self):
        """Computa el journal asociado al método de pago Culqi"""
        for culqi_method in self:
            provider = culqi_method.provider_ids[:1]
            if not provider or provider.code != 'culqi':
                culqi_method.journal_id = False
                continue
            
            payment_method = self.env['account.payment.method.line'].search([
                ('code', '=', culqi_method._get_journal_method_code()),
            ], limit=1)
            
            culqi_method.journal_id = payment_method.journal_id if payment_method else False

    def _inverse_journal_id(self):
        """Inversa del campo journal_id"""
        for culqi_method in self:
            provider = culqi_method.provider_ids[:1]
            if not provider or provider.code != 'culqi':
                continue

            code = culqi_method._get_journal_method_code()
            payment_method_line = self.env['account.payment.method.line'].search([
                *self.env['account.payment.method.line']._check_company_domain(provider.company_id),
                ('code', '=', code),
            ], limit=1)

            if culqi_method.journal_id:
                if not payment_method_line:
                    self._link_culqi_payment_method_to_journal(culqi_method)
                else:
                    payment_method_line.journal_id = culqi_method.journal_id
            elif payment_method_line:
                payment_method_line.unlink()

    def _get_journal_method_code(self):
        """Obtiene el código del método para usar en journals"""
        self.ensure_one()
        return f'culqi_{self.code}'

    def _link_culqi_payment_method_to_journal(self, culqi_method):
        """Vincula el método de pago Culqi a un journal"""
        provider = culqi_method.provider_ids[:1]
        default_payment_method_id = culqi_method._get_default_culqi_payment_method_id(culqi_method)
        
        existing_payment_method_line = self.env['account.payment.method.line'].search([
            *self.env['account.payment.method.line']._check_company_domain(provider.company_id),
            ('payment_method_id', '=', default_payment_method_id),
            ('journal_id', '=', culqi_method.journal_id.id)
        ], limit=1)

        if not existing_payment_method_line:
            self.env['account.payment.method.line'].create({
                'payment_method_id': default_payment_method_id,
                'journal_id': culqi_method.journal_id.id,
            })

    @api.model
    def _get_default_culqi_payment_method_id(self, culqi_method):
        """Obtiene o crea el método de pago por defecto para Culqi"""
        provider_payment_method = self._get_provider_payment_method(culqi_method._get_journal_method_code())
        
        if not provider_payment_method:
            provider_payment_method = self.env['account.payment.method'].sudo().create({
                'name': f'Culqi {culqi_method.name}',
                'code': culqi_method._get_journal_method_code(),
                'payment_type': 'inbound',
            })
        
        return provider_payment_method.id

    @api.model
    def _get_provider_payment_method(self, code):
        """Busca un método de pago existente por código"""
        return self.env['account.payment.method'].search([('code', '=', code)], limit=1)

    def _get_inline_form_xml_id(self, original_xml_id, provider_sudo):
        """Obtiene el ID del template de formulario inline"""
        self.ensure_one()
        inline_form_xml_id = original_xml_id
        
        if provider_sudo.code == 'culqi':
            # Formulario específico para tarjetas Culqi
            if self.code == 'card' and provider_sudo.culqi_checkout_mode == 'embedded':
                inline_form_xml_id = 'payment_culqi.culqi_card_form'
            elif self.code == 'yape':
                inline_form_xml_id = 'payment_culqi.culqi_yape_form'
            elif self.code == 'pagoefectivo':
                inline_form_xml_id = 'payment_culqi.culqi_pagoefectivo_form'
            elif self.code == 'cuotealo':
                inline_form_xml_id = 'payment_culqi.culqi_cuotealo_form'
        
        return inline_form_xml_id

