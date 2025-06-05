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

        console.log('🚀 Iniciando configuración de Culqi v4...');
        this._hideInputs();
        this._setPaymentFlow('direct');

        document.getElementById('o_culqi_loading')?.classList.remove('d-none');

        try {
            // Validar datos de configuración
            const rawData = radio.dataset.culqiInlineFormValues;
            console.log('📋 Raw data: [DATOS OCULTOS POR SEGURIDAD]');
            
            if (!rawData || rawData.trim() === '') {
                throw new Error('No hay datos de configuración para Culqi');
            }

            let inlineFormValues;
            try {
                inlineFormValues = JSON.parse(rawData);
                console.log('✅ Datos parseados correctamente:', {
                    provider_id: inlineFormValues.provider_id,
                    public_key: inlineFormValues.public_key ? 'pk_***' : 'NO DEFINIDA',
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
            
            if (this.orderAmount && !isNaN(this.orderAmount)) {
                orderAmount = parseFloat(this.orderAmount);
                console.log('💰 Monto obtenido de this.orderAmount:', orderAmount);
            } else {
                const amountElement = document.querySelector('.oe_currency_value, [data-oe-expression*="amount"], .monetary_field');
                if (amountElement) {
                    const amountText = amountElement.textContent || amountElement.innerText || '';
                    const cleanAmount = amountText.replace(/[^\d.,]/g, '').replace(',', '.');
                    orderAmount = parseFloat(cleanAmount) || 0;
                    console.log('💰 Monto obtenido del DOM:', amountText, '→', orderAmount);
                }
            }

            if (!orderAmount || orderAmount <= 0) {
                orderAmount = 122.00;
                console.log('⚠️ Usando monto de fallback:', orderAmount);
            }

            const amountInCents = Math.round(orderAmount * 100);
            console.log('💵 Monto final: S/ ' + orderAmount + ' → ' + amountInCents + ' centavos');

            // Obtener referencia de transacción de manera más robusta
            let txReference = this.txReference;
            
            // Si no hay referencia, buscarla de diferentes maneras
            if (!txReference) {
                // Buscar en el DOM
                const refElement = document.querySelector('[name="reference"]') || 
                                 document.querySelector('[data-reference]') ||
                                 document.querySelector('#reference');
                if (refElement) {
                    txReference = refElement.value || refElement.dataset.reference || refElement.textContent;
                }
                
                // Buscar en la URL
                if (!txReference) {
                    const urlParams = new URLSearchParams(window.location.search);
                    txReference = urlParams.get('reference') || urlParams.get('tx_ref');
                }
                
                // Generar desde información de la página
                if (!txReference) {
                    const currentUrl = window.location.href;
                    const invoiceMatch = currentUrl.match(/invoices\/(\d+)/);
                    
                    if (invoiceMatch) {
                        txReference = 'TX-INV-' + invoiceMatch[1] + '-' + Date.now();
                    } else {
                        txReference = 'TX-' + Date.now() + '-' + Math.random().toString(36).substr(2, 5);
                    }
                    console.warn('⚠️ Generando referencia:', txReference);
                }
            }
            
            console.log('🔍 Referencia de transacción:', txReference);

            // Cargar SDK de Culqi v4
            console.log('📦 Cargando SDK de Culqi v4...');
            await loadJS('https://checkout.culqi.com/js/v4');

            // Verificar que Culqi se haya cargado
            if (typeof window.Culqi === 'undefined') {
                throw new Error('No se pudo cargar el SDK de Culqi');
            }
            console.log('✅ SDK de Culqi v4 cargado exitosamente');

            // Configurar clave pública
            window.Culqi.publicKey = culqiPublicKey;
            console.log('🔑 Clave pública configurada: pk_***');

            // Configurar settings obligatorios para v4
            const settings = {
                title: 'Pago Odoo',
                currency: 'PEN',
                amount: amountInCents,
                description: 'Pago desde Odoo'
            };

            // Agregar cifrado RSA si está configurado
            if (inlineFormValues.rsa_id && inlineFormValues.rsa_public_key) {
                settings.xculqirsaid = inlineFormValues.rsa_id;
                settings.rsapublickey = inlineFormValues.rsa_public_key;
                console.log('🔐 Cifrado RSA configurado: rsa_***');
            }

            console.log('⚙️ Configurando Culqi settings...');
            window.Culqi.settings(settings);

            // Configurar opciones de estilo y comportamiento
            const options = {
                lang: "es",
                installments: false,
                paymentMethods: {
                    tarjeta: true,
                    yape: true,
                    bancaMovil: true,
                    agente: true,
                    billetera: true,
                    cuotealo: false
                },
                style: {
                    logo: inlineFormValues.logo_url || '',
                    bannerColor: inlineFormValues.banner_color || '#0033A0',
                    buttonBackground: inlineFormValues.button_color || '#0033A0',
                    buttonText: 'Pagar ahora',
                    buttonTextColor: '#FFFFFF'
                }
            };

            console.log('🎨 Configurando opciones de estilo...');
            window.Culqi.options(options);

            // Función global para manejar respuestas exitosas
            window.culqi = async function() {
                console.log('🔄 Callback de Culqi ejecutado');
                
                if (window.Culqi.token) {
                    console.log('✅ Token creado exitosamente: tkn_***');
                    console.log('📄 Datos del token:', {
                        id: 'tkn_***',
                        email: window.Culqi.token.email || 'No email',
                        card_number: window.Culqi.token.card_number || 'No card',
                        last_four: window.Culqi.token.last_four || 'N/A',
                        card_brand: window.Culqi.token.card_brand || 'N/A'
                    });
                    
                    try {
                        console.log('📤 Enviando token al backend...');
                        const result = await rpc('/payment/culqi/confirm', {
                            provider_id: providerId,
                            token: window.Culqi.token.id,
                            reference: txReference,
                        });
                        
                        console.log('✅ Respuesta del backend:', result);
                        
                        if (result.redirect_url) {
                            console.log('↗️ Redirigiendo a:', result.redirect_url);
                            window.location = result.redirect_url;
                        } else {
                            console.log('↗️ Redirigiendo a estado de pago por defecto');
                            window.location = '/payment/status';
                        }
                        
                    } catch (error) {
                        console.error('❌ Error procesando pago:', error);
                        alert('Error procesando el pago: ' + (error.data?.message || error.message));
                    }
                    
                } else if (window.Culqi.order) {
                    console.log('📋 Order creado para método alternativo');
                    
                    try {
                        const result = await rpc('/payment/culqi/confirm_order', {
                            provider_id: providerId,
                            order: window.Culqi.order,
                            reference: txReference,
                        });
                        
                        if (result.redirect_url) {
                            window.location = result.redirect_url;
                        }
                        
                    } catch (error) {
                        console.error('❌ Error procesando order:', error);
                        alert('Error procesando la orden de pago');
                    }
                }
            };

            // Función global para manejar errores de Culqi
            window.culqiError = function() {
                console.error('❌ Error en Culqi:', window.Culqi.error);
                
                let errorMessage = 'Error en el proceso de pago';
                
                if (window.Culqi.error && window.Culqi.error.merchant_message) {
                    errorMessage = window.Culqi.error.merchant_message;
                } else if (window.Culqi.error && window.Culqi.error.user_message) {
                    errorMessage = window.Culqi.error.user_message;
                }
                
                console.log('📝 Mostrando error al usuario:', errorMessage);
                alert('Error: ' + errorMessage);
            };

            console.log('✅ Funciones callback configuradas');

            // Crear botón de pago oficial de Culqi
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
                
                // Agregar información de prueba
                const infoDiv = document.createElement('div');
                infoDiv.className = 'alert alert-info mt-3';
                infoDiv.innerHTML = `
                    <h6><i class="fa fa-info-circle"></i> Datos de prueba:</h6>
                    <small>
                        <strong>Tarjeta:</strong> 4111 1111 1111 1111<br>
                        <strong>Vencimiento:</strong> 12/30<br>
                        <strong>CVV:</strong> 123<br>
                        <strong>Email:</strong> review@culqi.com
                    </small>
                `;
                culqiBtnContainer.appendChild(infoDiv);
                
            } else {
                console.warn('⚠️ No se encontró el contenedor del botón: o_culqi_checkout_placeholder');
            }

            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            document.getElementById('o_culqi_button_container')?.classList.remove('d-none');

            console.log('🎉 Configuración de Culqi v4 completada exitosamente');

        } catch (error) {
            console.error('❌ Error configurando Culqi:', error);
            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            alert('Error de configuración: ' + error.message);
            return;
        }
    },
});