# payment_culqi/hooks.py

def post_init_hook(cr, registry):
    from odoo.api import Environment
    env = Environment(cr, 1, {})

    culqi_provider = env['payment.provider'].search([('code', '=', 'culqi')], limit=1)
    if not culqi_provider:
        return

    env['payment.method'].create({
        'name': 'Culqi (Tarjeta)',
        'code': 'culqi_card',
        'provider_id': culqi_provider.id,
        'available_on': ['portal'],
    })
