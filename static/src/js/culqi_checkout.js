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

        try {
            // Validar que existan los datos antes de parsear
            const rawData = radio.dataset.culqiInlineFormValues;
            console.log('Raw data:', rawData); // Para debug
            
            if (!rawData || rawData.trim() === '') {
                throw new Error('No hay datos de configuración para Culqi');
            }

            let inlineFormValues;
            try {
                inlineFormValues = JSON.parse(rawData);
            } catch (parseError) {
                console.error('Error parsing JSON:', parseError);
                throw new Error('Datos de configuración de Culqi malformados');
            }

            // Validar que existan las propiedades necesarias
            if (!inlineFormValues.public_key) {
                throw new Error('Falta la clave pública de Culqi');
            }

            if (!inlineFormValues.provider_id) {
                throw new Error('Falta el ID del proveedor');
            }

            const culqiPublicKey = inlineFormValues.public_key;
            const providerId = inlineFormValues.provider_id;

            // Cargar SDK de Culqi
            await loadJS('https://checkout.culqi.com/js/v4');

            // Verificar que Culqi se haya cargado
            if (typeof window.Culqi === 'undefined') {
                throw new Error('No se pudo cargar el SDK de Culqi');
            }

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

        } catch (error) {
            console.error('Error en Culqi:', error);
            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            this._displayErrorDialog(_t("Error de configuración"), error.message);
            return;
        }
    },
});