# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch
from odoo.tests import tagged
from odoo.exceptions import ValidationError
from odoo.addons.payment_culqi.tests.test_common import CulqiCommon


@tagged('post_install', '-at_install')
class CulqiTransactionTest(CulqiCommon):

    def test_culqi_transaction_process_success(self):
        """ Verifica que una transacción se complete correctamente con un token válido. """
        tx = self._create_transaction(
            provider_id=self.provider.id,
            amount=self.amount,
            currency_id=self.currency.id,
            flow='direct',
        )

        mock_response = {
            'id': 'charge_test_id_123',
            'outcome': {'type': 'venta_exitosa'},
        }

        with patch(
            'odoo.addons.payment_culqi.models.payment_provider.PaymentProvider._culqi_make_request',
            return_value=mock_response,
        ):
            tx._process_direct_payment({'culqi_token': 'tok_test_123'})

        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.provider_reference, 'charge_test_id_123')
        self.assertEqual(tx.culqi_charge_id, 'charge_test_id_123')

    def test_culqi_transaction_missing_token(self):
        """ Asegura que la transacción falle si no se proporciona el token. """
        tx = self._create_transaction(
            provider_id=self.provider.id,
            amount=self.amount,
            currency_id=self.currency.id,
            flow='direct',
        )

        with self.assertRaises(ValidationError):
            tx._process_direct_payment({})  # Sin token

    def test_culqi_transaction_rejected(self):
        """ Verifica que una transacción con respuesta negativa quede en estado de error. """
        tx = self._create_transaction(
            provider_id=self.provider.id,
            amount=self.amount,
            currency_id=self.currency.id,
            flow='direct',
        )

        mock_response = {
            'id': 'charge_fail_456',
            'outcome': {'type': 'venta_rechazada'},
        }

        with patch(
            'odoo.addons.payment_culqi.models.payment_provider.PaymentProvider._culqi_make_request',
            return_value=mock_response,
        ):
            tx._process_direct_payment({'culqi_token': 'tok_fail_456'})

        self.assertEqual(tx.state, 'error')
