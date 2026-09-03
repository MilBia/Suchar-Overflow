/* Hidden frontend achievements tracker.
 * Only runs for authenticated users. Fetches already-owned slugs on init
 * and skips monitors for achievements the user already has.
 * Relies on window.getCsrfToken, defined in project.js (loaded first).
 */

async function getOwnedSlugs() {
    try {
        const resp = await fetch('/api/achievements/frontend-owned');
        if (!resp.ok) return [];
        return await resp.json();
    } catch {
        return [];
    }
}

async function awardAchievement(slug) {
    try {
        await fetch('/api/achievements/frontend-event', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({ event_slug: slug }),
        });
    } catch {
        // Silent fail — user will get another chance next session.
    }
}

// Guard against double-award within the same page session (e.g. rapid threshold hits).
function award(slug, teardownRegistry) {
    if (sessionStorage.getItem('awarded_' + slug)) return;
    sessionStorage.setItem('awarded_' + slug, '1');

    const teardown = teardownRegistry[slug];
    if (teardown) teardown();

    awardAchievement(slug);
}

// ── Achievement 1: Recenzent Totalny ────────────────────────────────────────
// Trigger: hover 20 different suchar cards for 3+ seconds each.
function setupRecenzentTotalny(teardownRegistry) {
    const SLUG = 'frontend-recenzent-totalny';
    if (document.querySelectorAll('.card.suchar-card').length === 0) return;

    // Delegated on `document` (one pair of listeners instead of two per card).
    // `mouseenter`/`mouseleave` don't bubble, so use `mouseover`/`mouseout` and
    // ignore transitions that stay within the same card via `relatedTarget`.
    // Cards have no stable id of their own, so dedupe by the element itself —
    // one card == one suchar on the list, so this matches the old id-based set.
    const hovered = new Set();  // card elements that completed a 3s dwell
    const timers = new Map();   // card element -> pending timeout id

    const onOver = (e) => {
        const card = e.target.closest('.card.suchar-card');
        if (!card || card.contains(e.relatedTarget)) return;
        if (hovered.has(card) || timers.has(card)) return;

        timers.set(card, setTimeout(() => {
            timers.delete(card);
            hovered.add(card);
            if (hovered.size >= 20) {
                award(SLUG, teardownRegistry);
            }
        }, 3000));
    };
    const onOut = (e) => {
        const card = e.target.closest('.card.suchar-card');
        if (!card || card.contains(e.relatedTarget)) return;
        clearTimeout(timers.get(card));
        timers.delete(card);
    };

    document.addEventListener('mouseover', onOver);
    document.addEventListener('mouseout', onOut);

    teardownRegistry[SLUG] = () => {
        document.removeEventListener('mouseover', onOver);
        document.removeEventListener('mouseout', onOut);
        timers.forEach(t => clearTimeout(t));
        timers.clear();
    };
}

// ── Achievement 2: Stłuczona Mysz ───────────────────────────────────────────
// Trigger: click vote buttons on the same suchar 5+ times (indecisive voter).
function setupStluczonaMysz(teardownRegistry) {
    const SLUG = 'frontend-stluczona-mysz';
    if (document.querySelectorAll('.btn-vote').length === 0) return;

    const clicks = new Map();

    const onClick = (e) => {
        const btn = e.target.closest('.btn-vote[data-suchar-id]');
        if (!btn) return;
        const sucharId = btn.dataset.sucharId;
        if (!sucharId) return;

        const count = (clicks.get(sucharId) || 0) + 1;
        clicks.set(sucharId, count);
        if (count >= 5) {
            award(SLUG, teardownRegistry);
        }
    };

    document.addEventListener('click', onClick);
    teardownRegistry[SLUG] = () => document.removeEventListener('click', onClick);
}

// ── Achievement 3: Zbieracz Sucharów ────────────────────────────────────────
// Trigger: navigate through 5 suchar list pages without casting a vote.
// Uses sessionStorage so the counter resets when the browser session ends.
function setupZbieraczSucharow(teardownRegistry) {
    const SLUG = 'frontend-zbieracz-sucharow';
    const PAGE_KEY = 'zbieracz_pages';

    // Reset counter on any vote-button click during this page load. Unlike
    // Stłuczona Mysz this doesn't require a data-suchar-id — any `.btn-vote`.
    const onVote = (e) => {
        if (e.target.closest('.btn-vote')) {
            sessionStorage.setItem(PAGE_KEY, '0');
        }
    };
    document.addEventListener('click', onVote);
    // Registered before the early return below, matching the original.
    teardownRegistry[SLUG] = () => document.removeEventListener('click', onVote);

    if (!window.location.pathname.startsWith('/suchary')) return;

    // Don't count this visit if a vote was cast before leaving the page.
    // We track that via the reset above — if voted, counter is already 0.
    const current = parseInt(sessionStorage.getItem(PAGE_KEY) || '0', 10) + 1;
    sessionStorage.setItem(PAGE_KEY, String(current));

    if (current >= 5) {
        sessionStorage.removeItem(PAGE_KEY);
        award(SLUG, teardownRegistry);
    }
}

