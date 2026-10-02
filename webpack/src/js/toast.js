// Custom toast helper, split out of the old project.js (#468) so modules can import it instead of
// reading `window.showToast`. The container is looked up per call (it is rendered by base.html),
// so importing this has no side effects. `app.js` still publishes it as `window.showToast`: the
// E2E suite and anything outside the bundles read that name.

export function showToast(messageHtml, titleText, type = 'success', isPersistent = false) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    // Errors interrupt the screen reader (assertive, via role="alert");
    // everything else — achievements, easter-egg delight — is announced
    // politely so it doesn't talk over the user (issue #345).
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    if (isPersistent) {
        toast.setAttribute('data-persistent', 'true');
    }

    const header = document.createElement('div');
    header.className = 'toast-header';

    const strong = document.createElement('strong');
    strong.className = 'me-auto';
    // Translated fallbacks travel on #toast-container's data- attributes
    // (rendered by base.html) — a script can't call {% trans %}.
    strong.textContent = titleText || container.dataset.defaultTitle || 'Powiadomienie';

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close';
    closeBtn.setAttribute('aria-label', container.dataset.closeText || 'Zamknij');

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
        const remove = () => toast.remove();
        toast.addEventListener('transitionend', remove, { once: true });
        // Same reason as hideTooltip's fallback: no fade transition (reduced
        // motion, background tab) means no transitionend, so clean up anyway.
        setTimeout(remove, 400);
    };

    if (!isPersistent) {
        setTimeout(dismiss, 5000);
    }

    closeBtn.addEventListener('click', dismiss);
}
