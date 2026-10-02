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

| Warstwa                       | Technologia                                                                                      |
| ----------------------------- | ------------------------------------------------------------------------------------------------ |
| **Język**                     | Python 3.14                                                                                      |
| **Framework**                 | Django 6.1                                                                                       |
| **REST API**                  | Django Ninja                                                                                     |
| **Baza danych**               | PostgreSQL 18                                                                                    |
| **Cache**                     | Redis 8 (django-redis)                                                                           |
| **Kolejka i harmonogram**     | RQ (django-rq): usługi `worker` i `cron`                                                         |
| **Serwer ASGI**               | Gunicorn + Uvicorn                                                                               |
| **Reverse Proxy**             | Traefik 3 (produkcja)                                                                            |
| **Media Proxy**               | Nginx (produkcja)                                                                                |
| **Konteneryzacja**            | Docker & Docker Compose                                                                          |
| **Zarządzanie zależnościami** | [uv](https://docs.astral.sh/uv/)                                                                 |
| **Frontend**                  | webpack 5 + Babel + Sass + PostCSS (django-webpack-loader), obok django-compressor do czasu #469 |
| **Linting**                   | Ruff, djLint                                                                                     |
| **Type checking**             | mypy + django-stubs                                                                              |
| **Testy**                     | pytest, pytest-django, factory-boy, pytest-playwright                                            |

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

> Migracje bazy danych, `collectstatic` i `compress` (minifikacja CSS/JS) wykonują się automatycznie przy starcie kontenera Django.
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
istniejący). Wartość tokenu pojawia się **raz**, w komunikacie po zapisie — w bazie leży tylko jej skrót SHA-256,
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
│   ├── contrib/              #   └─ współdzielone narzędzia i mixiny
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
