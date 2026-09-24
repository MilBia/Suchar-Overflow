/* Strefa czasowa przeglądarki → cookie `user_tz` (issue #410, etap 2 #405).
 *
 * Serwer (`suchar_overflow/middleware.py`) aktywuje tę strefę dla żądania —
 * wyłącznie do interpretacji wejścia (godzina planowania suchara) i
 * wyświetlania dat. Reguły osiągnięć, konkursy, wykresy i heatmapa zostają przy
 * strefie serwisu (`TIME_ZONE`), niezależnie od cookie.
 *
 * Działa dla KAŻDEGO odwiedzającego, także niezalogowanego (bez bramki
 * `userIsAuthenticated`, w przeciwieństwie do easter eggów). Pierwsze
 * wejście renderuje się jeszcze w strefie serwisu; od następnego żądania
 * obowiązuje strefa przeglądarki. Cookie jest zapisywane tylko przy zmianie
 * wartości (np. po podróży), żeby nie przepisywać go przy każdej stronie.
 *
 * Wartość idzie do cookie surowa: nazwy IANA (`Europe/Warsaw`,
 * `America/Argentina/Buenos_Aires`, `Etc/GMT+5`) składają się wyłącznie ze
 * znaków dozwolonych w wartości cookie, a serwer i tak przyjmuje tylko
 * dokładny klucz z bazy stref.
 *
 * Cały plik to IIFE (brak kolizji `const` w globalnym bundlu
 * `{% compress js %}`), z chronionym ogonem CommonJS dla Vitesta.
 */

(function () {
    'use strict';

    const COOKIE_NAME = 'user_tz';
    const MAX_AGE_SECONDS = 365 * 24 * 60 * 60;

    function browserTimeZone() {
        try {
            const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
            return typeof zone === 'string' && zone ? zone : null;
        } catch {
            return null;
        }
    }

    function readCookie() {
        const prefix = COOKIE_NAME + '=';
        for (const part of document.cookie.split(';')) {
            const trimmed = part.trim();
            if (trimmed.startsWith(prefix)) return trimmed.slice(prefix.length);
        }
        return null;
    }

    function buildCookie(zone, secure) {
        let cookie = COOKIE_NAME + '=' + zone
            + '; path=/; max-age=' + MAX_AGE_SECONDS + '; SameSite=Lax';
        if (secure) cookie += '; Secure';
        return cookie;
    }

    function syncTimezoneCookie() {
        const zone = browserTimeZone();
        if (!zone) return false;
        // `document.cookie` throws a SecurityError when cookies are blocked
        // (strict privacy settings, sandboxed iframe). This is the first script
        // of the shared global bundle, so an uncaught throw here would stop
        // every script after it — fall back to the service zone instead.
        try {
            if (readCookie() === zone) return false;
            document.cookie = buildCookie(zone, window.location.protocol === 'https:');
            return true;
        } catch {
            return false;
        }
    }

    syncTimezoneCookie();

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            COOKIE_NAME,
            browserTimeZone,
            buildCookie,
            readCookie,
            syncTimezoneCookie,
        };
    }
})();
