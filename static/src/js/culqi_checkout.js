/** @odoo-module **/

import { loadJS } from '@web/core/assets';
import { _t } from '@web/core/l10n/translation';
import { rpc, RPCError } from '@web/core/network/rpc';
import paymentForm from '@payment/js/payment_form';

paymentForm.include({
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
            // Validar datos de configuración
            const rawData = radio.dataset.culqiInlineFormValues;
            console.log('Raw data:', rawData);
            
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

            if (!inlineFormValues.public_key) {
                throw new Error('Falta la clave pública de Culqi');
            }

            const culqiPublicKey = inlineFormValues.public_key;
            const providerId = inlineFormValues.provider_id;

            // Cargar SDK de Culqi (documentación oficial)
            await loadJS('https://checkout.culqi.com/js/v4');

            // Verificar que Culqi se haya cargado
            if (typeof window.Culqi === 'undefined') {
                throw new Error('No se pudo cargar el SDK de Culqi');
            }

            // Configurar Culqi según documentación oficial
            window.Culqi.publicKey = culqiPublicKey;
            
            // Configurar settings (obligatorio según documentación)
            window.Culqi.settings({
                title: 'Pago Odoo',
                currency: this.orderCurrency || 'PEN',
                amount: Math.round(this.orderAmount * 100), // Culqi espera centavos
            });

            // Configurar opciones (opcional)
            window.Culqi.options({
                lang: "auto",
                installments: false, // Deshabilitamos cuotas por simplicidad
                paymentMethods: {
                    tarjeta: true,
                    yape: true,
                    bancaMovil: true,
                    agente: true,
                    billetera: true,
                    cuotealo: true,
                },
                style: {
                    logo: inlineFormValues.logo_url || '',
                    bannerColor: inlineFormValues.banner_color || '#0033A0',
                    buttonBackground: inlineFormValues.button_color || '#0033A0',
                    buttonText: 'Pagar ahora',
                    buttonTextColor: '#FFFFFF',
                }
            });

            // Definir función callback global (OBLIGATORIO según documentación)
            window.culqi = async () => {
                if (window.Culqi.token) {
                    // Token creado exitosamente
                    console.log('Token creado:', window.Culqi.token.id);
                    
                    try {
                        // Enviar token al backend de Odoo
                        const result = await rpc('/payment/culqi/confirm', {
                            provider_id: providerId,
                            token: window.Culqi.token.id,
                            reference: this.txReference,
                        });
                        
                        // Redirigir según respuesta
                        if (result.redirect_url) {
                            window.location = result.redirect_url;
                        } else {
                            window.location = '/payment/status';
                        }
                        
                    } catch (error) {
                        console.error('Error procesando pago:', error);
                        if (error instanceof RPCError) {
                            this._displayErrorDialog(_t("Error procesando el pago"), error.data.message);
                        } else {
                            this._displayErrorDialog(_t("Error"), _t("Error inesperado procesando el pago"));
                        }
                    }
                    
                } else if (window.Culqi.order) {
                    // Order creado para métodos alternativos (PagoEfectivo, etc.)
                    console.log('Order creado:', window.Culqi.order);
                    
                    try {
                        const result = await rpc('/payment/culqi/confirm_order', {
                            provider_id: providerId,
                            order: window.Culqi.order,
                            reference: this.txReference,
                        });
                        
                        if (result.redirect_url) {
                            window.location = result.redirect_url;
                        }
                        
                    } catch (error) {
                        console.error('Error procesando order:', error);
                        this._displayErrorDialog(_t("Error"), _t("Error procesando la orden de pago"));
                    }
                    
                } else {
                    // Error en Culqi
                    console.error('Error Culqi:', window.Culqi.error);
                    this._displayErrorDialog(_t("Error de pago"), _t("Culqi rechazó el pago"));
                }
            };

            // Mostrar botón de pago
            const culqiBtnContainer = document.getElementById('o_culqi_checkout_placeholder');
            if (culqiBtnContainer) {
                culqiBtnContainer.innerHTML = '';
                const button = document.createElement('button');
                button.className = 'btn btn-primary btn-lg w-100';
                button.innerText = _t("Pagar con Culqi");
                button.onclick = function (e) {
                    e.preventDefault();
                    window.Culqi.open();
                };
                culqiBtnContainer.appendChild(button);
            }

            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            document.getElementById('o_culqi_button_container')?.classList.remove('d-none');

        } catch (error) {
            console.error('Error configurando Culqi:', error);
            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            this._displayErrorDialog(_t("Error de configuración"), error.message);
            return;
        }
    },
});