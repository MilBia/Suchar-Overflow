/* Easter egg: siedmiokrotne szybkie klepnięcie logo w navbarze → krótki obrót
 * logo i toast z losowym „meta-sucharem" o suchości / o serwisie. Issue #285,
 * parasol #278.
 *
 * Egg „delight" z grupy A zbudowany na fundamencie #282. Nie podpina żadnego
 * własnego globala (poza flagą inicjalizacji `window.__logoSpinReady`):
 * korzysta z `window.easterEggs` dla bramki reduced-motion i z
 * `window.showToast` (project.js) na toast.
 *
 * W przeciwieństwie do konami.js / badumtss.js, których triggerem jest keydown
 * długo po załadowaniu, efekt tego egga może odpalić z `checkAndFire()`
 * WEWNĄTRZ własnego handlera `DOMContentLoaded` (patrz niżej), czyli przed
 * jakimkolwiek późniejszym naciśnięciem klawisza. To wywołanie sięga po
 * `window.showToast`, które project.js definiuje dopiero we własnym handlerze
 * `DOMContentLoaded` — więc ten plik ZALEŻY od tego, że project.js jest w
 * bloku `{% compress js %}` w base.html wcześniej, tak by jego handler (a więc
 * i `showToast`) zarejestrował się i wykonał przed handlerem tego pliku.
 * `showToast` / `easterEggs` i tak są wyszukiwane w chwili wywołania, nigdy
 * przechwytywane przy ładowaniu modułu, więc brakujący helper degeneruje się
 * łagodnie zamiast rzucać wyjątkiem.
 *
 * Ładowany w globalnym bloku `{% compress js %}` w base.html, PO badumtss.js
 * (i, jak wyżej, po project.js).
 * Cały plik to IIFE, żeby jego drobne helpery (`rand`, `STYLE_ID`, …) nie
 * kolidowały na najwyższym poziomie bundla z project.js / easter_eggs.js /
 * konami.js / badumtss.js — kolizja `const` to SyntaxError obejmujący cały
 * bundle (patrz CLAUDE.md i ta sama reguła w konami.js / badumtss.js).
 *
 * Model triggera — DLACZEGO sessionStorage, a nie licznik w pamięci: logo to
 * `<a href="{% url 'home' %}">` i #285 wymaga, by kliknięcie nadal nawigowało
 * na stronę główną, więc każde kliknięcie przeładowuje stronę i żaden stan w
 * pamięci nie przetrwa. `handleLogoClick` zapisuje więc „łańcuch" w
 * sessionStorage — każde kliknięcie w ciągu 3 s od poprzedniego zwiększa
 * `count` — a `checkAndFire`, uruchamiane raz na załadowanie strony, odpala
 * efekt, gdy `count` osiągnął próg, a łańcuch jest wciąż świeży, po czym go
 * czyści. Powtarza się przy każdej nowej serii 7 (celowo nie jednorazowy, jak
 * konami / badumtss).
 *
 * Czysty „delight": ŻADNEGO achievementu, ŻADNEGO slugu frontend-ee-, ŻADNEJ
 * sieci. Korzysta tylko z `easterEggs.reducedJuice()` i `window.showToast`.
 * Pula meta-sucharów to wyspa danych JSON (`#ee-logo-suchary`) emitowana przez
 * base.html dla zalogowanych użytkowników — celowo NIE wewnątrz
 * `{% compress js %}` (#285), żeby jej przetłumaczony tekst nie był
 * minifikowany do bundla.
 */

