/* Project specific Javascript goes here. */

const themeToggleBtn = document.getElementById('theme-toggle');
const htmlElement = document.documentElement;

// Functions for theme handling
function setTheme(theme) {
    htmlElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
}

function getCurrentTheme() {
    const localTheme = localStorage.getItem('theme');
    if (localTheme) {
        return localTheme;
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

// Icon SVGs - No longer needed as we use CSS toggling, but kept for reference if needed or cleanup
// ...

// Initialize theme on load
const currentTheme = getCurrentTheme();
setTheme(currentTheme);

// Toggle event listener
if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
        const theme = htmlElement.getAttribute('data-theme');
        const newTheme = theme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    });
}

document.addEventListener('DOMContentLoaded', () => {
    // Mobile Navigation Toggle
    const navbarToggler = document.getElementById('navbar-toggler');
    const navbarMenu = document.getElementById('navbar-menu');

    if (navbarToggler && navbarMenu) {
        navbarToggler.addEventListener('click', () => {
            navbarMenu.classList.toggle('active');
        });
    }

    // Toasts
    const toasts = document.querySelectorAll('.toast');
    toasts.forEach(toast => {
        // Auto remove after 5s
        setTimeout(() => {
            toast.classList.add('hiding');
            toast.addEventListener('transitionend', () => toast.remove());
        }, 5000);

        // Dismiss button
        const closeBtn = toast.querySelector('.btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                toast.classList.add('hiding');
                toast.addEventListener('transitionend', () => toast.remove());
            });
        }
    });

    // Modal Handling
    const logoutBtn = document.getElementById('logout-button');
    const logoutModal = document.getElementById('logoutModal');

    if (logoutBtn && logoutModal) {
        logoutBtn.addEventListener('click', () => {
            logoutModal.hidden = false;
        });
    }

    // Close modals
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        // Close on overlay click
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.hidden = true;
            }
        });

        // Close buttons
        overlay.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                overlay.hidden = true;
            });
        });
    });

    // Custom Dropdown Handling
    const dropdowns = document.querySelectorAll('.custom-dropdown');

    dropdowns.forEach(dropdown => {
        const trigger = dropdown.querySelector('.dropdown-trigger');
        const menu = dropdown.querySelector('.dropdown-menu');
        const input = dropdown.querySelector('input[type="hidden"]');
        const options = dropdown.querySelectorAll('.dropdown-item');

        if (trigger && menu) {
            // Toggle
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                // Close others
                document.querySelectorAll('.custom-dropdown').forEach(d => {
                    if (d !== dropdown) d.classList.remove('show');
                });
                dropdown.classList.toggle('show');
            });

            // Select
            options.forEach(option => {
                option.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const value = option.dataset.value;

                    // Update input
                    if (input) {
                        input.value = value;
                        // Determine parent form and submit
                        const form = dropdown.closest('form');
                        if (form) {
                            form.submit();
                        }
                    }

                    dropdown.classList.remove('show');
                });
            });
        }
    });

    // Outside Click
    document.addEventListener('click', (e) => {
        dropdowns.forEach(dropdown => {
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('show');
            }
        });
    });
});
