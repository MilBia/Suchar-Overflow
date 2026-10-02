/* Easter egg: wpisz "suchar" / "badumtss" / "ba dum tss" → toast 🥁 + obłoczek
 * opadającego kurzu. Issue #284, parasol #278.
 *
 * Egg „delight" z grupy A zbudowany na fundamencie #282. Nie podpina żadnego
 * własnego globala (poza flagą inicjalizacji `window.__baDumTssReady`):
 * korzysta z `easterEggs` dla bramki reduced-motion i wyciszonego domyślnie
 * helpera dźwięku, oraz z `showToast` (toast.js) na toast.
 *
 * Moduł ES (#468), importowany przez wpis `project` (webpack/src/js/project.js) po
 * konami.js, więc trigger nasłuchuje na każdej stronie dla zalogowanego
 * użytkownika. `easterEggs` i `showToast` są importowane wprost i używane w
 * chwili triggera.
 *
 * Czysty „delight": ŻADNEGO achievementu, ŻADNEGO slugu frontend-ee-, ŻADNEJ
 * sieci. Efekt powtarza się przy każdym wpisaniu (jak konami, celowo nie
 * jednorazowy):
 *   - pełny ruch: ~24 drobinki kurzu opadające przez viewport, ~2 s;
 *   - prefers-reduced-motion: sam toast, żadnego overlaya;
 *   - toast „🥁 / ba dum tss";
 *   - sygnał rimshot przez `easterEggs.playSound` (wyciszony, jeśli nie
 *     włączono go świadomie).
 */
import { showToast } from '../toast.js';
import { easterEggs } from './easter_eggs.js';

// Literal suffixes to match against the tail of the typed-key buffer. Spaces
// are ordinary single-character keys, so "ba dum tss" is matched verbatim.
const PHRASES = ['suchar', 'badumtss', 'ba dum tss'];
const LONGEST_PHRASE = PHRASES.reduce((n, p) => Math.max(n, p.length), 0);

// Idle timeout after which a half-typed phrase is forgotten, so "sucha" now
// and "r" a minute later don't combine into a hit.
const IDLE_MS = 2000;

const STYLE_ID = 'ee-badumtss-style';
const OVERLAY_CLASS = 'ee-dust-overlay';
const DUST_PARTICLES = 24;
// Per-mote animation bounds. The overlay must outlive the last mote or motes
// vanish mid-fall (cf. konami: lifetime ≥ maxDelay + maxDuration), so keep
// `MOTE_MAX_DELAY_S + MOTE_MAX_DURATION_S <= OVERLAY_LIFETIME_MS / 1000`.
const MOTE_MIN_DURATION_S = 1.2;
const MOTE_MAX_DURATION_S = 1.7;
const MOTE_MAX_DELAY_S = 0.4;
const OVERLAY_LIFETIME_MS = 2200;

// `@keyframes` for the drifting motes. Injected once as a <style> element —
// CSP `style-src` allows 'unsafe-inline' (see config/settings/base.py),
// which covers both this block and the per-particle inline `style=` below.
const DRIFT_KEYFRAMES =
    '@keyframes ee-badumtss-drift{' +
    '0%{transform:translate(0,-8vh) scale(0.5);opacity:0}' +
    '15%{opacity:0.75}' +
    '100%{transform:translate(var(--ee-dx,0),108vh) scale(1);opacity:0}' +
    '}';

// ── Module-level mutable state (reset between Vitest tests via _resetForTests) ─
// A bounded string of the last few typed characters. Comparing its tail with
// each phrase is O(1) and immune to any junk or repeated prefix.
let charBuffer = '';
let idleTimer = null;
let keydownHandler = null;
const activeTimers = new Set();
const activeOverlays = new Set();

function rand(min, max) {
    return min + Math.random() * (max - min);
}

function clearBuffer() {
    charBuffer = '';
    if (idleTimer !== null) {
        clearTimeout(idleTimer);
        idleTimer = null;
    }
}

function armIdleClear() {
    if (idleTimer !== null) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
        idleTimer = null;
        charBuffer = '';
    }, IDLE_MS);
}

// ── Dust overlay ────────────────────────────────────────────────────────────

function ensureKeyframes() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = DRIFT_KEYFRAMES;
    document.head.appendChild(style);
}

function makeOverlay() {
    const overlay = document.createElement('div');
    overlay.className = OVERLAY_CLASS;
    overlay.setAttribute('aria-hidden', 'true');
    // Set property-by-property (not `cssText`): jsdom's CSSOM silently drops
    // custom properties and some shorthands set through `cssText`, and the
    // per-particle styles below rely on `--ee-dx`.
    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    overlay.style.pointerEvents = 'none';
    overlay.style.overflow = 'hidden';
    overlay.style.zIndex = '2147483000';
    return overlay;
}

