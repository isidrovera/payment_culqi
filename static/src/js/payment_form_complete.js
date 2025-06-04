/* payment_culqi/static/src/js/payment_form.js */

(function() {
    'use strict';

    // Configuración global de Culqi
    window.CulqiPayment = {
        config: {},
        initialized: false,
        
        // Inicializar Culqi
        init: function(config) {
            this.config = config;
            
            if (typeof Culqi === 'undefined') {
                console.error('SDK de Culqi no cargado');
                this.showError('Error cargando el procesador de pagos');
                return;
            }

            // Configurar Culqi
            Culqi.publicKey = config.publicKey;
            Culqi.init();
            
            this.initialized = true;
            this.setupEventListeners();
            this.renderPaymentForm();
            
            console.log('Culqi inicializado correctamente');
        },

        // Configurar event listeners
        setupEventListeners: function() {
            const self = this;
            
            // Botón de popup
            const popupButton = document.getElementById('culqi-popup-trigger');
            if (popupButton) {
                popupButton.addEventListener('click', function() {
                    self.openCheckout();
                });
            }

            // Formulario embebido
            if (this.config.checkoutMode === 'embedded') {
                this.setupEmbeddedForm();
            }

            // Escuchar respuesta de Culqi
            this.setupCulqiResponse();
        },

        // Configurar formulario embebido
        setupEmbeddedForm: function() {
            const container = document.getElementById('culqi-payment-container');
            if (!container) return;

            // Crear formulario de tarjeta
            container.innerHTML = `
                <div class="culqi-card-form">
                    <div class="row">
                        <div class="col-12 mb-3">
                            <label for="card-number" class="form-label">Número de Tarjeta</label>
                            <input type="text" id="card-number" class="form-control" 
                                   placeholder="4444 4444 4444 4411" maxlength="19">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-6 mb-3">
                            <label for="expiration-date" class="form-label">Vencimiento</label>
                            <input type="text" id="expiration-date" class="form-control" 
                                   placeholder="MM/YY" maxlength="5">
                        </div>
                        <div class="col-6 mb-3">
                            <label for="cvv" class="form-label">CVV</label>
                            <input type="text" id="cvv" class="form-control" 
                                   placeholder="123" maxlength="4">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-12 mb-3">
                            <label for="cardholder-email" class="form-label">Email</label>
                            <input type="email" id="cardholder-email" class="form-control" 
                                   placeholder="cliente@ejemplo.com">
                        </div>
                    </div>
                    <div class="text-center">
                        <button type="button" id="culqi-pay-button" class="btn btn-primary btn-lg">
                            <i class="fa fa-lock me-2"></i>
                            Procesar Pago
                        </button>
                    </div>
                </div>
            `;

            // Event listener para el botón de pago
            document.getElementById('culqi-pay-button').addEventListener('click', () => {
                this.processEmbeddedPayment();
            });

            // Formateo automático de campos
            this.setupCardFormatting();
        },

        // Configurar formateo de tarjeta
        setupCardFormatting: function() {
            const cardNumber = document.getElementById('card-number');
            const expirationDate = document.getElementById('expiration-date');

            if (cardNumber) {
                cardNumber.addEventListener('input', function(e) {
                    let value = e.target.value.replace(/\s/g, '');
                    let formattedValue = value.replace(/(.{4})/g, '$1 ').trim();
                    e.target.value = formattedValue;
                });
            }

            if (expirationDate) {
                expirationDate.addEventListener('input', function(e) {
                    let value = e.target.value.replace(/\D/g, '');
                    if (value.length >= 2) {
                        value = value.substring(0, 2) + '/' + value.substring(2, 4);
                    }
                    e.target.value = value;
                });
            }
        },

        // Abrir checkout popup
        openCheckout: function() {
            if (!this.initialized) {
                this.showError('Culqi no inicializado');
                return;
            }

            Culqi.open();
        },

        // Procesar pago embebido
        processEmbeddedPayment: function() {
            const cardData = this.getCardData();
            
            if (!this.validateCardData(cardData)) {
                return;
            }

            this.showLoading(true);
            
            // Actualizar configuración de Culqi con datos de la tarjeta
            Culqi.card_number = cardData.card_number;
            Culqi.cvv = cardData.cvv;
            Culqi.expiration_month = cardData.expiration_month;
            Culqi.expiration_year = cardData.expiration_year;
            Culqi.email = cardData.email;
            
            // Crear token con Culqi
            Culqi.createToken();
        },

        // Obtener datos de tarjeta
        getCardData: function() {
            return {
                card_number: document.getElementById('card-number')?.value.replace(/\s/g, ''),
                cvv: document.getElementById('cvv')?.value,
                expiration_month: document.getElementById('expiration-date')?.value.split('/')[0],
                expiration_year: '20' + document.getElementById('expiration-date')?.value.split('/')[1],
                email: document.getElementById('cardholder-email')?.value
            };
        },

        // Validar datos de tarjeta
        validateCardData: function(data) {
            const errors = [];

            if (!data.card_number || data.card_number.length < 13) {
                errors.push('Número de tarjeta inválido');
            }

            if (!data.cvv || data.cvv.length < 3) {
                errors.push('CVV inválido');
            }

            if (!data.expiration_month || !data.expiration_year) {
                errors.push('Fecha de vencimiento inválida');
            }

            if (!data.email || !this.isValidEmail(data.email)) {
                errors.push('Email inválido');
            }

            if (errors.length > 0) {
                this.showError(errors.join(', '));
                return false;
            }

            return true;
        },

        // Validar email
        isValidEmail: function(email) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(email);
        },

        // Configurar respuesta de Culqi
        setupCulqiResponse: function() {
            const self = this;

            // Respuesta exitosa
            window.culqi = function() {
                if (Culqi.token) {
                    self.handleTokenSuccess(Culqi.token);
                } else {
                    self.handleTokenError(Culqi.error);
                }
            };
        },

        // Manejar token exitoso
        handleTokenSuccess: function(token) {
            console.log('Token Culqi generado:', token);
            
            this.showLoading(false);
            this.showSuccess('Token generado correctamente');

            // Enviar token al servidor para crear el cargo
            this.createCharge(token.id);
        },

        // Manejar error de token
        handleTokenError: function(error) {
            console.error('Error Culqi:', error);
            
            this.showLoading(false);
            this.showError(error.user_message || 'Error procesando el pago');
        },

        // Crear cargo en el servidor
        createCharge: function(tokenId) {
            const self = this;
            
            this.showLoading(true, 'Procesando pago...');

            fetch('/payment/culqi/confirm', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    token_id: tokenId,
                    reference: this.config.reference,
                    amount: this.config.amount,
                    currency: this.config.currency,
                    description: this.config.description,
                    customer_email: this.config.customerEmail
                })
            })
            .then(response => response.json())
            .then(data => {
                self.showLoading(false);
                
                if (data.success) {
                    self.showSuccess('¡Pago procesado exitosamente!');
                    
                    // Redireccionar después de un momento
                    setTimeout(() => {
                        if (data.redirect_url) {
                            window.location.href = data.redirect_url;
                        }
                    }, 2000);
                } else {
                    self.showError(data.error || 'Error procesando el pago');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                self.showLoading(false);
                self.showError('Error de conexión');
            });
        },

        // Mostrar mensaje de carga
        showLoading: function(show, message = 'Procesando...') {
            const container = document.getElementById('culqi-payment-container');
            if (!container) return;

            if (show) {
                container.innerHTML = `
                    <div class="text-center p-4">
                        <div class="spinner-border text-primary mb-3" role="status">
                            <span class="visually-hidden">Cargando...</span>
                        </div>
                        <p>${message}</p>
                    </div>
                `;
            }
        },

        // Mostrar mensaje de éxito
        showSuccess: function(message) {
            this.showMessage(message, 'success');
        },

        // Mostrar mensaje de error
        showError: function(message) {
            this.showMessage(message, 'error');
        },

        // Mostrar mensaje general
        showMessage: function(message, type) {
            const messagesContainer = document.getElementById('culqi-messages');
            if (!messagesContainer) return;

            messagesContainer.style.display = 'block';

            // Ocultar otros mensajes
            messagesContainer.querySelectorAll('.alert').forEach(alert => {
                alert.style.display = 'none';
            });

            // Mostrar mensaje apropiado
            const messageElement = document.getElementById(`culqi-${type}-message`);
            if (messageElement) {
                messageElement.style.display = 'block';
                messageElement.querySelector('.message-text').textContent = message;

                // Auto-ocultar después de 5 segundos
                setTimeout(() => {
                    messageElement.style.display = 'none';
                }, 5000);
            }
        },

        // Renderizar formulario de pago
        renderPaymentForm: function() {
            if (this.config.checkoutMode === 'embedded') {
                // El formulario embebido ya se configura en setupEmbeddedForm
                return;
            }

            // Para modo popup, configurar el checkout
            if (this.config.checkoutMode === 'popup') {
                Culqi.settings({
                    title: 'Pago con Culqi',
                    currency: this.config.currency,
                    description: this.config.description,
                    amount: this.config.amount
                });
            }
        },

        // Métodos adicionales para integración con Odoo
        updateTransactionStatus: function(reference) {
            fetch(`/payment/culqi/status?reference=${reference}`, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status) {
                    this.handleStatusUpdate(data);
                }
            })
            .catch(error => {
                console.error('Error actualizando estado:', error);
            });
        },

        handleStatusUpdate: function(data) {
            if (data.status === 'done') {
                this.showSuccess('Pago completado exitosamente');
                setTimeout(() => {
                    window.location.href = '/payment/status';
                }, 2000);
            } else if (data.status === 'pending') {
                this.showMessage('Pago en proceso...', 'info');
                // Volver a verificar en 5 segundos
                setTimeout(() => {
                    this.updateTransactionStatus(this.config.reference);
                }, 5000);
            }
        }
    };

    // Funciones auxiliares para formularios de Odoo
    window.CulqiPayment.OdooIntegration = {
        
        // Inicializar desde formulario de Odoo
        initFromForm: function(formElement) {
            const config = {
                publicKey: formElement.dataset.publicKey,
                checkoutMode: formElement.dataset.checkoutMode,
                reference: formElement.dataset.reference,
                amount: parseInt(formElement.dataset.amount),
                currency: formElement.dataset.currency,
                customerEmail: formElement.dataset.customerEmail,
                description: formElement.dataset.description
            };
            
            window.CulqiPayment.init(config);
        },

        // Manejar envío de formulario de pago
        handlePaymentSubmit: function(event) {
            event.preventDefault();
            
            const form = event.target;
            const paymentMethod = form.querySelector('input[name="payment_method"]:checked');
            
            if (!paymentMethod) {
                window.CulqiPayment.showError('Seleccione un método de pago');
                return;
            }
            
            // Procesar según el método seleccionado
            if (paymentMethod.value === 'card') {
                window.CulqiPayment.processEmbeddedPayment();
            } else {
                // Para otros métodos (Yape, PagoEfectivo, etc.)
                this.processAlternativeMethod(paymentMethod.value);
            }
        },

        // Procesar métodos alternativos
        processAlternativeMethod: function(method) {
            const config = window.CulqiPayment.config;
            
            // Crear cargo directamente para métodos que no requieren token
            fetch('/payment/culqi/create_alternative_charge', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    reference: config.reference,
                    amount: config.amount,
                    currency: config.currency,
                    payment_method: method,
                    customer_email: config.customerEmail
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (method === 'pagoefectivo') {
                        // Mostrar información del CIP
                        this.showPagoEfectivoInfo(data.cip_data);
                    } else {
                        window.location.href = data.redirect_url;
                    }
                } else {
                    window.CulqiPayment.showError(data.error);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                window.CulqiPayment.showError('Error de conexión');
            });
        },

        // Mostrar información de PagoEfectivo
        showPagoEfectivoInfo: function(cipData) {
            const infoHtml = `
                <div class="alert alert-info">
                    <h5>Instrucciones para PagoEfectivo</h5>
                    <p><strong>Código CIP:</strong> ${cipData.cip_code}</p>
                    <p><strong>Válido hasta:</strong> ${cipData.expiration_date}</p>
                    <p>Acérquese a cualquier agente PagoEfectivo con este código para completar su pago.</p>
                </div>
            `;
            
            const container = document.getElementById('culqi-payment-container');
            if (container) {
                container.innerHTML = infoHtml;
            }
        }
    };

    // Inicializar cuando el DOM esté listo
    document.addEventListener('DOMContentLoaded', function() {
        // Verificar si existe configuración de Culqi
        if (typeof window.culqiConfig !== 'undefined') {
            window.CulqiPayment.init(window.culqiConfig);
        }

        // Configurar formularios de pago
        const paymentForms = document.querySelectorAll('.culqi-payment-form');
        paymentForms.forEach(form => {
            window.CulqiPayment.OdooIntegration.initFromForm(form);
            
            form.addEventListener('submit', 
                window.CulqiPayment.OdooIntegration.handlePaymentSubmit
            );
        });
    });

    // Exponer funciones globales si es necesario
    window.initCulqiPayment = function(config) {
        window.CulqiPayment.init(config);
    };

})();