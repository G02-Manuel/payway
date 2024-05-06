/* global Accept */
odoo.define('payment_pay_way.payment_form', require => {
    'use strict';

    const core = require('web.core');
    const ajax = require('web.ajax');

    const checkoutForm = require('payment.checkout_form');
    const manageForm = require('payment.manage_form');

    const _t = core._t;
    const paywayMethodByName=  {'Visa':'1', 'Diners Club':'8', 'Tarjeta Shopping':'23', 'Tarjeta Naranja':'24', 'PagoFacil':'25', 'RapiPago':'26', 'Italcred':'29', 'ArgenCard':'30', 'CoopePlus':'34', 'Nexo':'37', 'Credimás':'38', 'Tarjeta Nevada':'39', 'Nativa':'42', 'Tarjeta Cencosud':'43', 'Tarjeta Carrefour / Cetelem':'44', 'Tarjeta PymeNacion':'45', 'Caja de Pagos':'48', 'BBPS':'50', 'Cobro Express':'51', 'Qida':'52', 'Grupar':'54', 'Patagonia 365':'55', 'Tarjeta Club Día':'56', 'Tuya':'59', 'Distribution':'60', 'Tarjeta La Anónima':'61', 'CrediGuia':'62', 'Cabal Prisma':'63', 'Tarjeta SOL':'64', 'American Express':'65', 'Amex':'65', 'Favacard':'103', 'MasterCard Prisma':'104', 'MasterCard Prisma':'104', 'Nativa Prisma':'109', 'American Express Prisma':'111', 'Visa Débito':'31', 'MasterCard Debit Prisma':'105', 'Maestro Prisma':'106', 'Cabal Débito Prisma':'108'};
    const paywayMixin = {

        start: function () {

            this._super(...arguments);
        },

        /**
         * Return all relevant inline form inputs based on the payment method type of the provider.
         *
         * @private
         * @param {number} providerId - The id of the selected provider
         * @param {string} flow - The online payment flow of the transaction
         * @return {Object} - An object mapping the name of inline form inputs to their DOM element
         */
        _paywayGetInlineFormInputs: function (providerId, flow) {
            if (flow === 'direct') {
                return {
                    methods: document.getElementById(`o_payway_method_${providerId}`),
                    card: document.getElementById(`o_payway_card_number_${providerId}`),
                    month: document.getElementById(`o_payway_month_${providerId}`),
                    year: document.getElementById(`o_payway_year_${providerId}`),
                    code: document.getElementById(`o_payway_code_${providerId}`),
                    vat: document.getElementById(`o_payway_vat_number_${providerId}`),
                };
            } else if (flow === 'token') {
                return {
                    code: document.getElementById(`o_token_code_${providerId}`),
                };
            }
        },

        /**
         * Prepare the inline form of payway for direct payment.
         *
         * @override method from payment.payment_form_mixin
         * @private
         * @param {string} provider - The provider of the selected payment option's provider
         * @param {number} paymentOptionId - The id of the selected payment option
         * @param {string} flow - The online payment flow of the selected payment option
         * @return {Promise}
         */
        _prepareInlineForm: function (provider, paymentOptionId, flow) {
            if (provider !== 'payway') {
                return this._super(...arguments);
            }
            this._rpc({
                route: '/payment/payway/get_provider_info',
                params: {
                    'rec_id': paymentOptionId,
                    'flow': flow,
                    'net_amount': this.txContext.amount
                },
            }).then(providerInfo => {
                var self = this;
                this.active_card_tree = providerInfo['card_tree'];
                this.payway_url = providerInfo['base_url']
                this.payway_public_key = providerInfo['public_key'];
                this.payway_inhabilitarCS = providerInfo['cybersource'];
                if (flow === 'token') {
                    this._paywaysetInstallments(1, paymentOptionId, 'o_payway_token');
                    return Promise.resolve(); // Don't show the form for tokens
                }
                else {
                    this._setPaymentFlow('direct');
                    this._paywayProcessForm(paymentOptionId)
                    this._paywayListPaymentMethod(paymentOptionId, providerInfo['card_tree']);
                    self = this;
                    document.getElementById('o_payway_card_number_' + paymentOptionId).addEventListener('change',function guessPayment(event){
                        self.guessPaywayPaymentMethod(event, paymentOptionId);
                    });

                }
            }).guardedCatch((error) => {
                error.event.preventDefault();
                this._displayError(
                    _t("Server Error"),
                    _t("An error occurred when displayed this payment form."),
                    error.message.data.message
                );
            });
        },
        guessPaywayPaymentMethod: function(event,paymentOptionId){
            try{
                let inputCard = event.target;
                let cardnumber = inputCard.value.split(" ").join("");
                this.DecidirValidator = new DecidirValidator();
                let cardType = this.DecidirValidator.getCardType(cardnumber);
                if(paywayMethodByName[cardType]){
                    let paywayMethodSelect = document.getElementById('o_payway_method_' + paymentOptionId);
                    paywayMethodSelect.value = paywayMethodByName[cardType];
                    paywayMethodSelect.dispatchEvent(new Event('change'));
                }
            } catch (error) {
                console.error(error);
            }
        },
        /**
         * prepare payway method buttons.
         *
         * @private
         * @param {dict} paymentTree - list of payment info
         */
        _paywayListPaymentMethod: function (paymentOptionId, paymentTree) {
            var self = this;
            let paywayMethodSelect = document.getElementById('o_payway_method_' + paymentOptionId);
            paywayMethodSelect.options.length = 0;

            Object.keys(paymentTree).map((key, index) => {
                let btn = document.createElement('button');
                //TODO : esto deberia ser un Qweb
                let opt = document.createElement('option');
                opt.text = paymentTree[key]['name'];
                opt.value = paymentTree[key]['payway_method'];
                opt.setAttribute("data-card-id", paymentTree[key]['id']);
                opt.setAttribute("data-payway-method-id", paymentTree[key]['payway_method']);
                paywayMethodSelect.appendChild(opt);
            });
            paywayMethodSelect.addEventListener('change', function handleClick(event) {
                self._paywaySetPaymentMethod(event, paymentOptionId);
            });
            paywayMethodSelect.dispatchEvent(new Event('change'));


        },
        _paywaySetPaymentMethod: function (event, paymentOptionId, input_prefix="o_payway") {
            let methodSelect = document.getElementById(input_prefix + '_method_' + paymentOptionId);
            let cardId = methodSelect.options[methodSelect.selectedIndex].dataset.cardId;
            this._paywaysetInstallments(cardId, paymentOptionId);
        },
        _paywaysetInstallments: function (cardId, paymentOptionId, input_prefix="o_payway") {
            let show_installments = this.active_card_tree[cardId]['installments'].length > 1;

            let installmentsLabel = document.getElementById(input_prefix + '_installments_label_' + paymentOptionId);
            let installmentsSelect = document.getElementById(input_prefix + '_installments_select_' + paymentOptionId);

            installmentsSelect.options.length = 0;
            this.active_card_tree[cardId]['installments'].forEach(installment => {
                //TODO : esto deberia ser un Qweb
                let opt = document.createElement('option');
                opt.text = installment.description;
                opt.value = installment.installment;
                opt.setAttribute("data-payway-amount", installment.amount);
                opt.setAttribute("data-payway-base-amount", installment.base_amount);
                opt.setAttribute("data-fees", installment.fee);
                opt.setAttribute("data-payway-installment-id", installment.id);
                opt.setAttribute("data-payway-divisor", installment.divisor);

                installmentsSelect.appendChild(opt);


            });

            if (show_installments) {
                installmentsLabel.classList.remove("o_hidden");
                installmentsSelect.classList.remove("o_hidden");

            } else {
                installmentsLabel.classList.add("o_hidden");
                installmentsSelect.classList.add("o_hidden");
            }

        },
    _prepareTransactionRouteParams: function (provider, paymentOptionId, flow) {
        let RouteParams = this._super(...arguments);
        if (provider === 'payway' && RouteParams['landing_route'] == '/payment/confirmation') {
            RouteParams['landing_route'] = '/payment/payway_confirmation';
        }
        return RouteParams
    },

    /**
     * Process the form of payway for direct payment.
     *
     * @private
     * @param {string} publishable_key - payway public key
     */
        _paywayProcessForm: function (paymentOptionId) {

        },

        /**
         * Dispatch the secure data to payway.
         *
         * @override method from payment.payment_form_mixin
         * @private
         * @param {string} provider - The provider of the provider
         * @param {number} paymentOptionId - The id of the provider handling the transaction
         * @param {object} processingValues - The processing values of the transaction
         * @return {Promise}
         */
        _processDirectPayment: function (provider, paymentOptionId, processingValues) {
            if (provider !== 'payway') {
                return this._super(...arguments);
            }
            var self = this;
            var form = document.getElementById('o_payway_form_' + paymentOptionId);
            if (!this._paywayValidateFormInputs(paymentOptionId, 'direct')) {
                this._enableButton(); // The submit button is disabled at this point, enable it
                $('body').unblock(); // The page is blocked at this point, unblock it
                return Promise.resolve();
            }
            try {
                var decidir = new Decidir(this.payway_url, this.payway_inhabilitarCS);
                decidir.setPublishableKey(this.payway_public_key);
                decidir.createToken(form, function (status, response) {
                    if (status != 200 && status != 201) {
                        let error = response['error'].map(function (obj) {
                            return obj['error']['message']
                        })
                        self._displayError(
                            _t("Server Error"),
                            _t("An error occurred when displayed this payment form."),
                            _t(error.join('<br/>')));
    
                    } else {
                        self._paywayResponseHandler(processingValues, paymentOptionId, response);
    
                    }
                });
            } catch (error) {
                self._displayError(
                    _t("Server Error"),
                    _t("An error occurred when displayed this payment form."),
                    _t(error));

            }             

            //return this._createpaywayToken(paymentOptionId).then((response) => this._paywayResponseHandler(processingValues, response));
        },

        /**
         * called when clicking on pay now or add payment event to create token for credit card/debit card.
         *
         * @private
         * @param {number} providerId - The id of the provider handling the transaction
         * @return {Promise}Form
         */
        _createpaywayToken: function (providerId) {
            let form = document.getElementById('o_payway_form_' + providerId);
            self = this;
            return new Promise(function (resolve, reject) {
                window.payway.createToken(form, function setCardToken(status, response) {
                    if (status == 200 || status == 201) {
                        resolve(response);
                    } else {
                        var error_msg = error_messages[response.cause[0].code];
                        if (error_msg === undefined)
                            error_msg = error_messages['0']
                        self._displayError(
                            _t("Server Error"),
                            _t("An error occurred when displayed this payment form."),
                            _t(error_msg));
                    }
                });
            });
        },

        /**
         * Checks that all payment inputs adhere to the DOM validation constraints.
         *
         * @private
         * @param {number} providerId - The id of the selected provider
         * @return {boolean} - Whether all elements pass the validation constraints
         */
        _paywayValidateFormInputs: function (providerId, flow) {
            const inputs = Object.values(this._paywayGetInlineFormInputs(providerId, flow));
            return inputs.every(element => element.reportValidity());
        },

        /**
         * Payment form payway Token.
         *
         * @override method from payment.payment_form_mixin
         * @param {string} provider - The provider of the provider
         * @param {number} paymentOptionId - The id of the provider handling the transaction
         * @return {Promise}
         */
        _processTokenPayment(provider, paymentOptionId, processingValues) {
            if (provider !== 'payway') {
                return this._super(...arguments);
            }
            try {

                var decidir = new Decidir(this.payway_url, this.payway_inhabilitarCS);
                decidir.setPublishableKey(this.payway_public_key);
                var form = document.getElementById('o_payway_token_form_' + paymentOptionId);
                var self = this;
                decidir.createToken(form, function (status, response) {
                    if (status != 200 && status != 201) {
                        let error = response['error'].map(function (obj) {
                            return obj['error']['message']
                        })
                        self._displayError(
                            _t("Server Error"),
                            _t("An error occurred when displayed this payment form."),
                            _t(error.join('<br/>')));
    
                    } else {
                       self._paywayResponseHandler(processingValues, paymentOptionId, response, 'o_payway_token');
    
                    }
                });
            } catch (error) {
                self._displayError(
                    _t("Server Error"),
                    _t("An error occurred when displayed this payment form."),
                    _t(error));

            }    
        },
        _paywayResponseHandler: function (processingValues, paymentOptionId, response, input_prefix = 'o_payway'){
            // Initiate the payment
            let installments_select = document.getElementById(input_prefix + '_installments_select_' + paymentOptionId);
            let payway_payment_method =  document.getElementById(input_prefix + '_method_' + paymentOptionId);
            let fees = installments_select.options[installments_select.selectedIndex].dataset.fees;
            return this._rpc({
                route: '/payment/payway/payment',
                params: {
                    'bin':response.bin,
                    'last_four_digits':response.last_four_digits,
                    'cardholder':response.cardholder,
                    'reference': processingValues.reference,
                    'partner_id': processingValues.partner_id,
                    'access_token': this.txContext.accessToken,
                    'provider_id': processingValues.provider_id,
                    'token': response.id,
                    'payway_payment_method': payway_payment_method.value,
                    'payway_payment_instalment': parseInt(installments_select.value),
                    'fees': parseFloat(fees),
                    'email': document.getElementById('email').value,
                }
            }).then(() => window.location = '/payment/status');

        }

    };

    checkoutForm.include(paywayMixin);
    manageForm.include(paywayMixin);
});
