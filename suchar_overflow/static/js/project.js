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

            // Keyboard: open/close with Enter/Space/Escape on trigger
            trigger.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    trigger.click();
                } else if (e.key === 'Escape') {
                    dropdown.classList.remove('show');
                    trigger.focus();
                } else if (e.key === 'ArrowDown' && dropdown.classList.contains('show')) {
                    e.preventDefault();
                    const visibleOptions = [...dropdown.querySelectorAll('.dropdown-item:not(.hidden)')];
                    if (visibleOptions.length) visibleOptions[0].focus();
                }
            });

            // Select
            options.forEach(option => {
                option.setAttribute('tabindex', '0');

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

                // Keyboard navigation within dropdown items
                option.addEventListener('keydown', (e) => {
                    const visibleOptions = [...dropdown.querySelectorAll('.dropdown-item:not(.hidden)')];
                    const idx = visibleOptions.indexOf(option);

                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        if (idx < visibleOptions.length - 1) visibleOptions[idx + 1].focus();
                    } else if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        if (idx > 0) visibleOptions[idx - 1].focus();
                        else (searchInput || trigger).focus();
                    } else if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        option.click();
                    } else if (e.key === 'Escape') {
                        dropdown.classList.remove('show');
                        trigger.focus();
                    }
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
    function activateTab(btn) {
        const targetSelector = btn.getAttribute('data-target');
        const targetPane = document.querySelector(targetSelector);
        if (!targetPane) return;

        const parentList = btn.closest('[role="tablist"]');
        if (parentList) {
            parentList.querySelectorAll('[data-toggle="tab"]').forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
                b.setAttribute('tabindex', '-1');
            });
        }

        const contentContainer = targetPane.parentElement;
        if (contentContainer) {
            contentContainer.querySelectorAll('.tab-pane').forEach(pane => {
                pane.classList.remove('show', 'active');
            });
        }

        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        btn.setAttribute('tabindex', '0');
        targetPane.classList.add('show', 'active');
    }

    document.querySelectorAll('[data-toggle="tab"]').forEach(btn => {
        btn.addEventListener('click', () => activateTab(btn));

        btn.addEventListener('keydown', (e) => {
            const parentList = btn.closest('[role="tablist"]');
            if (!parentList) return;
            const tabs = [...parentList.querySelectorAll('[data-toggle="tab"]')];
            const idx = tabs.indexOf(btn);

            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault();
                const next = tabs[(idx + 1) % tabs.length];
                activateTab(next);
                next.focus();
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                const prev = tabs[(idx - 1 + tabs.length) % tabs.length];
                activateTab(prev);
                prev.focus();
            } else if (e.key === 'Home') {
                e.preventDefault();
                activateTab(tabs[0]);
                tabs[0].focus();
            } else if (e.key === 'End') {
                e.preventDefault();
                activateTab(tabs[tabs.length - 1]);
                tabs[tabs.length - 1].focus();
            }
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

    // Custom Toast Helper
    function showToast(messageHtml, titleText = 'Success', type = 'success', isPersistent = false) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.role = 'alert';
        if (isPersistent) {
            toast.setAttribute('data-persistent', 'true');
        }

        const header = document.createElement('div');
        header.className = 'toast-header';

        const strong = document.createElement('strong');
        strong.className = 'me-auto';
        strong.textContent = titleText;

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close';
        closeBtn.setAttribute('aria-label', 'Close');

        header.appendChild(strong);
        header.appendChild(closeBtn);

        const body = document.createElement('div');
        body.className = 'toast-body';
        if (messageHtml instanceof Node) {
            body.appendChild(messageHtml);
        } else {
            body.textContent = messageHtml;
        }

        toast.appendChild(header);
        toast.appendChild(body);

        container.appendChild(toast);

        // Setup dismiss behavior
        const dismiss = () => {
            toast.classList.add('hiding');
            toast.addEventListener('transitionend', () => toast.remove(), { once: true });
        };

        if (!isPersistent) {
            setTimeout(dismiss, 5000);
        }

        closeBtn.addEventListener('click', dismiss);
    }

    window.showToast = showToast;

    // Bell notification dropdown
    const bellWrapper = document.getElementById('bell-wrapper');
    const bellBtn = document.getElementById('bell-btn');
    const bellDropdown = document.getElementById('bell-dropdown');

    if (bellBtn && bellDropdown) {
        bellBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const opening = bellDropdown.hidden;
            bellDropdown.hidden = !opening;
            bellBtn.setAttribute('aria-expanded', String(opening));

            if (opening) {
                const badge = document.getElementById('bell-badge');
                if (badge) {
                    const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
                    fetch('/api/achievements/mark-seen', {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrfToken },
                    }).then(() => badge.remove()).catch(() => {});
                }
            }
        });

        document.addEventListener('click', (e) => {
            if (bellWrapper && !bellWrapper.contains(e.target)) {
                bellDropdown.hidden = true;
                bellBtn.setAttribute('aria-expanded', 'false');
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !bellDropdown.hidden) {
                bellDropdown.hidden = true;
                bellBtn.setAttribute('aria-expanded', 'false');
                bellBtn.focus();
            }
        });
    }

    // Achievements via SSE — browser auto-reconnects after server closes connection
    const userLink = document.querySelector('.user-link');
    if (userLink && window.EventSource) {
        const es = new EventSource('/achievements/stream/');

        es.onmessage = async () => {
            try {
                const response = await fetch('/api/achievements/unseen');
                if (response.status === 401 || response.status === 403) {
                    es.close();
                    return;
                }
                if (!response.ok) return;

                const achievements = await response.json();
                if (!achievements || achievements.length === 0) return;

                const lang = document.documentElement.lang || 'pl';
                const titleText = lang.startsWith('pl') ? 'Odblokowano osiągnięcie!' : 'Achievement Unlocked!';

                achievements.forEach(ach => {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'd-flex align-items-center gap-3';

                    const iconWrapper = document.createElement('div');
                    iconWrapper.className = 'achievement-icon-wrapper text-warning';
                    iconWrapper.style.flexShrink = '0';
                    iconWrapper.textContent = ach.icon_content || '🏆';

                    const textWrapper = document.createElement('div');

                    const title = document.createElement('h6');
                    title.className = 'mb-1 fw-bold';
                    title.textContent = ach.name;

                    const desc = document.createElement('p');
                    desc.className = 'mb-0 text-muted small';
                    desc.textContent = ach.description;

                    textWrapper.appendChild(title);
                    textWrapper.appendChild(desc);
                    wrapper.appendChild(iconWrapper);
                    wrapper.appendChild(textWrapper);

                    showToast(wrapper, titleText, 'success', true);
                });
            } catch (err) {
                console.error('Error fetching achievements:', err);
            }
        };
    }
});
