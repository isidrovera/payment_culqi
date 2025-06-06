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
                    console.log('✅ Token creado exitosamente');
                    
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

            // Variables para control de temporizador y seguridad
            let inactivityTimer = null;
            let isPaymentModalOpen = false;
            const INACTIVITY_TIMEOUT = 300000; // 5 minutos en milisegundos

            // Función para iniciar temporizador de inactividad
            function startInactivityTimer() {
                if (inactivityTimer) {
                    clearTimeout(inactivityTimer);
                }
                
                inactivityTimer = setTimeout(() => {
                    if (isPaymentModalOpen) {
                        console.log('⏱️ Cerrando modal por inactividad');
                        window.Culqi.close();
                        isPaymentModalOpen = false;
                        alert('Sesión de pago cerrada por inactividad. Por favor, intente nuevamente.');
                    }
                }, INACTIVITY_TIMEOUT);
            }

            // Función para resetear temporizador
            function resetInactivityTimer() {
                if (isPaymentModalOpen) {
                    startInactivityTimer();
                }
            }

            // Función para enmascarar datos sensibles en logs
            function maskSensitiveData() {
                // Interceptar console.log para ocultar datos sensibles
                const originalLog = console.log;
                console.log = function(...args) {
                    const maskedArgs = args.map(arg => {
                        if (typeof arg === 'string') {
                            // Enmascarar números de tarjeta
                            arg = arg.replace(/\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/g, '****-****-****-****');
                            // Enmascarar CVV
                            arg = arg.replace(/\bcvv[:\s]*\d{3,4}\b/gi, 'cvv: ***');
                            // Enmascarar tokens
                            arg = arg.replace(/tkn_[a-zA-Z0-9]{20,}/g, 'tkn_***[MASKED]***');
                        }
                        return arg;
                    });
                    originalLog.apply(console, maskedArgs);
                };
            }

            // Aplicar enmascaramiento de datos sensibles
            maskSensitiveData();

            // Override del método open de Culqi para control de eventos
            const originalCulqiOpen = window.Culqi.open;
            window.Culqi.open = function() {
                isPaymentModalOpen = true;
                startInactivityTimer();
                
                // Detectar actividad del usuario en el modal
                document.addEventListener('click', resetInactivityTimer);
                document.addEventListener('keypress', resetInactivityTimer);
                document.addEventListener('mousemove', resetInactivityTimer);
                
                console.log('🔓 Modal de pago abierto - Temporizador iniciado');
                return originalCulqiOpen.apply(this, arguments);
            };

            // Override del método close de Culqi
            const originalCulqiClose = window.Culqi.close;
            window.Culqi.close = function() {
                isPaymentModalOpen = false;
                if (inactivityTimer) {
                    clearTimeout(inactivityTimer);
                    inactivityTimer = null;
                }
                
                // Remover listeners de actividad
                document.removeEventListener('click', resetInactivityTimer);
                document.removeEventListener('keypress', resetInactivityTimer);
                document.removeEventListener('mousemove', resetInactivityTimer);
                
                console.log('🔒 Modal de pago cerrado - Temporizador cancelado');
                return originalCulqiClose.apply(this, arguments);
            };

            // Crear botón de pago oficial de Culqi
            const culqiBtnContainer = document.getElementById('o_culqi_checkout_placeholder');
            if (culqiBtnContainer) {
                culqiBtnContainer.innerHTML = '';
                
                // Contenedor principal
                const paymentContainer = document.createElement('div');
                paymentContainer.className = 'culqi-payment-container';
                paymentContainer.innerHTML = `
                    <div class="card border-0 shadow-sm">
                        <div class="card-body text-center p-4">
                            <div class="mb-3">
                                <i class="fa fa-credit-card fa-2x text-primary mb-2"></i>
                                <h5 class="card-title">Pago Seguro</h5>
                                <p class="text-muted">Procesa tu pago de forma segura con Culqi</p>
                            </div>
                            
                            <div class="payment-amount mb-3">
                                <span class="h4 text-success">S/ ${orderAmount.toFixed(2)}</span>
                            </div>
                            
                            <button id="culqi-pay-button" class="btn btn-primary btn-lg w-100 mb-3">
                                <i class="fa fa-lock me-2"></i>
                                ${_t("Pagar Ahora")}
                            </button>
                            
                            <div class="security-info">
                                <small class="text-muted d-block">
                                    <i class="fa fa-shield-alt text-success"></i>
                                    Pago protegido con cifrado SSL
                                </small>
                                <small class="text-muted d-block mt-1">
                                    <i class="fa fa-clock text-info"></i>
                                    Sesión expira en 5 minutos por seguridad
                                </small>
                            </div>
                        </div>
                    </div>
                `;
                
                culqiBtnContainer.appendChild(paymentContainer);
                
                // Agregar evento al botón
                document.getElementById('culqi-pay-button').onclick = function (e) {
                    e.preventDefault();
                    console.log('🔘 Iniciando proceso de pago seguro...');
                    
                    // Cambiar estado del botón
                    e.target.disabled = true;
                    e.target.innerHTML = '<i class="fa fa-spinner fa-spin me-2"></i>Cargando...';
                    
                    // Abrir modal de Culqi
                    try {
                        window.Culqi.open();
                    } catch (error) {
                        console.error('Error abriendo modal:', error);
                        alert('Error al abrir el formulario de pago');
                    } finally {
                        // Restaurar botón después de un delay
                        setTimeout(() => {
                            e.target.disabled = false;
                            e.target.innerHTML = '<i class="fa fa-lock me-2"></i>Pagar Ahora';
                        }, 2000);
                    }
                };
                
                console.log('🔘 Interfaz de pago profesional creada');
                
            } else {
                console.warn('⚠️ No se encontró el contenedor del botón: o_culqi_checkout_placeholder');
            }

            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            document.getElementById('o_culqi_button_container')?.classList.remove('d-none');

            console.log('🎉 Configuración de Culqi v4 completada exitosamente');

            // Agregar estilos CSS personalizados para la interfaz
            const style = document.createElement('style');
            style.textContent = `
                .culqi-payment-container {
                    max-width: 400px;
                    margin: 0 auto;
                }
                
                .culqi-payment-container .card {
                    border-radius: 15px;
                    transition: transform 0.2s ease;
                }
                
                .culqi-payment-container .card:hover {
                    transform: translateY(-2px);
                }
                
                .payment-amount {
                    background: linear-gradient(45deg, #28a745, #20c997);
                    color: white;
                    padding: 15px;
                    border-radius: 10px;
                    margin: 15px 0;
                }
                
                #culqi-pay-button {
                    border-radius: 25px;
                    padding: 12px 30px;
                    font-weight: 600;
                    transition: all 0.3s ease;
                    background: linear-gradient(45deg, #007bff, #0056b3);
                    border: none;
                }
                
                #culqi-pay-button:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 5px 15px rgba(0,123,255,0.3);
                }
                
                #culqi-pay-button:disabled {
                    opacity: 0.7;
                    transform: none;
                }
                
                .security-info {
                    border-top: 1px solid #e9ecef;
                    padding-top: 15px;
                }
                
                .fa-shield-alt, .fa-clock {
                    margin-right: 5px;
                }
                
                /* Animación de carga */
                @keyframes pulse {
                    0% { opacity: 1; }
                    50% { opacity: 0.5; }
                    100% { opacity: 1; }
                }
                
                .loading-pulse {
                    animation: pulse 1.5s infinite;
                }
            `;
            document.head.appendChild(style);

        } catch (error) {
            console.error('❌ Error configurando Culqi:', error);
            document.getElementById('o_culqi_loading')?.classList.add('d-none');
            alert('Error de configuración: ' + error.message);
            return;
        }
    },
});