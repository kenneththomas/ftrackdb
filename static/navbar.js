document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-site-nav]').forEach(function (nav) {
        var toggle = nav.querySelector('.nav-menu-toggle');
        var menu = nav.querySelector('.nav-menu');
        if (!toggle || !menu) return;

        nav.classList.add('nav-enhanced');
        toggle.addEventListener('click', function () {
            var isOpen = nav.classList.toggle('is-open');
            toggle.setAttribute('aria-expanded', String(isOpen));
        });
        menu.addEventListener('click', function (event) {
            if (event.target.closest('a')) {
                nav.classList.remove('is-open');
                toggle.setAttribute('aria-expanded', 'false');
            }
        });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && nav.classList.contains('is-open')) {
                nav.classList.remove('is-open');
                toggle.setAttribute('aria-expanded', 'false');
                toggle.focus();
            }
        });
    });
});