function makeMote() {
    const mote = document.createElement('div');
    const size = rand(4, 10).toFixed(1);
    mote.style.position = 'absolute';
    mote.style.top = '0';
    mote.style.left = `${rand(-2, 98).toFixed(1)}%`;
    mote.style.width = `${size}px`;
    mote.style.height = `${size}px`;
    mote.style.borderRadius = '50%';
    // Warm mid-grey at high alpha + a soft glow so the motes read as dust on
    // both the light and dark themes (konami's crackers are opaque for the
    // same reason). Deliberately not theme-aware — one calm tone for both.
    mote.style.background = 'rgba(146, 128, 104, 0.85)';
    mote.style.boxShadow = '0 0 3px rgba(120, 104, 82, 0.7)';
    mote.style.setProperty('--ee-dx', `${rand(-10, 10).toFixed(1)}vw`);
    mote.style.animationName = 'ee-badumtss-drift';
    mote.style.animationDuration = `${rand(MOTE_MIN_DURATION_S, MOTE_MAX_DURATION_S).toFixed(2)}s`;
    mote.style.animationTimingFunction = 'ease-in';
    mote.style.animationDelay = `${rand(0, MOTE_MAX_DELAY_S).toFixed(2)}s`;
    mote.style.animationFillMode = 'both';
    return mote;
}

function scheduleRemoval(overlay, ms) {
    const id = setTimeout(() => {
        activeTimers.delete(id);
        activeOverlays.delete(overlay);
        overlay.remove();
    }, ms);
    activeTimers.add(id);
}

// Full-motion only — the reduced-motion branch never calls this.
function dustBurst() {
    ensureKeyframes();
    const overlay = makeOverlay();
    for (let i = 0; i < DUST_PARTICLES; i += 1) {
        overlay.appendChild(makeMote());
    }
    document.body.appendChild(overlay);
    activeOverlays.add(overlay);
    scheduleRemoval(overlay, OVERLAY_LIFETIME_MS);
}

function showBaDumTssToast() {
    showToast('ba dum tss', '🥁', 'success');
}

function triggerBaDumTss() {
    showBaDumTssToast();

    easterEggs.playSound('rimshot');

    if (!easterEggs.reducedJuice()) dustBurst();
}

// Push the key into the bounded buffer and fire when its tail matches a
// phrase. Ignores keystrokes typed into a form field (so a phrase can't be
// swallowed mid-edit, nor fired from one) and any chord with a Ctrl/Alt/Meta
// modifier (browser/OS shortcuts such as Ctrl+A, Alt+←).
function handleKeydown(e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;

    const target = e.target;
    if (
        target &&
        (target.tagName === 'INPUT' ||
            target.tagName === 'TEXTAREA' ||
            target.tagName === 'SELECT' ||
            target.isContentEditable)
    ) {
        return;
    }

    // Only printable single-character keys extend the buffer; "Shift",
    // "ArrowLeft", "Enter" etc. are inert (they also don't break a phrase).
    if (typeof e.key !== 'string' || e.key.length !== 1) return;

    charBuffer = (charBuffer + e.key.toLowerCase()).slice(-LONGEST_PHRASE);
    armIdleClear();

    if (PHRASES.some((phrase) => charBuffer.endsWith(phrase))) {
        clearBuffer();
        triggerBaDumTss();
    }
}

function teardownBaDumTss() {
    if (keydownHandler) {
        document.removeEventListener('keydown', keydownHandler);
        keydownHandler = null;
    }
    activeTimers.forEach((id) => clearTimeout(id));
    activeTimers.clear();
    activeOverlays.forEach((el) => el.remove());
    activeOverlays.clear();
    const style = document.getElementById(STYLE_ID);
    if (style) style.remove();
    clearBuffer();
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    try {
        if (document.body.dataset.userIsAuthenticated !== 'true') return;

        keydownHandler = handleKeydown;
        document.addEventListener('keydown', keydownHandler);

        easterEggs.registerTeardown('badumtss', teardownBaDumTss);
    } finally {
        // Init-complete signal, mirroring window.__konamiReady /
        // window.__easterEggsReady. The E2E test waits on it before typing
        // (page `load` isn't synced with bundle execution).
        window.__baDumTssReady = true;
    }
});

/* Per-test reset (tests/js/badumtss.test.js): detaches the listener, clears timers, overlays,
 * <style> and the char buffer. Module export only — never reaches `window`. NOT dead code, see
 * CLAUDE.md "JS tests (Vitest)". */
export function _resetForTests() {
    teardownBaDumTss();
}

export { PHRASES, handleKeydown, triggerBaDumTss, dustBurst, showBaDumTssToast, teardownBaDumTss };