(function () {
    'use strict';

    // sessionStorage key for the click chain: `{ count, last }`.
    const STORAGE_KEY = 'ee_logo_clicks';
    // Max gap between two clicks that still counts as the same chain.
    const CHAIN_MS = 3000;
    // Extra slack `checkAndFire` allows on top of CHAIN_MS for the page load that
    // follows the 7th click: the click records `last`, then the browser
    // navigates, and on a slow connection the reload itself can eat >CHAIN_MS
    // before `DOMContentLoaded` — without this grace a genuine 7-mash would be
    // discarded as stale on exactly the slow loads it most wants to reward. It
    // still bounds "mash, wander off, navigate much later" (> CHAIN_MS +
    // RELOAD_GRACE_MS since the last click → forgotten).
    const RELOAD_GRACE_MS = 4000;
    // Clicks needed, within one unbroken chain, to fire the effect.
    const CLICK_THRESHOLD = 7;

    const LOGO_SELECTOR = '.navbar-brand';
    const POOL_ELEMENT_ID = 'ee-logo-suchary';

    const STYLE_ID = 'ee-logo-spin-style';
    const SPIN_CLASS = 'ee-logo-spin';
    // Keep in sync with the `600ms` literal in SPIN_CSS; the class is stripped a
    // hair later so the animation is never cut short.
    const SPIN_MS = 600;
    const SPIN_CLEAR_MS = SPIN_MS + 80;

    // One `@keyframes` turn + the class rule that drives it. Injected once as a
    // <style> element — CSP `style-src` allows 'unsafe-inline' (see
    // config/settings/base.py). The nested media query is defence in depth: the
    // JS reduced-motion gate already skips this branch, but if the class is ever
    // added anyway the animation still collapses to nothing.
    const SPIN_CSS =
        '@keyframes ee-logo-spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}'
        + '.ee-logo-spin{animation:ee-logo-spin 600ms ease-in-out}'
        + '@media (prefers-reduced-motion: reduce){.ee-logo-spin{animation:none}}';

    // ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
    let clickHandler = null;
    let boundLogo = null;
    const activeTimers = new Set();

    // Reduced-motion gate. Delegates to the #282 foundation's single check, with
    // a direct-media-query fallback if easter_eggs.js failed to load — a user
    // who asked for reduced motion must not get the spin just because the
    // foundation is missing. Mirrors `easterEggs.reducedJuice()` (reduced when
    // asked, or when the environment can't tell us).
    function prefersReducedMotion() {
        const ee = window.easterEggs;
        if (ee && typeof ee.reducedJuice === 'function') return ee.reducedJuice();
        try {
            if (typeof window.matchMedia !== 'function') return true;
            return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        } catch {
            return true;
        }
    }

    // ── Click-chain persistence ────────────────────────────────────────────────

    function readState() {
        try {
            const raw = sessionStorage.getItem(STORAGE_KEY);
            if (!raw) return { count: 0, last: 0 };
            const parsed = JSON.parse(raw);
            if (
                !parsed
                || typeof parsed.count !== 'number'
                || typeof parsed.last !== 'number'
            ) {
                return { count: 0, last: 0 };
            }
            return { count: parsed.count, last: parsed.last };
        } catch {
            return { count: 0, last: 0 };
        }
    }

    function writeState(state) {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch {
            // Storage unavailable — the egg just won't trigger this session.
        }
    }

    function clearState() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch {
            // Nothing to do.
        }
    }

    // Record one logo click. Ignores non-primary buttons and any chord with a
    // Ctrl/Alt/Meta/Shift modifier (open-in-new-tab / OS shortcuts), which
    // otherwise navigate elsewhere or not at all and shouldn't feed the chain.
    // Never fires the effect: the 7th click navigates home, so `checkAndFire`
    // on the next load is what actually triggers it.
    function handleLogoClick(e) {
        if (e && (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey)) return;
        if (e && typeof e.button === 'number' && e.button !== 0) return;

        const now = Date.now();
        const { count, last } = readState();
        const chained = last > 0 && now - last < CHAIN_MS;
        const next = chained ? Math.min(count + 1, CLICK_THRESHOLD) : 1;
        writeState({ count: next, last: now });
    }

    // Run once per page load. Fires the effect if the chain reached the
    // threshold and its last click is recent enough to still be "this mash" —
    // CHAIN_MS plus RELOAD_GRACE_MS for the reload the 7th click triggered, so
    // mashing the logo then wandering off and navigating much later does not
    // trigger it. Clears a fired or stale chain; leaves a still-building one
    // alone.
    function checkAndFire() {
        const { count, last } = readState();
        if (last === 0) return false;

        const now = Date.now();
        if (now - last >= CHAIN_MS + RELOAD_GRACE_MS) {
            clearState();
            return false;
        }
        if (count >= CLICK_THRESHOLD) {
            clearState();
            triggerLogoSpin();
            return true;
        }
        return false;
    }

    // ── Effect ────────────────────────────────────────────────────────────────

    function ensureKeyframes() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = SPIN_CSS;
        document.head.appendChild(style);
    }

    function spinLogo() {
        const logo = document.querySelector(LOGO_SELECTOR);
        if (!logo) return;

        ensureKeyframes();
        logo.classList.add(SPIN_CLASS);

        const id = setTimeout(() => {
            activeTimers.delete(id);
            logo.classList.remove(SPIN_CLASS);
        }, SPIN_CLEAR_MS);
        activeTimers.add(id);
    }

    // Random entry from the JSON data island, or null when it is absent /
    // empty / unparseable (the spin still runs; only the toast is skipped).
    function pickMetaSuchar() {
        const el = document.getElementById(POOL_ELEMENT_ID);
        if (!el) return null;
        try {
            const pool = JSON.parse(el.textContent);
            if (!Array.isArray(pool) || pool.length === 0) return null;
            return pool[Math.floor(Math.random() * pool.length)];
        } catch {
            return null;
        }
    }

    function triggerLogoSpin() {
        const text = pickMetaSuchar();
        if (text && typeof window.showToast === 'function') {
            window.showToast(text, '🌀', 'info');
        }
        if (!prefersReducedMotion()) spinLogo();
    }

    function teardownLogoSpin() {
        if (clickHandler && boundLogo) {
            boundLogo.removeEventListener('click', clickHandler);
        }
        clickHandler = null;
        boundLogo = null;
        activeTimers.forEach((id) => clearTimeout(id));
        activeTimers.clear();
        const style = document.getElementById(STYLE_ID);
        if (style) style.remove();
        document.querySelectorAll(`.${SPIN_CLASS}`).forEach((el) => {
            el.classList.remove(SPIN_CLASS);
        });
        clearState();
    }

    // ── Init ─────────────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        try {
            if (document.body.dataset.userIsAuthenticated !== 'true') return;

            const logo = document.querySelector(LOGO_SELECTOR);
            if (logo) {
                clickHandler = handleLogoClick;
                boundLogo = logo;
                // Not preventDefault: the click must still navigate home (#285).
                logo.addEventListener('click', clickHandler);
            }

            checkAndFire();

            const ee = window.easterEggs;
            if (ee && typeof ee.registerTeardown === 'function') {
                ee.registerTeardown('logoSpin', teardownLogoSpin);
            }
        } finally {
            // Init-complete signal, mirroring window.__konamiReady /
            // window.__baDumTssReady. The E2E test waits on it before clicking
            // (page `load` isn't synced with bundle execution).
            window.__logoSpinReady = true;
        }
    });

    /* Test-only export for Vitest + jsdom (tests/js/logo_spin.test.js).
     * `module` is undefined in the browser, so this tail is inert there and is
     * kept verbatim by rjsmin inside {% compress js %} — NOT dead code (see
     * CLAUDE.md "JS tests (Vitest)" and the same pattern in konami.js /
     * badumtss.js).
     *
     * `vi.resetModules()` does not re-run a required CJS module, so this
     * module's mutable state (the bound click listener, the spin timers)
     * survives between tests. `_resetForTests()` is the per-test reset the
     * `beforeEach` must call; it is attached here only, so it never reaches a
     * real browser. */
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            STORAGE_KEY,
            CHAIN_MS,
            CLICK_THRESHOLD,
            handleLogoClick,
            checkAndFire,
            triggerLogoSpin,
            spinLogo,
            pickMetaSuchar,
            teardownLogoSpin,
            _resetForTests: teardownLogoSpin,
        };
    }
})();
