// The CSRF token for fetch() calls, split out of the old project.js (#468) so modules can import it.
// `app.js` still publishes it as `window.getCsrfToken` (tests and external code read that name).

export function getCsrfToken() {
    return (
        document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
        document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
        ''
    );
}
