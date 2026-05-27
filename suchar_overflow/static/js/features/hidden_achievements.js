/* Hidden frontend achievements tracker.
 * Only runs for authenticated users. Fetches already-owned slugs on init
 * and skips monitors for achievements the user already has.
 */

function getCsrfToken() {
    return (
        document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
        document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
        ''
    );
}

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
    const cards = document.querySelectorAll('.card.suchar-card');
    if (cards.length === 0) return;

    const hovered = new Set();
    const timers = new Map();
    const listeners = [];

    cards.forEach((card, idx) => {
        // Cards have no own data-suchar-id; read it from the child vote button.
        const btn = card.querySelector('.btn-vote[data-suchar-id]');
        const id = btn ? btn.dataset.sucharId : String(idx);

        const onEnter = () => {
            if (hovered.has(id)) return;
            timers.set(id, setTimeout(() => {
                hovered.add(id);
                if (hovered.size >= 20) {
                    award('frontend-recenzent-totalny', teardownRegistry);
                }
            }, 3000));
        };
        const onLeave = () => {
            clearTimeout(timers.get(id));
            timers.delete(id);
        };

        card.addEventListener('mouseenter', onEnter);
        card.addEventListener('mouseleave', onLeave);
        listeners.push({ el: card, onEnter, onLeave });
    });

    teardownRegistry['frontend-recenzent-totalny'] = () => {
        listeners.forEach(({ el, onEnter, onLeave }) => {
            el.removeEventListener('mouseenter', onEnter);
            el.removeEventListener('mouseleave', onLeave);
        });
        timers.forEach(t => clearTimeout(t));
        timers.clear();
    };
}

// ── Achievement 2: Stłuczona Mysz ───────────────────────────────────────────
// Trigger: click vote buttons on the same suchar 5+ times (indecisive voter).
function setupStluczonaMysz(teardownRegistry) {
    const btns = document.querySelectorAll('.btn-vote');
    if (btns.length === 0) return;

    const clicks = new Map();
    const listeners = [];

    btns.forEach(btn => {
        const sucharId = btn.dataset.sucharId;
        if (!sucharId) return;

        const onClick = () => {
            const count = (clicks.get(sucharId) || 0) + 1;
            clicks.set(sucharId, count);
            if (count >= 5) {
                award('frontend-stluczona-mysz', teardownRegistry);
            }
        };
        btn.addEventListener('click', onClick);
        listeners.push({ el: btn, onClick });
    });

    teardownRegistry['frontend-stluczona-mysz'] = () => {
        listeners.forEach(({ el, onClick }) => el.removeEventListener('click', onClick));
    };
}

// ── Achievement 3: Zbieracz Sucharów ────────────────────────────────────────
// Trigger: navigate through 5 suchar list pages without casting a vote.
// Uses sessionStorage so the counter resets when the browser session ends.
function setupZbieraczSucharow(teardownRegistry) {
    const PAGE_KEY = 'zbieracz_pages';
    const VOTED_KEY = 'zbieracz_voted';

    // Reset counter on any vote action during this page load.
    const btns = document.querySelectorAll('.btn-vote');
    const listeners = [];
    btns.forEach(btn => {
        const onVote = () => sessionStorage.setItem(PAGE_KEY, '0');
        btn.addEventListener('click', onVote);
        listeners.push({ el: btn, onVote });
    });

    teardownRegistry['frontend-zbieracz-sucharow'] = () => {
        listeners.forEach(({ el, onVote }) => el.removeEventListener('click', onVote));
    };

    if (!window.location.pathname.startsWith('/suchary')) return;

    // Don't count this visit if a vote was cast before leaving the page.
    // We track that via the reset above — if voted, counter is already 0.
    const current = parseInt(sessionStorage.getItem(PAGE_KEY) || '0', 10) + 1;
    sessionStorage.setItem(PAGE_KEY, String(current));

    if (current >= 5) {
        sessionStorage.removeItem(PAGE_KEY);
        award('frontend-zbieracz-sucharow', teardownRegistry);
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
document.addEventListener('DOMContentLoaded', async () => {
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
});
