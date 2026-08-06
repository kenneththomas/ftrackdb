(function () {
    'use strict';

    const form = document.querySelector('[data-leaderboard-filters]');
    if (!form) return;

    const eventSelect = form.querySelector('#leaderboard-event');
    const sortSelect = form.querySelector('#leaderboard-sort');

    function syncRelayControls() {
        if (!eventSelect || !sortSelect) return;
        const option = eventSelect.options[eventSelect.selectedIndex];
        const relaySelected = option && option.dataset.relay === 'true';
        sortSelect.disabled = relaySelected;
        if (relaySelected) sortSelect.value = 'performance';
    }

    form.querySelectorAll('select, input[type="checkbox"]').forEach(function (control) {
        control.addEventListener('change', function () {
            syncRelayControls();
            form.requestSubmit();
        });
    });

    form.addEventListener('submit', function () {
        form.setAttribute('aria-busy', 'true');
    });

    syncRelayControls();
}());
