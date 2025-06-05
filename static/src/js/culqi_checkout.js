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

        console.log('🚀 Iniciando configuración de Culqi...');
        this._hideInputs();
        this._setPaymentFlow('direct');

        document.getElementById('o_culqi_loading')?.classList.remove('d-none');

        try {
            // Validar datos de configuración
            const rawData = radio.dataset.culqiInlineFormValues;
            console.log('📋 Raw data:', rawData);
            
            if (!rawData || rawData.trim() === '') {
                throw new Error('No hay datos de configuración para Culqi');
            }

            let inlineFormValues;
            try {
                inlineFormValues = JSON.parse(rawData);
                console.log('✅ Datos parseados correctamente:', {
                    provider_id: inlineFormValues.provider_id,
                    public_key: inlineFormValues.public_key ? `${inlineFormValues.public_key.substring(0, 8)}***` : 'NO DEFINIDA',
                    rsa_id: inlineFormValues.rsa_id ? `${inlineFormValues.rsa_id.substring(0, 8)}***` : 'NO DEFINIDA',
                    logo_url: inlineFormValues.logo_url || 'Sin logo',
                    banner_color: inlineFormValues.banner_color,
                    button_color: inlineFormValues.button_color
                });
            } catch (parseError) {
                console.error('❌ Error parsing JSON:', parseError);
                throw new Error('Datos de configuración de Culqi malformados');
            }

            if (!inlineFormValues.public_key) {
                throw new Error('Falta la clave pública de Culqi');
            }

            const culqiPublicKey = inlineFormValues.public_key;
            const providerId = inlineFormValues.provider_id;

            // Obtener el monto de la transacción
            let orderAmount = 0;
            
            // Intentar obtener desde this.orderAmount
            if (this.orderAmount && !isNaN(this.orderAmount)) {
                orderAmount = parseFloat(this.orderAmount);
                console.log('💰 Monto obtenido de this.orderAmount:', orderAmount);
            } else {
                // Fallback: buscar en el DOM
                const amountElement = document.querySelector('.oe_currency_value, [data-oe-expression*="amount"], .monetary_field');
                if (amountElement) {
                    const amountText = amountElement.textContent || amountElement.innerText || '';
                    const cleanAmount = amountText.replace(/[^\d.,]/g, '').replace(',', '.');
                    orderAmount = parseFloat(cleanAmount) || 0;
                    console.log('💰 Monto obtenido del DOM:', amountText, '→', orderAmount);
                }
            }

            // Si aún no hay monto, usar un valor por defecto para testing
            if (!orderAmount || orderAmount <= 0) {
                orderAmount = 850.00; // Valor de fallback para testing
                console.log('⚠️ Usando monto de fallback:', orderAmount);
            }

            const amountInCents = Math.round(orderAmount * 100);
            console.log('💵 Monto final: S/ ' + orderAmount + ' → ' + amountInCents + ' centavos');

            // Cargar SDK de Culqi (documentación oficial)
            console.log('📦 Cargando SDK de Culqi...');
            await loadJS('https://checkout.culqi.com/js/v4');

            // Verificar que Culqi se haya cargado
            if (typeof window.Culqi === 'undefined') {
                throw new Error('No se pudo cargar el SDK de Culqi');
            }
            console.log('✅ SDK de Culqi cargado exitosamente');

            // Configurar Culqi según documentación oficial
            window.Culqi.publicKey = culqiPublicKey;
            console.log('🔑 Clave pública configurada:', `${culqiPublicKey.substring(0, 12)}***`);
            
            // Configurar settings (obligatorio según documentación)
            const settings = {
                title: 'Pago Odoo',
                currency: 'PEN', // Forzar PEN para Perú
                amount: amountInCents, // Culqi espera centavos
            };

            // Agregar cifrado RSA si está configurado
            if (inlineFormValues.rsa_id && inlineFormValues.rsa_public_key) {
                settings.xculqirsaid = inlineFormValues.rsa_id;
                settings.rsapublickey = inlineFormValues.rsa_public_key;
                console.log('🔐 Cifrado RSA configurado:', `${inlineFormValues.rsa_id.substring(0, 8)}***`);
            } else {
                console.log('ℹ️ Sin cifrado RSA configurado');
            }

            console.log('⚙️ Configurando Culqi settings:', {
                title: settings.title,
                currency: settings.currency,
                amount: settings.amount,
                hasRSA: !!(settings.xculqirsaid && settings.rsapublickey)
            });

            window.Culqi.settings(settings);

            // Configurar opciones (opcional)
            const options = {
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
            };

            console.log('🎨 Configurando opciones de estilo:', {
                logo: options.style.logo || 'Sin logo',
                bannerColor: options.style.bannerColor,
                buttonBackground: options.style.buttonBackground
            });

            window.Culqi.options(options);

            // Definir función callback global (OBLIGATORIO según documentación)
            window.culqi = async () => {
                console.log('🔄 Callback de Culqi ejecutado');
                
                if (window.Culqi.token) {
                    // Token creado exitosamente
                    console.log('✅ Token creado exitosamente:', `${window.Culqi.token.id.substring(0, 12)}***`);
                    console.log('📄 Datos del token:', {
                        id: `${window.Culqi.token.id.substring(0, 12)}***`,
                        email: window.Culqi.token.email,
                        card_number: window.Culqi.token.card_number,
                        last_four: window.Culqi.token.last_four,
                        card_brand: window.Culqi.token.card_brand
                    });
                    
                    try {
                        console.log('📤 Enviando token al backend...');
                        // Enviar token al backend de Odoo
                        const result = await rpc('/payment/culqi/confirm', {
                            provider_id: providerId,
                            token: window.Culqi.token.id,
                            reference: this.txReference,
                        });
                        
                        console.log('✅ Respuesta del backend:', result);
                        
                        // Redirigir según respuesta
                        if (result.redirect_url) {
                            console.log('↗️ Redirigiendo a:', result.redirect_url);
                            window.location = result.redirect_url;
                        } else {
                            console.log('↗️ Redirigiendo a estado de pago por defecto');
                            window.location = '/payment/status';
                        }
                        
                    } catch (error) {
                        console.error('❌ Error procesando pago:', error);
                        if (error instanceof RPCError) {
                            this._displayErrorDialog(_t("Error procesando el pago"), error.data.message);
                        } else {
                            this._displayErrorDialog(_t("Error"), _t("Error inesperado procesando el pago"));
                        }
                    }
                    
                } else if (window.Culqi.order) {
                    // Order creado para métodos alternativos (PagoEfectivo, etc.)
                    console.log('📋 Order creado para método alternativo:', window.Culqi.order);
                    
                    try {
                        console.log('📤 Enviando order al backend...');
                        const result = await rpc('/payment/culqi/confirm_order', {
                            provider_id: providerId,
                            order: window.Culqi.order,
                            reference: this.txReference,
                        });
                        
                        console.log('✅ Respuesta del backend para order:', result);
                        
                        if (result.redirect_url) {
                            console.log('↗️ Redirigiendo a:', result.redirect_url);
                            window.location = result.redirect_url;
                        }
                        
                    } catch (error) {
                        console.error('❌ Error procesando order:', error);
                        this._displayErrorDialog(_t("Error"), _t("Error procesando la orden de pago"));
                    }
                    
                } else {
                    // Error en Culqi
                    console.error('❌ Error en Culqi:', window.Culqi.error);
                    this._displayErrorDialog(_t("Error de pago"), _t("Culqi rechazó el pago: ") + JSON.stringify(window.Culqi.error));
                }
            };

            console.log('✅ Función callback configurada');

            // Mostrar botón de pago
            const culqiBtnContainer = document.getElementById('o_culqi_checkout_placeholder');
            if (culqiBtnContainer) {
                culqiBtnContainer.innerHTML = '';
                const button = document.createElement('button');
                button.className = 'btn btn-primary btn-lg w-100';
                button.innerText = _t("Pagar con Culqi");
                button.onclick = function (e) {
                    e.preventDefault();
                    console.log('🔘 Botón de pago clickeado - Abriendo Culqi...');
                    window.Culqi.open();
                };
                culqiBtnContainer.appendChild(button);
                console.log('🔘 Botón de pago creado y configurado');
            } else {
                console.warn('⚠️ No se encontró el contenedor del botón: o_culqi_checkout_placeholder');
            }

            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            document.getElementById('o_culqi_button_container')?.classList.remove('d-none');

            console.log('🎉 Configuración de Culqi completada exitosamente');

        } catch (error) {
            console.error('❌ Error configurando Culqi:', error);
            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            this._displayErrorDialog(_t("Error de configuración"), error.message);
            return;
        }
    },
});