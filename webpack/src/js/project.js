// The global entry (#468): everything base.html used to load as classic scripts in one
// {% compress js %} block, imported in the same order — the initialisation order is the order of
// these lines (ES modules evaluate depth-first, in import order), and each module registers its own
// `DOMContentLoaded` listener when evaluated, so listener order is preserved too.
import '../scss/project.scss';

// First: it writes the `user_tz` cookie and wraps `document.cookie` in try/catch, so a blocked
// cookie store cannot stop the modules after it.
import './timezone.js';
import './app.js';
import './features/easter_eggs.js';
import './features/konami.js';
import './features/badumtss.js';
import './features/logo_spin.js';
import './features/console_egg.js';
import './features/tumbleweed.js';
import './features/theme_spam.js';
import './features/archeolog.js';
import './features/publika_rozgrzana.js';
