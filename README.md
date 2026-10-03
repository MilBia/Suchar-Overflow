# 🌵 Suchar Overflow

Agregator żartów o krytycznie niskim poziomie wilgotności.
Wchodzisz na własną odpowiedzialność (i z butelką wody).

[![CI](https://github.com/MilBia/Suchar-Overflow/actions/workflows/ci.yml/badge.svg)](https://github.com/MilBia/Suchar-Overflow/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.2-blue.svg)](<>)

---

## Spis treści

- [O projekcie](#o-projekcie)
- [Technologie](#technologie)
- [Wymagania](#wymagania)
- [Uruchomienie lokalne](#uruchomienie-lokalne)
- [Uruchomienie na produkcji](#uruchomienie-na-produkcji)
- [Architektura produkcji](#architektura-produkcji)
- [Zmienne środowiskowe](#zmienne-środowiskowe)
- [Operacje](#operacje)
- [Przydatne komendy](#przydatne-komendy)
- [Tłumaczenia AI](#tłumaczenia-ai-fill_translations)
- [Struktura projektu](#struktura-projektu)
- [Testy](#testy)
- [Dev Container](#dev-container)
- [Pre-commit](#pre-commit)
- [Licencja](#licencja)

---

## O projekcie

Suchar Overflow to platforma do dzielenia się żartami (sucharami) – z systemem głosowania,
rankingiem użytkowników, osiągnięciami i statystykami. Projekt wspiera dwa języki
(polski i angielski), wysyła maile przez kolejkę zadań (RQ) oraz obsługuje
cykliczne zadania (np. przyznawanie osiągnięć) w osobnej usłudze `cron`.

### Główne funkcje

- 📝 **Dodawanie i przeglądanie żartów** – z paginacją i sortowaniem
- 👍👎 **System głosowania** – oceniaj suchary (i obserwuj jak lecą w dół)
- 🏆 **Ranking / Leaderboard** – najlepsi twórcy sucharów
- 🎖️ **Osiągnięcia** – system achievement'ów z ukrytymi odznaczeniami i skrzynką powiadomień
- 📊 **Statystyki** – wykresy aktywności użytkowników
- 📬 **Maile transakcyjne** – aktywacja konta i zmiana e-maila (Django mail backend)
- 🌙 **Dark / Light mode** – przełączanie motywu
- 🌍 **Internationalizacja** – pełne wsparcie PL / EN

---

## Technologie

| Warstwa                       | Technologia                                               |
| ----------------------------- | --------------------------------------------------------- |
| **Język**                     | Python 3.14                                               |
| **Framework**                 | Django 6.1                                                |
| **REST API**                  | Django Ninja                                              |
| **Baza danych**               | PostgreSQL 18                                             |
| **Cache**                     | Redis 8 (django-redis)                                    |
| **Kolejka i harmonogram**     | RQ (django-rq): usługi `worker` i `cron`                  |
| **Serwer ASGI**               | Gunicorn + Uvicorn                                        |
| **Reverse Proxy**             | Traefik 3 (produkcja)                                     |
| **Media Proxy**               | Nginx (produkcja)                                         |
| **Konteneryzacja**            | Docker & Docker Compose                                   |
| **Zarządzanie zależnościami** | [uv](https://docs.astral.sh/uv/)                          |
| **Frontend**                  | webpack 5 + Babel + Sass + PostCSS, django-webpack-loader |
| **Linting**                   | Ruff, djLint                                              |
| **Type checking**             | mypy + django-stubs                                       |
| **Testy**                     | pytest, pytest-django, factory-boy, pytest-playwright     |

---

## Wymagania

- [Docker](https://docs.docker.com/get-docker/) (w wersji z Compose V2)
- [just](https://github.com/casey/just) _(opcjonalnie – skróty do komend)_

> **Uwaga:** Nie musisz instalować Pythona lokalnie – wszystko działa wewnątrz kontenerów Docker.

---

## Uruchomienie lokalne

### 1. Sklonuj repozytorium

```bash
git clone https://github.com/MilBia/Suchar-Overflow.git
cd Suchar-Overflow
```

### 2. Zbuduj obrazy Docker

```bash
docker compose -f docker-compose.local.yml build
```

Lub z użyciem `just`:

```bash
just build
```

### 3. Uruchom kontenery

```bash
docker compose -f docker-compose.local.yml up -d --remove-orphans
```

Postgres, Redis i Mailpit mają healthchecki, a `django` startuje dopiero, gdy są
`healthy` — stan widać w `docker compose -f docker-compose.local.yml ps`. Redis zapisuje
migawkę na wolumen (`--save 60 1`), więc jego dane przetrwają restart kontenera.
Od #456 obraz Postgresa buduje się lokalnie jako `suchar_overflow_local_postgres`; stary
`suchar_overflow_production_postgres` z wcześniejszych buildów można usunąć:
`docker image rm suchar_overflow_production_postgres` (tylko na maszynie deweloperskiej, nie na serwerze).

Lub:

```bash
just up
```

#### Frontend (webpack) i live reload

Od #466 repozytorium ma pipeline frontendu: **webpack + Babel + Sass + PostCSS**. Usługa `node`
(uruchamiana razem z resztą przez `just up`) trzyma `webpack-dev-server`:

- **http://localhost:3000** — aplikacja przez proxy do Django, z **live reloadem** (zmiana szablonu
  albo źródła w `webpack/src/` przeładowuje stronę). Używaj jej przy pracy nad frontendem.
- **http://localhost:8000** — Django bezpośrednio, działa jak dotąd (bundle dev są też zapisywane
  na dysk w `suchar_overflow/static/webpack_bundles/`). W konsoli przeglądarki zobaczysz jedną
  nieudaną próbę połączenia z gniazdem live reloadu — to normalne.

Bez działającej usługi `node` nie ma pliku `webpack-stats.json` i strony zwracają błąd 500.
Po zmianie `package.json` zbuduj obraz i odnów anonimowy wolumen z `node_modules`:
`just build && docker compose -f docker-compose.local.yml up -d --renew-anon-volumes`.

Bundle produkcyjne buduje `npm run build` (skrót: `just build-js`; na hoście, po jednorazowym
`npm ci`) — potrzebne m.in. testom E2E, które ładują prawdziwe bundle (`just test-e2e` sprawdza,
czy `webpack-stats.json` istnieje). Obraz produkcyjny buduje je sam w etapie `client-builder`.
Nie uruchamiaj `just build-js` przy działającej usłudze `node`: oba piszą do tego samego katalogu,
a dev-server nie wyemituje ponownie plików, które uważa za zapisane (`docker compose restart node`).

##### Architektura frontendu

```
webpack/
├── common.config.js, dev.config.js, prod.config.js, postcss.config.js, licenses-plugin.js
└── src/
    ├── js/
    │   ├── project.js          # wpis globalny: importuje wszystko, co ładuje każda strona
    │   ├── timezone.js         #   └─ pierwszy import (cookie `user_tz`)
    │   ├── app.js              #   └─ motyw, nawigacja, dropdowny, modale, SSE, dzwonek
    │   ├── csrf.js, toast.js   #   └─ `getCsrfToken`, `showToast` (importowane wprost)
    │   ├── features/           #   └─ easter eggi, `voting`, `hidden_achievements`
    │   └── pages/              # wpisy stron: `leaderboard`, `user_detail`, `suchar_form`, ...
    └── scss/
        ├── project.scss        # globalny arkusz: lista `@use` w kolejności kaskady
        ├── _*.scss, components/
        └── pages/              # arkusze stron, ładowane po globalnym
```

- **Wpisy.** `project` (JS + globalne CSS) renderuje `base.html`. Strony dokładają własne wpisy
  (`{% render_bundle 'leaderboard' 'js' attrs='defer' %}`, `{% render_bundle 'dashboard' 'css' %}`),
  które mają `dependOn: 'project'` — dzielą z nim instancje modułów i jeden runtime.
  Przy `render_bundle` zawsze podawaj rozszerzenie (`'js'` albo `'css'`).
- **Nowa strona ze skryptem lub stylem:** dodaj `webpack/src/js/pages/<nazwa>.js` (importuje swój
  `.scss`), zarejestruj go w `webpack/common.config.js` z `dependOn: 'project'` i wyrenderuj w szablonie.
- **Biblioteki** (Chart.js, flatpickr) pochodzą z npm i są pod Dependabotem; ich licencje trafiają do
  `/static/webpack_bundles/licenses.txt` w buildzie produkcyjnym.
- **Testy JS:** `just test-js` (Vitest + jsdom, na hoście) importuje moduły ES z `webpack/src/js/`
  i sprawdza m.in., że moduły współdzielone nie są kopiowane do wpisów stron.

Przy starcie kontener `django` sam stosuje migracje i kompiluje tłumaczenia
(`compilemessages`: pliki `.po` → `.mo`). Pliki `.mo` nie są w repozytorium, więc bez tego
kroku interfejs wyświetlałby surowe, nieprzetłumaczone teksty zamiast polskich.

#### Ponowna kompilacja tłumaczeń

Po edycji dowolnego pliku `locale/*/LC_MESSAGES/django.po` przekompiluj katalogi:

```bash
just messages          # wszystkie języki
just messages -l pl    # tylko wybrany język
```

Działający serwer przeładuje się sam — `uvicorn` obserwuje także pliki `*.mo`
(`--reload-include "*.mo"`), a restart procesu jest konieczny, bo Django trzyma wczytane
tłumaczenia w pamięci. Restart kontenera (`docker compose -f docker-compose.local.yml restart
django`) również kompiluje tłumaczenia przy starcie.

### 4. Zastosuj migracje i stwórz superusera

```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py migrate
docker compose -f docker-compose.local.yml run --rm django python manage.py createsuperuser
```

Lub z `just`:

```bash
just manage migrate
just manage createsuperuser
```

### 5. Otwórz w przeglądarce

| Usługa    | URL                          |
| --------- | ---------------------------- |
| Aplikacja | http://127.0.0.1:8000        |
| Mailpit   | http://127.0.0.1:8025        |
| Admin     | http://127.0.0.1:8000/admin/ |
| API       | http://127.0.0.1:8000/api/   |

> Maile (aktywacja konta, zmiana e-maila) trafiają do kolejki RQ i wysyła je usługa `worker`
> (z trzema ponowieniami); błąd SMTP nie kończy się już błędem 500 w żądaniu.
> Cykliczne zadania (np. przyznawanie osiągnięcia „Najlepszy suchar miesiąca") planuje usługa `cron`
> — uruchamiaj dokładnie jedną jej instancję. Panel kolejki: `/admin/django-rq/`.
> Po aktualizacji z wersji bez RQ uruchom `docker compose up -d --renew-anon-volumes`, żeby kontener
> `django` dostał nowe zależności.
> Mailpit przechwytuje wszystkie maile wychodzące w środowisku lokalnym.

### 6. Zatrzymaj kontenery

```bash
just down
```

Aby zatrzymać i **usunąć wolumeny** (czysta baza):

```bash
just prune
```

---

## Uruchomienie na produkcji

### 1. Przygotuj pliki konfiguracyjne

Skopiuj szablony plików środowiskowych i uzupełnij wartości:

```bash
cp .envs/.production/.django.example .envs/.production/.django
cp .envs/.production/.postgres.example .envs/.production/.postgres
```

**Wymagane zmienne w `.envs/.production/.django`:**

| Zmienna                | Opis                                                                                                  |
| ---------------------- | ----------------------------------------------------------------------------------------------------- |
| `DJANGO_SECRET_KEY`    | Losowy, długi klucz – np. wygenerowany `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DJANGO_ADMIN_URL`     | Ukryta ścieżka do panelu admin (np. `s3cr3t-admin/`)                                                  |
| `DJANGO_ALLOWED_HOSTS` | Domena(y) produkcyjne, np. `example.com`                                                              |

**Wymagane zmienne w `.envs/.production/.postgres`:**

| Zmienna             | Opis                          |
| ------------------- | ----------------------------- |
| `POSTGRES_USER`     | Losowa nazwa użytkownika bazy |
| `POSTGRES_PASSWORD` | Losowe, silne hasło           |

### 2. Skonfiguruj domenę w Traefik

Edytuj `compose/production/traefik/traefik.yml` – zamień `example.com` na swoją domenę
w sekcjach `rule: 'Host(...)'` oraz podaj poprawny email do certyfikatów Let's Encrypt.
Ten plik, w przeciwieństwie do reszty konfiguracji, nie czyta zmiennych środowiskowych –
zmiany trzeba wprowadzić ręcznie bezpośrednio w pliku.

### 3. Zbuduj i uruchom

```bash
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d
```

Lub z `just`:

```bash
just prod-build
just prod-up
```

> Migracje bazy danych i `collectstatic` wykonują się automatycznie przy starcie kontenera Django. Bundle JS/CSS (webpack) są budowane w obrazie (etap `client-builder`), nie przy starcie.
> Pliki statyczne (`/static/`) i media (`/media/`) serwuje nginx za Traefikiem — Django zapisuje statyki do wolumenu `production_django_static`, nginx czyta go tylko do odczytu.

#### Healthcheck i monitoring (`/healthz/`)

`GET /healthz/` zwraca `{"database": "ok", "cache": "ok"}` ze statusem 200 albo 503, gdy baza
lub Redis nie odpowiada (szczegóły błędu trafiają tylko do logów). Endpoint nie jest
przekierowywany na HTTPS i nie jest cache'owany — nadaje się do monitoringu uptime. Kontener
`django` ma na nim healthcheck (`docker compose ps` pokazuje `healthy`/`unhealthy`), a Traefik i
nginx startują dopiero, gdy jest `healthy`.

#### Dokumentacja API

`/api/docs` (Swagger) jest domyślnie włączona. Na produkcji wyłącz ją zmienną `DJANGO_API_ENABLE_DOCS=False`.

#### API — uwierzytelnianie

API przyjmuje dwa rodzaje uwierzytelnienia: sesję Django (jak frontend, z tokenem CSRF) albo token w nagłówku
`Authorization: Bearer <token>` (skrypty, integracje; bez CSRF).

Tokeny wystawia się wyłącznie w panelu admina (**API tokens → Add**; akcja „Generate a new token…” wymienia
istniejący, po ekranie potwierdzenia z listą użytkowników, którym cofnie dostęp). Nowe tokeny mają prefiks
`sot_` (Suchar Overflow Token), dzięki czemu skanery sekretów (GitHub Secret Scanning, Trufflehog) wyłapią
przypadkowo zacommitowany token; tokeny wystawione wcześniej, bez prefiksu, nadal działają. Wartość tokenu pojawia się **raz**, w komunikacie po zapisie — w bazie leży tylko jej skrót SHA-256,
więc nie da się jej odczytać ponownie. Token nieaktywnego użytkownika jest odrzucany.

```bash
curl -H "Authorization: Bearer $TOKEN" https://example.com/api/users/me   # {"username": "..."}
```

Brak lub zły token to `401`. Publiczny pozostaje tylko `GET /api/suchary/tags` (autouzupełnianie tagów).

### 4. Stwórz superusera (pierwsze uruchomienie)

```bash
docker compose -f docker-compose.production.yml run --rm django python manage.py createsuperuser
```

Lub:

```bash
just prod-manage createsuperuser
```

### 5. Zarządzanie

```bash
# Logi
just prod-logs           # wszystkie
just prod-logs django    # tylko Django

# Komendy manage.py
just prod-manage migrate
just prod-manage shell

# Zatrzymanie
just prod-down
```

### Backup bazy danych

Kontener PostgreSQL zawiera wbudowane skrypty do backupu (źródło: `compose/base/postgres/maintenance/`):

```bash
# Utworzenie backupu
docker compose -f docker-compose.production.yml exec postgres backup

# Lista backupów
docker compose -f docker-compose.production.yml exec postgres backups

# Przywrócenie backupu
docker compose -f docker-compose.production.yml exec postgres restore <nazwa_backupu>
```

---

## Architektura produkcji

```
                    ┌──────────────┐   /static/, /media/   ┌─────────┐
 przeglądarka ──443─▶   Traefik    ├──────────────────────▶│  nginx  │  (wolumeny tylko do odczytu)
                    │ (TLS, LE)    │                       └─────────┘
                    │              │   wszystko inne       ┌──────────────────────────────┐
                    │              ├──────────────────────▶│ django: gunicorn + uvicorn   │
                    └──────────────┘                       │ workers (ASGI), :5000        │
                                                           └───────┬───────────────┬──────┘
                                                                   │               │
                       ┌───────────┐   kolejka RQ (db /1)   ┌──────▼─────┐   ┌─────▼────┐
                       │  worker   │◀──────────────────────▶│   redis    │   │ postgres │
                       │ rqworker  │                        │ cache (/0) │   └─────▲────┘
                       └───────────┘                        │ kolejka(/1)│         │
                       ┌───────────┐   zadania cykliczne    └────────────┘         │
                       │   cron    ├───────────────────────────────────────────────┘
                       │  rqcron   │   (+ achievements_catch_up przy starcie; zadania i heartbeat przez redis)
                       └───────────┘
```

| Usługa     | Rola                                                                                                                                                      |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `traefik`  | Jedyny element wystawiony na świat (80/443); terminuje TLS (Let's Encrypt). `/static/` i `/media/` kieruje do `nginx`, resztę do `django`.                |
| `nginx`    | Serwuje `/static/` (wolumen `production_django_static`) i `/media/` (`production_django_media`), oba tylko do odczytu. W łańcuchu ASGI nie ma WhiteNoise. |
| `django`   | `gunicorn -k uvicorn.workers.UvicornWorker` (ASGI), liczba procesów z `WEB_CONCURRENCY`. Przy starcie: `migrate` i `collectstatic --clear`.               |
| `worker`   | `rqworker --with-scheduler default`: wysyła maile (z ponowieniami), wykonuje zadania z kolejki.                                                           |
| `cron`     | `achievements_catch_up`, potem `rqcron`: zadania cykliczne (konkursy miesiąca/roku, sweep publikacji). **Dokładnie jedna instancja.**                     |
| `postgres` | PostgreSQL 18 + skrypty backupu (`backup`, `backups`, `restore`, `rmbackup`).                                                                             |
| `redis`    | Cache (baza `/0`) i kolejka RQ (baza `/1`, osobna, żeby wyczyszczenie cache nie usunęło zadań). Snapshot co 60 s do wolumenu `/data`.                     |

Healthchecki mają `django`, `worker`, `cron`, `postgres` i `redis`; `traefik` i `nginx` startują dopiero, gdy `django` jest `healthy`.
Bundle webpacka powstają w obrazie (etap `client-builder`), nie przy starcie kontenera.

---

## Zmienne środowiskowe

Zmienne zależne od środowiska czyta `config/settings/*.py`. Kolejność źródeł (wygrywa pierwsze): zmienne
środowiska procesu (w produkcji `env_file` z compose) → `.env` (tylko z `DJANGO_READ_DOT_ENV_FILE=True`) →
`.envs/.secrets` (plik poza gitem i poza obrazem, czytany, gdy istnieje; w produkcji compose podaje go jako
opcjonalny `env_file` **przed** `.envs/.production/*`, więc te drugie go nadpisują).
Szablony: `.envs/.production/.django.example` i `.postgres.example`; lokalne wartości: `.envs/.local/`.

**Ogólne i bezpieczeństwo**

| Zmienna                                 | Opis                                                                                                                                                                       | Domyślnie                                                                                              | Środowisko  |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------- |
| `DJANGO_SETTINGS_MODULE`                | Moduł ustawień (`config.settings.local` / `.production`)                                                                                                                   | `config.settings.production` (`asgi.py`, `wsgi.py`); `manage.py` bez zmiennej: `config.settings.local` | wszystkie   |
| `DJANGO_SECRET_KEY`                     | Klucz kryptograficzny; brak wartości domyślnej                                                                                                                             | — (w `test` ma wartość domyślną)                                                                       | local, prod |
| `DJANGO_DEBUG`                          | Tryb debug (`base.py`; `local.py` ustawia `DEBUG = True` na sztywno)                                                                                                       | `False`                                                                                                | wszystkie   |
| `DJANGO_READ_DOT_ENV_FILE`              | Czy czytać `.env` z korzenia repo                                                                                                                                          | `False`                                                                                                | wszystkie   |
| `DJANGO_ALLOWED_HOSTS`                  | Dozwolone hosty, po przecinku (lokalnie `local.py` ustawia `["*"]` na sztywno); healthcheck `django` wysyła pierwszy wpis jako `Host`, więc błędna wartość psuje `healthy` | `example.com`                                                                                          | prod        |
| `DJANGO_ADMIN_URL`                      | Ścieżka panelu admina (z końcowym `/`); pod nią też panel `django-rq/`                                                                                                     | — (wymagana)                                                                                           | prod        |
| `DJANGO_ADMINS`                         | Odbiorcy maili o błędach 500 (`ADMINS`/`MANAGERS`), po przecinku; puste = nikt                                                                                             | puste                                                                                                  | wszystkie   |
| `DJANGO_SECURE_SSL_REDIRECT`            | Przekierowanie HTTP → HTTPS (`/healthz/` jest wyłączony z przekierowania)                                                                                                  | `True`                                                                                                 | prod        |
| `DJANGO_SECURE_HSTS_SECONDS`            | `max-age` HSTS                                                                                                                                                             | `518400`                                                                                               | prod        |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | `includeSubDomains` w HSTS                                                                                                                                                 | `True`                                                                                                 | prod        |
| `DJANGO_SECURE_HSTS_PRELOAD`            | `preload` w HSTS; wymaga `DJANGO_SECURE_HSTS_SECONDS >= 31536000`, inaczej start się nie uda                                                                               | `False`                                                                                                | prod        |
| `DJANGO_SECURE_CONTENT_TYPE_NOSNIFF`    | Nagłówek `X-Content-Type-Options: nosniff`                                                                                                                                 | `True`                                                                                                 | prod        |
| `DJANGO_API_ENABLE_DOCS`                | Publiczna dokumentacja `/api/docs` (zalecane `False` na produkcji)                                                                                                         | `True`                                                                                                 | wszystkie   |
| `API_ENABLE_DOCS`                       | Stara nazwa `DJANGO_API_ENABLE_DOCS`, czytana jeszcze jako zapasowa (jedno wydanie)                                                                                        | `True`                                                                                                 | wszystkie   |
| `FEEDBACK_URL`                          | Adres linku „zgłoś błąd" w stopce                                                                                                                                          | issues repozytorium                                                                                    | wszystkie   |
| `DJANGO_STATIC_ROOT`                    | Gdzie `collectstatic` zapisuje pliki statyczne                                                                                                                             | `<repo>/staticfiles` (`/app/staticfiles` w obrazie)                                                    | wszystkie   |
| `USE_DOCKER`                            | `yes` ustawia `INTERNAL_IPS` pod debug toolbar w kontenerze                                                                                                                | `no`                                                                                                   | local       |
| `DJANGO_ALLOW_ASYNC_UNSAFE`             | Ustawiana przez `e2e.py` dla Playwrighta; nie ustawiać ręcznie                                                                                                             | `true` (tylko E2E)                                                                                     | e2e         |

**Baza danych**

| Zmienna                                                              | Opis                                                                                                                           | Domyślnie                       | Środowisko  |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------- | ----------- |
| `DATABASE_URL`                                                       | DSN bazy. Gdy ustawiona (nawet pusta), wygrywa; `/entrypoint` zawsze ustawia ją z `POSTGRES_*` (nadpisując wartość z `run -e`) | składany z `POSTGRES_*`         | wszystkie   |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_PASSWORD` | Składniki DSN (hasło i nazwa są URL-enkodowane); także konfiguracja kontenera `postgres` i skryptów backupu                    | — (wymagane bez `DATABASE_URL`) | local, prod |
| `POSTGRES_USER`                                                      | Użytkownik bazy; skrypt `backup` odmawia pracy jako `postgres`                                                                 | `postgres`                      | local, prod |
| `CONN_MAX_AGE`                                                       | Czas życia połączenia. **Zostaw `0`** — pod ASGI wartość > 0 zostawia po jednym bezczynnym połączeniu na wątek (#430)          | `0`                             | prod        |

**Redis i kolejka**

| Zmienna           | Opis                                                                          | Domyślnie                   | Środowisko  |
| ----------------- | ----------------------------------------------------------------------------- | --------------------------- | ----------- |
| `REDIS_URL`       | Redis dla cache (`redis://` lub `rediss://`); brak wartości domyślnej         | — (wymagana)                | local, prod |
| `REDIS_QUEUE_URL` | Redis dla kolejki RQ — osobna baza, żeby czyszczenie cache nie kasowało zadań | `REDIS_URL` ze ścieżką `/1` | local, prod |

**Poczta** (każda opcja SMTP czytana jest też pod starą nazwą bez prefiksu `DJANGO_`, np. `EMAIL_HOST` — zapasowo,
przez jedno wydanie; wygrywa nazwa z prefiksem, pusta wartość = nieustawiona)

| Zmienna                       | Opis                                                     | Domyślnie                                     | Środowisko |
| ----------------------------- | -------------------------------------------------------- | --------------------------------------------- | ---------- |
| `DJANGO_EMAIL_BACKEND`        | Backend poczty                                           | `django.core.mail.backends.smtp.EmailBackend` | wszystkie  |
| `DJANGO_EMAIL_HOST`           | Serwer SMTP                                              | `localhost` (lokalnie `mailpit`)              | wszystkie  |
| `DJANGO_EMAIL_PORT`           | Port SMTP                                                | `25` (lokalnie `1025`)                        | wszystkie  |
| `DJANGO_EMAIL_HOST_USER`      | Użytkownik SMTP                                          | puste                                         | prod       |
| `DJANGO_EMAIL_HOST_PASSWORD`  | Hasło SMTP                                               | puste                                         | prod       |
| `DJANGO_EMAIL_USE_TLS`        | STARTTLS (port 587); wyklucza `DJANGO_EMAIL_USE_SSL`     | `False`                                       | prod       |
| `DJANGO_EMAIL_USE_SSL`        | Niejawny TLS (port 465); wyklucza `DJANGO_EMAIL_USE_TLS` | `False`                                       | prod       |
| `DJANGO_EMAIL_TIMEOUT`        | Limit czasu połączenia SMTP (s)                          | `5`                                           | prod       |
| `DJANGO_DEFAULT_FROM_EMAIL`   | Nadawca maili do użytkowników                            | `Suchar Overflow <noreply@example.com>`       | prod       |
| `DJANGO_SERVER_EMAIL`         | Nadawca maili o błędach                                  | `DJANGO_DEFAULT_FROM_EMAIL`                   | prod       |
| `DJANGO_EMAIL_SUBJECT_PREFIX` | Prefiks tematu maili o błędach                           | `[Suchar Overflow] `                          | prod       |

**Serwer**

| Zmienna           | Opis                                                                                                    | Domyślnie | Środowisko |
| ----------------- | ------------------------------------------------------------------------------------------------------- | --------- | ---------- |
| `WEB_CONCURRENCY` | Liczba procesów gunicorna (czyta ją sam gunicorn, nie settings). Bezpiecznie rosnąć: cron działa osobno | `1`       | prod       |

---

## Operacje

Poniższe komendy zakładają produkcję (`docker compose -f docker-compose.production.yml …`, skrót `just prod-manage`);
lokalnie odpowiadają im `just exec python manage.py …` i `just logs`.

| Co                         | Jak                                                                                                                                           |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Stan aplikacji             | `GET /healthz/` — `{"database", "cache", "queue"}`, 200 albo 503; `docker compose ps` pokazuje `healthy`                                      |
| Stan kolejki               | `just prod-manage rqstats` (lokalnie `just exec python manage.py rqstats`)                                                                    |
| Panel kolejki              | `/<DJANGO_ADMIN_URL>django-rq/` (zadania w toku, nieudane, ponowienia)                                                                        |
| Healthcheck worker / cron  | `manage.py rq_healthcheck` / `manage.py rq_healthcheck --cron` (to samo wywołują healthchecki compose)                                        |
| Logi worker / cron         | `just prod-logs worker cron`                                                                                                                  |
| Ręczny worker              | `docker compose -f docker-compose.production.yml run --rm worker` (ten sam obraz, polecenie `/worker`)                                        |
| Catch-up zadań cyklicznych | `just prod-manage achievements_catch_up` — wykonuje zaległe konkursy miesiąca/roku i sweep publikacji; `cron` robi to sam przy każdym starcie |
| Backup / restore           | patrz [Backup bazy danych](#backup-bazy-danych)                                                                                               |

Zasady: uruchamiaj **dokładnie jedną** instancję `cron` (druga podwoiłaby każde zadanie cykliczne);
`worker` nie przeładowuje się sam po zmianie kodu zadania — zrestartuj go po wdrożeniu; po twardym zabiciu workera
ponowienia mogą opóźnić się do ok. 10 minut (wygasa blokada schedulera RQ).

### Migracja wolumenu PostgreSQL

Od #464 wolumen danych (`production_postgres_cluster`, lokalnie `suchar_overflow_local_postgres_cluster`) jest
montowany na `/var/lib/postgresql`, a klaster leży w `/var/lib/postgresql/18/docker`. Dzięki temu przyszły
`pg_upgrade --link` (#174, PostgreSQL 19) działa w obrębie jednego wolumenu. Stary wolumen (`*_postgres_data`) miał klaster
w korzeniu i **nie wolno go podpinać pod nowy mount**: Postgres zainicjowałby pusty klaster. Obraz ma
bezpiecznik (`volume-guard`): gdy w korzeniu wolumenu leży `PG_VERSION`, a `PGDATA` jest puste, kontener kończy się
błędem zamiast tworzyć nowy klaster. Wolumen backupów (`*_postgres_data_backups`) się nie zmienia.

Procedura (produkcja wyłącznie w oknie serwisowym; nazwy wolumenów w Dockerze mają prefiks projektu compose):

```bash
C="docker compose -f docker-compose.production.yml"
PSQL='PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" "$POSTGRES_DB" -tAc'
COUNTS="select (select count(*) from suchary_suchar), (select count(*) from suchary_vote), (select count(*) from users_user), (select count(*) from django_migrations)"

# 1. Na STARYM commicie/obrazie (sprzed #464): zatrzymaj wszystko, co pisze do bazy (zostaje sam postgres),
#    zapisz liczniki do późniejszego porównania i zrób backup. Zapisy po backupie przepadłyby.
$C stop traefik nginx django worker cron
$C exec -T postgres bash -c "$PSQL \"$COUNTS\"" | tee counts_before.txt
$C exec postgres backup
$C exec postgres backups          # zapamiętaj nazwę pliku

# 2. Zatrzymanie stosu (wolumeny zostają). Dopiero teraz wdróż kod z #464.
$C down

# 3. Start samego Postgresa na nowym, pustym wolumenie.
$C up -d --build postgres

# 4. Przywrócenie backupu (restore robi dropdb + createdb + psql).
$C exec postgres restore <nazwa_backupu>

# 5. Weryfikacja: liczniki muszą być identyczne jak w counts_before.txt, potem pełny start.
$C exec -T postgres bash -c "$PSQL \"$COUNTS\"" | diff - counts_before.txt && echo "liczniki zgodne"
$C up -d
$C exec django python manage.py showmigrations     # wszystko [X]
```

6. Stary wolumen zostaje nietknięty do potwierdzenia, że wszystko działa. Dopiero wtedy usuń go ręcznie:
   `docker volume ls | grep 'postgres_data$'` → `docker volume rm <projekt>_production_postgres_data`.
   **Nie usuwaj** `*_postgres_data_backups`: to wolumen z backupami (w tym z dumpem z kroku 1).

**Cofnięcie.** Do kroku 5 włącznie (zanim stos przyjął ruch na nowym klastrze): `down`, przywróć poprzedni commit
(stary mount) i `up -d`; stary wolumen jest cały, więc nic nie ginie. Po `up -d` na nowym klastrze rollback nie jest
już bezstratny: zapisy z nowego klastra trzeba najpierw wyeksportować (`backup` z nowego stosu) i przywrócić
(`restore`) na starym układzie.

**Uwaga.** `volume-guard` jest entrypointem, więc blokuje też `docker compose run --rm postgres backup` na starym
wolumenie pod nowym mountem. Backup ze starego układu robi się przez `exec` na działającym starym kontenerze (krok 1).

Lokalnie: ta sama procedura (`docker-compose.local.yml`, `just`), albo — jeśli dane lokalne nie są potrzebne —
`just prune` i nowy start.

Procedurę przećwiczono na kopii danych (osobne wolumeny, 500 wierszy + tabela migracji): backup → odmowa startu
`volume-guard` na starym wolumenie pod nowym mountem → pusty klaster na nowym wolumenie → `restore` → te same liczniki
→ restart kontenera zachowuje dane.

---

## Przydatne komendy

Projekt udostępnia skróty poprzez [just](https://github.com/casey/just):

### Lokalne (development)

| Komenda                         | Opis                                                    |
| ------------------------------- | ------------------------------------------------------- |
| `just build`                    | Budowanie obrazów Docker                                |
| `just up`                       | Uruchomienie kontenerów                                 |
| `just down`                     | Zatrzymanie kontenerów                                  |
| `just prune`                    | Zatrzymanie + usunięcie wolumenów                       |
| `just logs [serwis]`            | Podgląd logów                                           |
| `just manage <cmd>`             | Wykonanie komendy `manage.py`                           |
| `just shell`                    | `shell_plus` w działającym kontenerze (po `just up`)    |
| `just bash`                     | Bash w działającym kontenerze (po `just up`)            |
| `just exec <cmd>`               | Dowolna komenda w działającym kontenerze (po `just up`) |
| `just messages`                 | Kompilacja tłumaczeń (`.po` → `.mo`)                    |
| `just test [args]`              | Uruchomienie testów jednostkowych (pytest)              |
| `just build-js`                 | Zbudowanie bundli webpacka (`npm run build`, na hoście) |
| `just test-e2e [args]`          | Uruchomienie testów E2E (Playwright)                    |
| `just test-all`                 | Testy jednostkowe, a następnie E2E                      |
| `just fill-translations [args]` | Uzupełnianie tłumaczeń przez lokalny model AI           |

### Produkcyjne

| Komenda                   | Opis                            |
| ------------------------- | ------------------------------- |
| `just prod-build`         | Budowanie obrazów produkcyjnych |
| `just prod-up`            | Uruchomienie produkcji          |
| `just prod-down`          | Zatrzymanie produkcji           |
| `just prod-logs [serwis]` | Podgląd logów produkcyjnych     |
| `just prod-manage <cmd>`  | Wykonanie komendy `manage.py`   |

---

## Tłumaczenia AI (`fill_translations`)

Projekt zawiera komendę zarządzania Django do automatycznego uzupełniania pustych ciągów w plikach `.po` za pomocą lokalnego modelu AI z interfejsem kompatybilnym z OpenAI API (np. LM Studio, Ollama).

### Wymagania

Model musi być dostępny przez endpoint `/v1` kompatybilny z OpenAI. Domyślnie używany jest model `translategemma`.

### Użycie

```bash
# Uzupełnij angielskie tłumaczenia (wszystkie puste wpisy)
just fill-translations --url 192.168.1.1:1234/v1 --language en --model translategemma-12b-it

# Podgląd bez zapisu (dry run)
just fill-translations --url 192.168.1.1:1234/v1 --language en --dry-run

# Ponowne przetłumaczenie wszystkich wpisów (także już wypełnionych)
just fill-translations --url 192.168.1.1:1234/v1 --language pl --all

# Bezpośrednio przez manage.py / uv
uv run manage.py fill_translations --url http://localhost:11434/v1 --language en --model llama3.2
```

Po uzupełnieniu tłumaczeń skompiluj pliki `.po`
(zob. [Ponowna kompilacja tłumaczeń](#ponowna-kompilacja-tłumaczeń)):

```bash
just messages
```

### Parametry

| Parametr        | Opis                                                  | Domyślna wartość                    |
| --------------- | ----------------------------------------------------- | ----------------------------------- |
| `--url`         | URL endpointu API (schemat `http://` jest opcjonalny) | _wymagany_                          |
| `--model`       | Nazwa modelu                                          | `translategemma`                    |
| `--language`    | Kod języka docelowego (np. `pl`, `en`)                | wszystkie języki                    |
| `--source-lang` | Kod języka źródłowego stringów `msgid`                | `en`                                |
| `--locale-dir`  | Ścieżka do katalogu locale                            | `LOCALE_PATHS[0]` z ustawień Django |
| `--all`         | Przetłumacz też już wypełnione wpisy                  | `false`                             |
| `--dry-run`     | Wyświetl wynik bez zapisu                             | `false`                             |
| `--api-key`     | Klucz API (dla lokalnych modeli zwykle zbędny)        | `nokey`                             |

---

## Struktura projektu

```
Suchar-Overflow/
├── compose/                  # Konfiguracja Docker
│   ├── base/                 #   └─ wspólne dla obu środowisk (entrypoint Django, obraz Postgresa + skrypty backupu)
│   ├── local/                #   └─ development (Dockerfile i start Django)
│   └── production/           #   └─ produkcja (Dockerfile i start Django, Nginx, Traefik)
├── config/                   # Konfiguracja Django
│   ├── settings/             #   └─ base.py, local.py, production.py, test.py, e2e.py
│   ├── urls.py               #   └─ główny routing
│   ├── api.py                #   └─ Django Ninja – rejestracja routerów API
│   └── wsgi.py
├── suchar_overflow/          # Kod aplikacji
│   ├── achievements/         #   └─ system osiągnięć (engine, signals, api)
│   ├── suchary/              #   └─ główna apka – żarty, głosowanie, API
│   ├── stats/                #   └─ statystyki i leaderboard
│   ├── users/                #   └─ zarządzanie użytkownikami (ActivationToken, mail tasks)
│   ├── utils/                #   └─ kod przekrojowy: handlery błędów, middleware, logowanie, `/healthz/`, schematy API (bez modeli)
│   ├── static/               #   └─ CSS, JS, obrazy, czcionki (+ `webpack_bundles/` – wynik buildu, poza gitem)
│   └── templates/            #   └─ szablony Django (HTML)
├── webpack/                  # Konfiguracja webpacka (common/dev/prod/postcss) i źródła w `src/`
├── locale/                   # Tłumaczenia (PL, EN)
├── tests/                    # Testy narzędziowe (root-level)
│   └── e2e/                  #   └─ testy Playwright (E2E)
├── .devcontainer/            # Konfiguracja VS Code Dev Container
├── .github/                  # GitHub Actions CI + Dependabot
├── docker-compose.local.yml  # Compose – development
├── docker-compose.production.yml  # Compose – produkcja
├── justfile                  # Skróty komend
├── pyproject.toml            # Zależności i konfiguracja narzędzi
└── uv.lock                   # Zablokowane wersje zależności
```

> **Uwaga:** `docs/superpowers/` (plany/specyfikacje generowane przez AI-agenta na potrzeby
> pracy nad projektem) to katalog roboczy, nie stała część repo – po zmergowaniu i
> udokumentowaniu opisanej w nich pracy pliki są usuwane. Git nie śledzi pustych katalogów,
> więc `docs/` może w danym momencie w ogóle nie występować w drzewie repo.

---

## Testy

Projekt posiada dwa oddzielne zestawy testów, które **muszą być uruchamiane osobno**:

| Zestaw                           | Marker             | Komenda         |
| -------------------------------- | ------------------ | --------------- |
| Testy jednostkowe / integracyjne | _(brak markera)_   | `just test`     |
| Testy E2E (Playwright)           | `@pytest.mark.e2e` | `just test-e2e` |

### Testy jednostkowe

```bash
just test
```

Lub bezpośrednio:

```bash
docker compose -f docker-compose.local.yml run --rm django pytest -m "not e2e"
```

Z pokryciem kodu:

```bash
docker compose -f docker-compose.local.yml run --rm django coverage run -m pytest -m "not e2e"
docker compose -f docker-compose.local.yml run --rm django coverage report
```

Konfiguracja pytest (w `pyproject.toml`) używa `--reuse-db` dla szybszych przebiegów oraz `factory-boy` do tworzenia danych testowych.

### Testy E2E (Playwright)

Testy E2E uruchamiają prawdziwą przeglądarkę Chromium wewnątrz kontenera Docker i testują zachowania frontendowe (formularze, dropdowny, modale, motywy, głosowanie itd.).

```bash
just test-e2e
```

Aby uruchomić oba zestawy sekwencyjnie:

```bash
just test-all
```

Testy E2E używają osobnych ustawień Django (`config.settings.e2e`), które rozszerzają `config.settings.test` o `ALLOWED_HOSTS` i `CSRF_TRUSTED_ORIGINS` dla `127.0.0.1`/`localhost` – wymaganych przy POSTach przez `live_server` Playwright.

Wyniki testów w formacie JUnit XML są generowane w CI automatycznie.

---

## Dev Container

Projekt zawiera konfigurację [VS Code Dev Container](https://code.visualstudio.com/docs/devcontainers/containers) (`.devcontainer/`).
Po otwarciu projektu w VS Code z zainstalowanym rozszerzeniem Dev Containers środowisko uruchomi się automatycznie z:

- Python 3.14, uv, Ruff, Pylance, mypy
- podłączonym do lokalnego `docker-compose.local.yml`
- zamontowanym `.ssh` i historią bash

---

## Pre-commit

Projekt używa [pre-commit](https://pre-commit.com/) do automatycznego sprawdzania kodu.

`pre-commit` (i `ipdb`) należą do grupy `local-tools` — celowo pominiętej przy
`uv sync` w obrazie Docker (są potrzebne tylko lokalnie, poza kontenerem), więc
trzeba ją zainstalować jawnie. Użyj `--only-group`, nie `--group` — `--group`
zsynchronizowałby też domyślną grupę `dev` i `[project.dependencies]`, co na
hoście bez nagłówków PostgreSQL (`pg_config`) zakończy się błędem kompilacji
`psycopg-c` (patrz CLAUDE.md, sekcja "Running commands").

### Instalacja hooków (wymagany lokalny `.venv`):

```bash
uv sync --only-group local-tools
source .venv/bin/activate
pre-commit install
```

### Ręczne uruchomienie:

```bash
pre-commit run --all-files
```

Konfiguracja hooków: [`.pre-commit-config.yaml`](.pre-commit-config.yaml)

Konwencje formatowania: linia 120 znaków, wcięcia 4 spacje. Python formatuje ruff,
szablony djLint, a resztę (JS, CSS, YAML, JSON, Markdown) hook `prettier` — opcje w
[`.prettierrc.json`](.prettierrc.json), wykluczenia w [`.prettierignore`](.prettierignore).
Hook sam pobiera Node przez pre-commit, więc lokalny Node nie jest wymagany.

Jednorazowy reformat całego repo jest w [`.git-blame-ignore-revs`](.git-blame-ignore-revs).
Żeby `git blame` go pomijał, wykonaj raz w klonie:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

---

## Licencja

Projekt udostępniony na licencji [MIT](LICENSE).

© 2026 Miłosz Białczak
