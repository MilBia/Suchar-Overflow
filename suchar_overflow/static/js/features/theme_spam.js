/* Easter egg: klepanie przełącznika motywu (10× w ciągu 5 s) → toast
 * „zdecyduj się 🙃" + ukryty achievement. Issue #289, parasol #278.
 *
 * Egg „delight" z grupy A zbudowany na fundamencie #282. Nie podpina żadnego
 * własnego globala (poza flagą inicjalizacji `window.__themeSpamReady`):
 * korzysta z `window.easterEggs` dla zdeduplikowanego przyznania + bramki
 * reduced-motion, oraz z `window.showToast` (project.js) na toast.
 *
 * Ładowany w globalnym bloku `{% compress js %}` w base.html, PO tumbleweed.js,
 * więc trigger nasłuchuje na każdej stronie dla zalogowanego użytkownika.
 * `window.showToast` i `window.easterEggs` czytane są w chwili triggera, nigdy
 * w czasie ładowania modułu — project.js definiuje `showToast` dopiero we
 * własnym handlerze DOMContentLoaded, więc kolejność rejestracji listenerów w
 * bundlu nie może mieć znaczenia.
 *
 * Cały plik to IIFE, żeby jego drobne helpery (`STYLE_ID`, …) nie kolidowały
 * na najwyższym poziomie bundla z project.js / easter_eggs.js / pozostałymi
 * eggami grupy A — kolizja `const` to SyntaxError obejmujący cały bundle
 * (patrz CLAUDE.md i ta sama reguła w konami.js / badumtss.js / logo_spin.js /
 * tumbleweed.js).
 *
 * Trigger: listener `click` bezpośrednio na `#theme-toggle`, NIE
 * MutationObserver na `data-theme` — project.js ustawia `data-theme` przy
 * każdym załadowaniu strony (`setTheme(currentTheme)` bezwarunkowo), co byłoby
 * wbudowanym fałszywym trafieniem dla obserwatora atrybutu. `#theme-toggle` to
 * zwykły `<button>` (bez nawigacji, w odróżnieniu od `<a>` w logo_spin.js),
 * więc bufor kliknięć żyje w pamięci jak bufor klawiszy konami, nie w
 * sessionStorage.
 *
 * Efekt przy każdej nowej serii 10 kliknięć w ciągu 5 s (per #289 — powtarza
 * się, jak pozostałe eggi grupy A, nie jednorazowy):
 *   - toast „Zdecyduj się 🙃";
 *   - ukryty achievement `frontend-ee-niezdecydowany` (POST raz na sesję przez
 *     `window.easterEggs.award`, który deduplikuje przez sessionStorage);
 *   - pełny ruch: szybki obrót o 360° samego przycisku przełącznika;
 *   - prefers-reduced-motion: tylko toast + achievement, bez obrotu.
 *
 * Ten egg NIGDY nie woła `setTheme` / nie zapisuje `localStorage.theme` / ciasteczka
 * motywu — jedynie liczy kliknięcia w przycisk, który obsługuje już własny
 * listener project.js, więc motyw zawsze kończy w stanie z ostatniego
 * kliknięcia użytkownika („bez psucia preferencji" z #289).
 */

