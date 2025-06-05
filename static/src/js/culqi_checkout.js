/** @odoo-module **/

import { loadJS } from '@web/core/assets';
import { _t } from '@web/core/l10n/translation';
import { rpc, RPCError } from '@web/core/network/rpc';
import paymentForm from '@payment/js/payment_form';

paymentForm.include({
    culqiData: undefined,

    async _expandInlineForm(radio) {
        const providerCode = this._getProviderCode(radio);
        if (providerCode !== 'culqi') {
            this._super(...arguments);
            return;
        }

        this._hideInputs();
        this._setPaymentFlow('direct');

        document.getElementById('o_culqi_loading')?.classList.remove('d-none');

        const inlineFormValues = JSON.parse(radio.dataset.culqiInlineFormValues);
        const culqiPublicKey = inlineFormValues.public_key;
        const providerId = inlineFormValues.provider_id;

        // Cargar SDK de Culqi
        await loadJS('https://checkout.culqi.com/js/v4');

        // Configurar Culqi
        window.Culqi.publicKey = culqiPublicKey;
        window.Culqi.settings({
            title: 'Pago Culqi',
            currency: this.orderCurrency,
            description: 'Pago con Odoo',
            amount: Math.round(this.orderAmount * 100), // centavos
        });

        // Definir función de respuesta
        window.culqi = async () => {
            if (Culqi.token) {
                try {
                    await rpc('/payment/culqi/confirm', {
                        provider_id: providerId,
                        token: Culqi.token.id,
                        reference: this.txReference,
                    });
                    window.location = '/payment/status';
                } catch (error) {
                    if (error instanceof RPCError) {
                        this._displayErrorDialog(_t("Error en el procesamiento del pago"), error.data.message);
                    }
                }
            } else if (Culqi.order) {
                this._displayErrorDialog(_t("Error"), _t("Culqi rechazó el pago."));
            } else {
                this._displayErrorDialog(_t("Error"), _t("Token no generado por Culqi."));
            }
        };

        // Mostrar botón
        const culqiBtnContainer = document.getElementById('o_culqi_checkout_placeholder');
        if (culqiBtnContainer) {
            culqiBtnContainer.innerHTML = '';
            const button = document.createElement('button');
            button.className = 'btn btn-primary btn-block';
            button.innerText = _t("Pagar con Culqi");
            button.onclick = function () {
                Culqi.open();
            };
            culqiBtnContainer.appendChild(button);
        }

        document.getElementById('o_culqi_loading')?.classList.add('d-none');
        document.getElementById('o_culqi_button_container')?.classList.remove('d-none');
    },
});
