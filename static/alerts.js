window.setTimeout(function() {
    const alerts = document.querySelectorAll('.alert:not(.alert-static)');
    alerts.forEach(function(alert) {
    alert.classList.add('fade');
    alert.classList.remove('show');

    // Wait for the fade transition to finish, then remove the element
    setTimeout(function() {
        alert.remove();
    }, 500); // match Bootstrap's fade transition duration
    });
}, 3000); // delay before starting fade