(function () {
    'use strict';

    const SLUG = 'frontend-ee-niezdecydowany';

    const TOGGLE_SELECTOR = '#theme-toggle';
    // 10 clicks within a 5s sliding window.
    const THRESHOLD = 10;
    const WINDOW_MS = 5000;

    const STYLE_ID = 'ee-theme-spam-style';
    const SPIN_CLASS = 'ee-toggle-spin';
    // Keep in sync with the `600ms` literal in SPIN_CSS; the class is stripped a
    // hair later so the animation is never cut short.
    const SPIN_MS = 600;
    const SPIN_CLEAR_MS = SPIN_MS + 80;

    // One `@keyframes` turn + the class rule that drives it. Injected once as a
    // <style> element — CSP `style-src` allows 'unsafe-inline' (see
    // config/settings/base.py). The nested media query is defence in depth: the
    // JS reduced-motion gate already skips this branch, but if the class is
    // ever added anyway the animation still collapses to nothing.
    const SPIN_CSS =
        '@keyframes ee-toggle-spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}'
        + '.ee-toggle-spin{animation:ee-toggle-spin 600ms ease-in-out}'
        + '@media (prefers-reduced-motion: reduce){.ee-toggle-spin{animation:none}}';

    // ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
    // A sliding window of the last THRESHOLD click timestamps. Stale entries
    // fall out on their own (no idle timer needed, unlike badumtss's typed
    // buffer): pushing past THRESHOLD just shifts the oldest one off.
    let clickTimestamps = [];
    let clickHandler = null;
    let boundToggle = null;
    const activeTimers = new Set();

    function ensureKeyframes() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = SPIN_CSS;
        document.head.appendChild(style);
    }

    function spinToggle(toggle) {
        ensureKeyframes();
        toggle.classList.add(SPIN_CLASS);

        const id = setTimeout(() => {
            activeTimers.delete(id);
            toggle.classList.remove(SPIN_CLASS);
        }, SPIN_CLEAR_MS);
        activeTimers.add(id);
    }

    function showNiezdecydowanyToast() {
        if (typeof window.showToast !== 'function') return;
        window.showToast('Zdecyduj się 🙃', 'Niezdecydowany', 'info');
    }

    function triggerThemeSpam() {
        const ee = window.easterEggs;

        if (ee && typeof ee.award === 'function') {
            ee.award(SLUG);
        }

        showNiezdecydowanyToast();

        const reduced = !!(ee && typeof ee.reducedJuice === 'function' && ee.reducedJuice());
        if (reduced) return;

        const toggle = document.querySelector(TOGGLE_SELECTOR);
        if (toggle) spinToggle(toggle);
    }

    // Push the click into the sliding window and fire when THRESHOLD clicks all
    // fall within WINDOW_MS of each other. Deliberately does not read/write
    // `data-theme` or `localStorage.theme` — project.js's own listener already
    // owns the actual toggle, so the theme is never touched here.
    function handleToggleClick() {
        const now = Date.now();
        clickTimestamps.push(now);
        if (clickTimestamps.length > THRESHOLD) {
            clickTimestamps.shift();
        }

        // `delta >= 0` guards against a system clock wound backward (NTP/DST)
        // mid-burst: without it a negative delta still satisfies `<= WINDOW_MS`
        // and a stale, far-apart click would wrongly look like it's inside the
        // window (same class of guard as tumbleweed.js rejecting a future
        // stored timestamp).
        const delta = now - clickTimestamps[0];
        if (clickTimestamps.length === THRESHOLD && delta >= 0 && delta <= WINDOW_MS) {
            clickTimestamps = [];
            triggerThemeSpam();
        }
    }

    function teardownThemeSpam() {
        if (clickHandler && boundToggle) {
            boundToggle.removeEventListener('click', clickHandler);
        }
        clickHandler = null;
        boundToggle = null;
        activeTimers.forEach((id) => clearTimeout(id));
        activeTimers.clear();
        const style = document.getElementById(STYLE_ID);
        if (style) style.remove();
        document.querySelectorAll(`.${SPIN_CLASS}`).forEach((el) => {
            el.classList.remove(SPIN_CLASS);
        });
        clickTimestamps = [];
    }

    // ── Init ─────────────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        try {
            if (document.body.dataset.userIsAuthenticated !== 'true') return;

            const toggle = document.querySelector(TOGGLE_SELECTOR);
            if (toggle) {
                clickHandler = handleToggleClick;
                boundToggle = toggle;
                toggle.addEventListener('click', clickHandler);
            }

            const ee = window.easterEggs;
            if (ee && typeof ee.registerTeardown === 'function') {
                ee.registerTeardown('themeSpam', teardownThemeSpam);
            }
        } finally {
            // Init-complete signal, mirroring window.__konamiReady /
            // window.__logoSpinReady. The E2E test waits on it before clicking
            // (page `load` isn't synced with bundle execution).
            window.__themeSpamReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/theme_spam.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in konami.js /
     * badumtss.js / logo_spin.js / tumbleweed.js).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the click buffer, the bound listener, the spin
     * timers) survives between tests. `_resetForTests()` is the per-test reset
     * the `beforeEach` in tests/js/theme_spam.test.js must call; it is attached
     * here only, so it never reaches a real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            THRESHOLD,
            WINDOW_MS,
            handleToggleClick,
            triggerThemeSpam,
            spinToggle,
            showNiezdecydowanyToast,
            teardownThemeSpam,
            _resetForTests: teardownThemeSpam,
        };
    }
})();
