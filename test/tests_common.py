# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.addons.payment.tests.common import PaymentCommon


class CulqiCommon(PaymentCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.culqi_provider = cls._prepare_provider('culqi', update_values={
            'culqi_public_key': 'pk_test_dummy',
            'culqi_secret_key': 'sk_test_dummy',
            'culqi_rsa_id': 'rsa_dummy',
            'culqi_rsa_public_key': '-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----',
        })

        cls.provider = cls.culqi_provider
        cls.currency = cls.currency_pen  # PEN es requerido por Culqi
        cls.reference = 'CULQI-TEST-0001'
        cls.amount = 50.00
