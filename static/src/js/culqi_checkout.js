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

        console.log('🚀 Iniciando configuración de Culqi (Backend Token)...');
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

            console.log('💵 Monto final: S/ ' + orderAmount);

            // Crear formulario de tarjeta personalizado
            const culqiBtnContainer = document.getElementById('o_culqi_checkout_placeholder');
            if (culqiBtnContainer) {
                culqiBtnContainer.innerHTML = `
                    <div class="card border-0 shadow-sm">
                        <div class="card-header bg-primary text-white">
                            <h5 class="mb-0"><i class="fa fa-credit-card"></i> Pagar con Tarjeta</h5>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-12 mb-3">
                                    <label class="form-label">Número de Tarjeta</label>
                                    <input type="text" id="card_number" class="form-control" placeholder="1234 5678 9012 3456" maxlength="19">
                                    <small class="text-muted">Usar: 4111 1111 1111 1111 para pruebas</small>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">Vencimiento</label>
                                    <input type="text" id="expiry_date" class="form-control" placeholder="MM/YY" maxlength="5">
                                    <small class="text-muted">Usar: 12/30</small>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <label class="form-label">CVV</label>
                                    <input type="text" id="cvv" class="form-control" placeholder="123" maxlength="4">
                                    <small class="text-muted">Usar: 123</small>
                                </div>
                                <div class="col-md-12 mb-3">
                                    <label class="form-label">Email</label>
                                    <input type="email" id="email" class="form-control" placeholder="email@ejemplo.com" value="review@culqi.com">
                                </div>
                            </div>
                            <button id="pay_button" class="btn btn-primary btn-lg w-100">
                                <i class="fa fa-lock"></i> Pagar S/ ${orderAmount}
                            </button>
                            <div class="text-center mt-2">
                                <small class="text-muted">🔒 Pago seguro con Culqi</small>
                            </div>
                        </div>
                    </div>
                `;

                // Formateo automático de campos
                document.getElementById('card_number').addEventListener('input', function(e) {
                    let value = e.target.value.replace(/\s/g, '');
                    let formattedValue = value.replace(/(\d{4})(?=\d)/g, '$1 ');
                    if (formattedValue !== e.target.value) {
                        e.target.value = formattedValue;
                    }
                });

                document.getElementById('expiry_date').addEventListener('input', function(e) {
                    let value = e.target.value.replace(/\D/g, '');
                    if (value.length >= 2) {
                        value = value.substring(0,2) + '/' + value.substring(2,4);
                    }
                    e.target.value = value;
                });

                document.getElementById('cvv').addEventListener('input', function(e) {
                    e.target.value = e.target.value.replace(/\D/g, '');
                });

                // Manejar el pago
                const self = this; // Guardar contexto
                document.getElementById('pay_button').addEventListener('click', async function(e) {
                    e.preventDefault();
                    
                    const cardNumber = document.getElementById('card_number').value.replace(/\s/g, '');
                    const expiryDate = document.getElementById('expiry_date').value;
                    const cvv = document.getElementById('cvv').value;
                    const email = document.getElementById('email').value;

                    // Validaciones básicas
                    if (!cardNumber || cardNumber.length < 13) {
                        alert('Por favor ingrese un número de tarjeta válido');
                        return;
                    }
                    if (!expiryDate || !expiryDate.includes('/')) {
                        alert('Por favor ingrese una fecha de vencimiento válida (MM/YY)');
                        return;
                    }
                    if (!cvv || cvv.length < 3) {
                        alert('Por favor ingrese un CVV válido');
                        return;
                    }
                    if (!email || !email.includes('@')) {
                        alert('Por favor ingrese un email válido');
                        return;
                    }

                    const [month, year] = expiryDate.split('/');

                    // Verificar que tenemos la referencia
                    const txRef = self.txReference || 'NO_REFERENCE';
                    console.log('🔍 Referencia de transacción:', txRef);

                    console.log('💳 Procesando pago con datos:', {
                        card: cardNumber.substring(0, 4) + '****',
                        expiry: expiryDate,
                        email: email,
                        provider_id: providerId,
                        reference: txRef
                    });

                    // Deshabilitar botón y mostrar loading
                    e.target.disabled = true;
                    e.target.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Procesando...';

                    try {
                        // Enviar datos al backend para crear token y procesar pago
                        console.log('📤 Enviando datos al backend...');
                        const result = await rpc('/payment/culqi/process_card', {
                            provider_id: providerId,
                            reference: txRef,
                            card_data: {
                                card_number: cardNumber,
                                expiration_month: month,
                                expiration_year: '20' + year,
                                cvv: cvv,
                                email: email
                            },
                            amount: Math.round(orderAmount * 100) // centavos
                        });

                        console.log('✅ Respuesta del backend:', result);

                        if (result.success) {
                            console.log('✅ Pago procesado exitosamente');
                            if (result.redirect_url) {
                                console.log('↗️ Redirigiendo a:', result.redirect_url);
                                window.location = result.redirect_url;
                            } else {
                                console.log('↗️ Redirigiendo a estado de pago por defecto');
                                window.location = '/payment/status';
                            }
                        } else {
                            console.error('❌ Error en el pago:', result.error);
                            alert('Error en el pago: ' + (result.error || 'Error desconocido'));
                        }

                    } catch (error) {
                        console.error('❌ Error procesando pago:', error);
                        let errorMessage = 'Error procesando el pago';
                        
                        if (error instanceof RPCError && error.data?.message) {
                            errorMessage = error.data.message;
                        } else if (error.message) {
                            errorMessage = error.message;
                        }
                        
                        alert(errorMessage);
                    } finally {
                        // Rehabilitar botón
                        e.target.disabled = false;
                        e.target.innerHTML = `<i class="fa fa-lock"></i> Pagar S/ ${orderAmount}`;
                    }
                });

                console.log('✅ Formulario de tarjeta creado');
            }

            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            document.getElementById('o_culqi_button_container')?.classList.remove('d-none');

            console.log('🎉 Configuración completada - Usando backend para tokens');

        } catch (error) {
            console.error('❌ Error configurando formulario:', error);
            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            alert('Error de configuración: ' + error.message);
            return;
        }
    },
});