# -*- coding: utf-8 -*-

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    """Hook ejecutado después de instalar el módulo"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    try:
        # Verificar si existe el proveedor Culqi
        culqi_provider = env['payment.provider'].search([('code', '=', 'culqi')], limit=1)
        
        if culqi_provider:
            _logger.info("Proveedor Culqi encontrado: %s", culqi_provider.name)
        else:
            _logger.info("Proveedor Culqi creado desde datos XML")
        
        # Crear métodos de pago por defecto si no existen
        create_default_payment_methods(env)
        
        _logger.info("Hook post_init_hook ejecutado correctamente para payment_culqi")
        
    except Exception as e:
        _logger.error("Error en post_init_hook: %s", str(e))


def uninstall_hook(cr, registry):
    """Hook ejecutado antes de desinstalar el módulo"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    try:
        # Desactivar proveedores Culqi
        culqi_providers = env['payment.provider'].search([('code', '=', 'culqi')])
        culqi_providers.write({'state': 'disabled'})
        
        _logger.info("Proveedores Culqi desactivados durante desinstalación")
        
    except Exception as e:
        _logger.error("Error en uninstall_hook: %s", str(e))


def create_default_payment_methods(env):
    """Crea métodos de pago por defecto para Culqi"""
    
    # Buscar el proveedor Culqi
    culqi_provider = env['payment.provider'].search([('code', '=', 'culqi')], limit=1)
    if not culqi_provider:
        return
    
    # Métodos de pago por defecto
    default_methods = [
        {
            'name': 'Tarjetas de Crédito/Débito',
            'code': 'card',
            'culqi_payment_type': 'card',
            'sequence': 10,
        },
        {
            'name': 'Yape',
            'code': 'yape', 
            'culqi_payment_type': 'yape',
            'sequence': 20,
        },
        {
            'name': 'PagoEfectivo',
            'code': 'pagoefectivo',
            'culqi_payment_type': 'pagoefectivo', 
            'sequence': 30,
        },
        {
            'name': 'Cuotéalo',
            'code': 'cuotealo',
            'culqi_payment_type': 'cuotealo',
            'sequence': 40,
        }
    ]
    
    for method_data in default_methods:
        # Verificar si ya existe el método
        existing_method = env['payment.method'].search([
            ('provider_id', '=', culqi_provider.id),
            ('code', '=', method_data['code'])
        ], limit=1)
        
        if not existing_method:
            method_data.update({
                'provider_id': culqi_provider.id,
                'is_primary': method_data['code'] == 'card',  # Tarjeta como método principal
            })
            
            try:
                env['payment.method'].create(method_data)
                _logger.info("Método de pago creado: %s", method_data['name'])
            except Exception as e:
                _logger.error("Error creando método %s: %s", method_data['name'], str(e))