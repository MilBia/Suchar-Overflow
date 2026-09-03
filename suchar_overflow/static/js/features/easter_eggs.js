/* Easter-egg foundation (issue #282, umbrella #278).
 *
 * Shared groundwork every "delight" easter egg in group A builds on, so the
 * children (#283+) don't each re-implement CSRF fetch, session dedupe, the
 * reduced-motion gate or sound playback. This file wires up NO easter egg of
 * its own — it only exposes `window.easterEggs`.
 *
 * Loaded in base.html's global `{% compress js %}` block, AFTER project.js
 * (needs `window.getCsrfToken`; children also use `window.showToast`, which
 * project.js only defines inside its own DOMContentLoaded handler — so read it
 * from an event handler, never at module load time). Because that block is
 * global, this runs before every per-page bundle, which is why
 * features/hidden_achievements.js can rely on `window.easterEggs` being set.
 *
 * Relies on `window.getCsrfToken` (project.js) and, for sound, on
 * `window.EE_AUDIO` (a tiny nonce'd inline map of `{% static %}` URLs emitted by
 * base.html for authenticated users — a classic script can't resolve `{% static %}`
 * itself, and production hashes the filenames).
 */

// ── Frontend-achievement helpers (shared with hidden_achievements.js) ─────────

function awardedKey(slug) {
    return 'awarded_' + slug;
}

// Guard against double-award within the same page session (rapid re-triggers,
// or a second listener for the same slug). Storage can throw in private mode —
// treat any failure as "not yet awarded" so the POST still gets a chance.
function alreadyAwarded(slug) {
    try {
        return sessionStorage.getItem(awardedKey(slug)) === '1';
    } catch {
        return false;
    }
}

function markAwarded(slug) {
    try {
        sessionStorage.setItem(awardedKey(slug), '1');
    } catch {
        // No session storage (private mode) — the in-memory listener guards in
        // each egg still prevent a tight double-fire within one page load.
    }
}

function awardFrontendAchievement(slug) {
    try {
        return fetch('/api/achievements/frontend-event', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ event_slug: slug }),
        }).catch(() => {
            // Silent fail — user gets another chance next session.
        });
    } catch {
        return Promise.resolve();
    }
}

// Convenience: dedupe + POST in one call. Returns true on the first award for
// this slug in the session, false if it was already awarded. Children that also
// want an immediate toast call `window.showToast` themselves after this.
function award(slug) {
    if (alreadyAwarded(slug)) return false;
    markAwarded(slug);
    awardFrontendAchievement(slug);
    return true;
}

// ── Mute preference (localStorage `ee_muted`, DEFAULT MUTED) ──────────────────

const MUTE_KEY = 'ee_muted';

// Muted unless the user has explicitly opted in (`ee_muted === '0'`). Any
// storage failure also reads as muted, so a broken storage never makes noise.
function isMuted() {
    try {
        return localStorage.getItem(MUTE_KEY) !== '0';
    } catch {
        return true;
    }
}

function setMuted(muted) {
    try {
        localStorage.setItem(MUTE_KEY, muted ? '1' : '0');
    } catch {
        // Nothing we can do; the getter still defaults to muted.
    }
}

// ── Sound helper ─────────────────────────────────────────────────────────────

const audioCache = {};

// Play a named cue (`rimshot`, `dust`). No-op when muted, when the URL map is
// absent, or when the browser blocks autoplay — a missed sound effect is never
// worth an error.
function playSound(name) {
    if (isMuted()) return;

    const urls = (typeof window !== 'undefined' && window.EE_AUDIO) || null;
    if (!urls || !urls[name]) return;

    try {
        let el = audioCache[name];
        if (!el) {
            el = new Audio(urls[name]);
            el.preload = 'auto';
            audioCache[name] = el;
        }
        el.currentTime = 0;
        const played = el.play();
        if (played && typeof played.catch === 'function') {
            played.catch(() => {});
        }
    } catch {
        // Audio unavailable / autoplay blocked.
    }
}

// ── Animation gate ───────────────────────────────────────────────────────────

// True when animations should be suppressed: the user asked for reduced motion,
// or the environment can't tell us (no `matchMedia`) — in which case we err on
// the calm side.
function reducedJuice() {
    try {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return true;
        }
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch {
        return true;
    }
}

// Run `fn` only when full "juice" is allowed. Children pass their confetti /
// shake / bounce here so the reduced-motion check lives in exactly one place.
function withJuice(fn) {
    if (reducedJuice()) return;
    fn();
}

// ── Teardown registry ────────────────────────────────────────────────────────

// Children register a detach callback under a unique key. `vi.resetModules()`
// does NOT remove listeners a child added to `document`, so a test that attaches
// key-buffer / combo handlers must call `teardownAll()` to leave `document`
// clean for the next test (see CLAUDE.md "JS tests (Vitest)"). Harmless in the
// browser, where the page only unloads once.
const teardownRegistry = {};

function registerTeardown(key, fn) {
    teardownRegistry[key] = fn;
}

function teardownAll() {
    Object.keys(teardownRegistry).forEach((key) => {
        const fn = teardownRegistry[key];
        if (typeof fn === 'function') fn();
        delete teardownRegistry[key];
    });
}

// ── Public surface ───────────────────────────────────────────────────────────

const easterEggs = {
    awardFrontendAchievement,
    alreadyAwarded,
    markAwarded,
    award,
    isMuted,
    setMuted,
    playSound,
    reducedJuice,
    withJuice,
    registerTeardown,
    teardownAll,
};

if (typeof window !== 'undefined') {
    window.easterEggs = easterEggs;
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    try {
        if (document.body.dataset.userIsAuthenticated !== 'true') return;
        // Foundation only (#282): nothing is wired up here. Group-A children
        // (#283+) attach their listeners in their own feature files using
        // `window.easterEggs.*` and `registerTeardown()`.
    } finally {
        // Init-complete signal, mirroring window.__hiddenAchievementsReady. A
        // child (#283+) that attaches listeners after an awaited fetch will need
        // it as a sync point the `load` event can't provide (cf. #221); until
        // then tests/js/easter_eggs.test.js is its only reader. Asserted there —
        // NOT dead code, keep it in a sweep.
        window.__easterEggsReady = true;
    }
});

/* Test-only export for Vitest + jsdom (tests/js/easter_eggs.test.js).
 * `module` is undefined in the browser, so this block is inert there and is
 * preserved verbatim by rjsmin inside {% compress js %}. NOT dead code — see
 * CLAUDE.md "JS tests (Vitest)" and the same tail in hidden_achievements.js. */
if (typeof module !== 'undefined' && module.exports) {
    module.exports = easterEggs;
}
