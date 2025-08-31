document.addEventListener("DOMContentLoaded", function () {
    const userTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const csrfToken = document.body.dataset.csrfToken;
    fetch('/set-timezone', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ timezone: userTimeZone })
    });
});