// ── Achievement 4: Niecierpliwy ──────────────────────────────────────────────
// Trigger: try to submit the suchar form with fewer than 10 characters 3 times.
function setupNiecierpliwy(teardownRegistry) {
    const textarea = document.getElementById('id_text');
    if (!textarea) return;

    const form = textarea.closest('form');
    if (!form) return;

    const KEY = 'niecierpliwy_count';

    const onSubmit = () => {
        if (textarea.value.trim().length < 10) {
            const count = parseInt(sessionStorage.getItem(KEY) || '0', 10) + 1;
            sessionStorage.setItem(KEY, String(count));
            if (count >= 3) {
                sessionStorage.removeItem(KEY);
                award('frontend-niecierpliwy', teardownRegistry);
            }
        }
    };

    form.addEventListener('submit', onSubmit);
    teardownRegistry['frontend-niecierpliwy'] = () => {
        form.removeEventListener('submit', onSubmit);
    };
}

// ── Achievement 5: Odkrywca ──────────────────────────────────────────────────
// Trigger: visit the achievements list page 5 times.
// Uses localStorage so visits accumulate across sessions.
function setupOdkrywca(teardownRegistry) {
    // Match /achievements/ but not /achievements/inbox or /achievements/stream.
    const path = window.location.pathname;
    const isAchievementsListPage = (
        path === '/achievements/' ||
        path === '/achievements'
    );
    if (!isAchievementsListPage) return;

    const KEY = 'odkrywca_visits';
    const count = parseInt(localStorage.getItem(KEY) || '0', 10) + 1;
    localStorage.setItem(KEY, String(count));

    if (count >= 5) {
        localStorage.removeItem(KEY);
        award('frontend-odkrywca', teardownRegistry);
    }

    teardownRegistry['frontend-odkrywca'] = () => {};
}

// ── Init ─────────────────────────────────────────────────────────────────────
// The monitors below are all gated behind an `await` (getOwnedSlugs), so their
// listeners/counters don't exist until that fetch resolves. `window.__hidden
// AchievementsReady` flips to true once init has fully finished — E2E tests wait
// on it instead of a load-state heuristic, which isn't synced with this fetch
// (see issue #221). Mirrors the window.getCsrfToken / window.showToast exports
// in project.js. The `finally` guarantees the flag is set even if a setupX()
// throws synchronously, so tests fail fast on the real error instead of hanging
// on the readiness wait.
document.addEventListener('DOMContentLoaded', async () => {
    try {
        if (document.body.dataset.userIsAuthenticated !== 'true') return;

        const owned = await getOwnedSlugs();
        const teardownRegistry = {};

        if (!owned.includes('frontend-recenzent-totalny')) {
            setupRecenzentTotalny(teardownRegistry);
        }
        if (!owned.includes('frontend-stluczona-mysz')) {
            setupStluczonaMysz(teardownRegistry);
        }
        if (!owned.includes('frontend-zbieracz-sucharow')) {
            setupZbieraczSucharow(teardownRegistry);
        }
        if (!owned.includes('frontend-niecierpliwy')) {
            setupNiecierpliwy(teardownRegistry);
        }
        if (!owned.includes('frontend-odkrywca')) {
            setupOdkrywca(teardownRegistry);
        }
    } finally {
        window.__hiddenAchievementsReady = true;
    }
});

/* Test-only export for Vitest + jsdom (tests/js/hidden_achievements.test.js).
 * `module` is undefined in the browser, so this block is inert there and is
 * preserved verbatim by rjsmin inside {% compress js %}. It is NOT dead code —
 * do not remove it in a JS sweep (cf. window.__hiddenAchievementsReady above).
 * See CLAUDE.md "JS tests (Vitest)". */
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        award,
        awardAchievement,
        getOwnedSlugs,
        setupRecenzentTotalny,
        setupStluczonaMysz,
        setupZbieraczSucharow,
        setupNiecierpliwy,
        setupOdkrywca,
    };
}
