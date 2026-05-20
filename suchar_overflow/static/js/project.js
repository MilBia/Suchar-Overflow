/* Project specific Javascript goes here. */

const themeToggleBtn = document.getElementById('theme-toggle');
const htmlElement = document.documentElement;

// Functions for theme handling
function setTheme(theme, withTransition = false) {
    if (withTransition) {
        htmlElement.classList.add('theme-transition');
        setTimeout(() => {
            htmlElement.classList.remove('theme-transition');
        }, 500);
    }
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
        setTheme(newTheme, true);
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
        const dismiss = () => {
            toast.classList.add('hiding');
            toast.addEventListener('transitionend', () => toast.remove(), { once: true });
        };

        // Achievement toasts stay until manually closed; others auto-dismiss after 5s
        if (toast.dataset.persistent !== 'true') {
            setTimeout(dismiss, 5000);
        }

        // Dismiss button
        const closeBtn = toast.querySelector('.btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', dismiss);
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
            // Language search filter
            const searchInput = dropdown.querySelector('.language-search');
            if (searchInput) {
                searchInput.addEventListener('input', () => {
                    const q = searchInput.value.toLowerCase();
                    dropdown.querySelectorAll('.dropdown-item').forEach(item => {
                        const text = item.textContent.toLowerCase();
                        item.classList.toggle('hidden', q.length > 0 && !text.includes(q));
                    });
                });
                searchInput.addEventListener('click', e => e.stopPropagation());
                searchInput.addEventListener('keydown', e => e.stopPropagation());
            }

            // Toggle
            trigger.addEventListener('click', (e) => {
                e.stopPropagation();
                // Close others
                document.querySelectorAll('.custom-dropdown').forEach(d => {
                    if (d !== dropdown) d.classList.remove('show');
                });
                dropdown.classList.toggle('show');
                if (dropdown.classList.contains('show') && searchInput) {
                    setTimeout(() => searchInput.focus(), 50);
                }
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

    // Outside Click — also clear language search on close
    document.addEventListener('click', (e) => {
        dropdowns.forEach(dropdown => {
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('show');
                const searchInput = dropdown.querySelector('.language-search');
                if (searchInput) {
                    searchInput.value = '';
                    dropdown.querySelectorAll('.dropdown-item').forEach(item => item.classList.remove('hidden'));
                }
            }
        });
    });

    // Custom Tabs Switcher
    document.querySelectorAll('[data-toggle="tab"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetSelector = btn.getAttribute('data-target');
            const targetPane = document.querySelector(targetSelector);
            if (!targetPane) return;

            // Deactivate other tabs in the same list
            const parentList = btn.closest('[role="tablist"]');
            if (parentList) {
                parentList.querySelectorAll('[data-toggle="tab"]').forEach(b => {
                    b.classList.remove('active');
                    b.setAttribute('aria-selected', 'false');
                });
            }

            // Deactivate other panes in the same container parent
            const contentContainer = targetPane.parentElement;
            if (contentContainer) {
                contentContainer.querySelectorAll('.tab-pane').forEach(pane => {
                    pane.classList.remove('show', 'active');
                });
            }

            // Activate current
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            targetPane.classList.add('show', 'active');
        });
    });

    // Custom Tooltips Handler
    let activeTooltip = null;

    document.addEventListener('mouseover', (e) => {
        const target = e.target.closest('[data-tooltip]');
        if (!target) return;

        const text = target.getAttribute('data-tooltip');
        if (!text) return;

        // Create tooltip element
        const tooltip = document.createElement('div');
        tooltip.className = 'custom-tooltip-box';
        tooltip.textContent = text;
        document.body.appendChild(tooltip);

        // Position tooltip
        const targetRect = target.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();

        const top = targetRect.top + window.scrollY - tooltipRect.height - 8;
        const left = targetRect.left + window.scrollX + (targetRect.width - tooltipRect.width) / 2;

        tooltip.style.top = `${top}px`;
        tooltip.style.left = `${left}px`;
        tooltip.classList.add('show');

        activeTooltip = tooltip;

        const removeTooltip = () => {
            if (tooltip) {
                tooltip.classList.remove('show');
                tooltip.addEventListener('transitionend', () => tooltip.remove(), { once: true });
                if (activeTooltip === tooltip) activeTooltip = null;
            }
            target.removeEventListener('mouseleave', removeTooltip);
        };

        target.addEventListener('mouseleave', removeTooltip);
    });
});
