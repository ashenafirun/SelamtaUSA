$(document).ready(function () {
    function parseMonetaryValue(value) {
        // Remove any non-numeric characters (except decimal point)
        value = value.replace(/[^0-9.-]+/g, '');
        return parseFloat(value);
    }

    // Correctly select the span containing the credit limit
    var customerCreditLimitText = $("div.card-body:contains('Credit Limit:')").find('span').text().trim();
    var customerCreditLimit = parseMonetaryValue(customerCreditLimitText);

    var overdueText = $("div.card-body:contains('Over Due:')").find('span').text().trim();
    var overdueLimit = parseMonetaryValue(overdueText);
    var amountTotal = parseFloat($('form[name=o_payment_checkout]').data('amount'));

    console.log('Credit Limit:', customerCreditLimit);
    console.log('Over Due Limit:', overdueLimit);
    console.log('Amount Total:', amountTotal);
    console.log('Amount and Overdue:', overdueLimit + amountTotal);
    console.log('Amount and Overdue condition:', customerCreditLimit <= (overdueLimit + amountTotal));
    console.log('HELLO');

    $('.o_payment_option_card').click(function() {
        var provider = $(this).find("input[name=o_payment_radio]").attr('data-provider');

        // Update blocking message logic
        if (customerCreditLimit <= (overdueLimit + amountTotal)) {
            if (provider == 'transfer') {
                $('#chk-btn').addClass('d-none').attr('disabled', 'disabled');
                $('.warn-msg').removeClass('d-none').fadeIn(1000);
            } else if (provider == 'adyen') {
                $('#chk-btn').removeClass('d-none').removeAttr('disabled');
                $('.warn-msg').addClass('d-none');
            } else {
                $('#chk-btn').addClass('d-none').attr('disabled', 'disabled');
                $('.warn-msg').removeClass('d-none').fadeIn(1000);
            }
        } else {
            $('#chk-btn').removeClass('d-none').removeAttr('disabled');
            $('.warn-msg').addClass('d-none');
        }

        // Trigger change event
        $(this).find("input[name=o_payment_radio]").prop('checked', true).change();
    });
});

