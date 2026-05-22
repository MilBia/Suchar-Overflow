# 🌵 Suchar Overflow

Agregator żartów o krytycznie niskim poziomie wilgotności.
Wchodzisz na własną odpowiedzialność (i z butelką wody).

[![CI](https://github.com/MilBia/Suchar-Overflow/actions/workflows/ci.yml/badge.svg)](https://github.com/MilBia/Suchar-Overflow/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0--beta.1-blue.svg)]()

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
(polski i angielski), używa kolejki RQ (Redis Queue) do asynchronicznego wysyłania maili
oraz cyklicznych zadań (np. przyznawanie osiągnięć) za pomocą wbudowanego schedulera RQ.

### Główne funkcje

- 📝 **Dodawanie i przeglądanie żartów** – z paginacją i sortowaniem
- 👍👎 **System głosowania** – oceniaj suchary (i obserwuj jak lecą w dół)
- 🏆 **Ranking / Leaderboard** – najlepsi twórcy sucharów
- 🎖️ **Osiągnięcia** – system achievement'ów z ukrytymi odznaczeniami i skrzynką powiadomień
- 📊 **Statystyki** – wykresy aktywności użytkowników
- 📬 **Asynchroniczne maile** – aktywacja konta i zmiana e-maila przez kolejkę RQ
- 🌙 **Dark / Light mode** – przełączanie motywu
- 🌍 **Internationalizacja** – pełne wsparcie PL / EN

---

## Technologie

| Warstwa          | Technologia                                        |
| ---------------- | -------------------------------------------------- |
| **Język**        | Python 3.13                                        |
| **Framework**    | Django 5.2                                         |
| **REST API**     | Django Ninja                                       |
| **Baza danych**  | PostgreSQL 18                                      |
| **Cache**        | Redis 7 (django-redis)                             |
| **Kolejka zadań** | django-rq + rq-scheduler + Redis                  |
| **Serwer WSGI** | Gunicorn                                           |
| **Reverse Proxy** | Traefik 3 (produkcja)                             |
| **Media Proxy**  | Nginx (produkcja)                                  |
| **Konteneryzacja** | Docker & Docker Compose                          |
| **Zarządzanie zależnościami** | [uv](https://docs.astral.sh/uv/)     |
| **Minifikacja CSS/JS** | django-compressor + rcssmin + rjsmin          |
| **Linting**      | Ruff, djLint                                       |
| **Type checking** | mypy + django-stubs                               |
| **Testy**        | pytest, pytest-django, factory-boy                 |

---

## Wymagania

- [Docker](https://docs.docker.com/get-docker/) (w wersji z Compose V2)
- [just](https://github.com/casey/just) *(opcjonalnie – skróty do komend)*

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

Lub:

```bash
just up
```

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

| Usługa      | URL                          |
| ----------- | ---------------------------- |
| Aplikacja   | http://127.0.0.1:8000        |
| Mailpit     | http://127.0.0.1:8025        |
| Admin       | http://127.0.0.1:8000/admin/ |
| API         | http://127.0.0.1:8000/api/   |

> **RQ worker** uruchamia się automatycznie jako osobny kontener (`rqworker`).
> Maile (aktywacja konta, zmiana e-maila) są wysyłane asynchronicznie przez ten worker.
> Cykliczne zadania (np. przyznawanie osiągnięcia „Najlepszy suchar miesiąca") obsługuje
> wbudowany `rqscheduler`, który działa w tle wewnątrz tego samego kontenera.
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

| Zmienna                  | Opis                                          |
| ------------------------ | --------------------------------------------- |
| `DJANGO_SECRET_KEY`      | Losowy, długi klucz – np. wygenerowany `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DJANGO_ADMIN_URL`       | Ukryta ścieżka do panelu admin (np. `s3cr3t-admin/`) |
| `DJANGO_ALLOWED_HOSTS`   | Domena(y) produkcyjne, np. `example.com`      |

**Wymagane zmienne w `.envs/.production/.postgres`:**

| Zmienna              | Opis                                          |
| -------------------- | --------------------------------------------- |
| `POSTGRES_USER`      | Losowa nazwa użytkownika bazy                 |
| `POSTGRES_PASSWORD`  | Losowe, silne hasło                           |

### 2. Skonfiguruj domenę w Traefik

Edytuj `compose/production/traefik/traefik.yml` – zamień `example.com` na swoją domenę
w sekcjach `rule: 'Host(...)'` oraz podaj poprawny email do certyfikatów Let's Encrypt.

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

Kontener PostgreSQL zawiera wbudowane skrypty do backupu:

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

| Komenda              | Opis                                  |
| -------------------- | ------------------------------------- |
| `just build`         | Budowanie obrazów Docker              |
| `just up`            | Uruchomienie kontenerów               |
| `just down`          | Zatrzymanie kontenerów                |
| `just prune`         | Zatrzymanie + usunięcie wolumenów     |
| `just logs [serwis]` | Podgląd logów                         |
| `just manage <cmd>`  | Wykonanie komendy `manage.py`         |
| `just test [args]`   | Uruchomienie testów (pytest)          |
| `just fill-translations [args]` | Uzupełnianie tłumaczeń przez lokalny model AI |

### Produkcyjne

| Komenda                  | Opis                                  |
| ------------------------ | ------------------------------------- |
| `just prod-build`        | Budowanie obrazów produkcyjnych       |
| `just prod-up`           | Uruchomienie produkcji                |
| `just prod-down`         | Zatrzymanie produkcji                 |
| `just prod-logs [serwis]`| Podgląd logów produkcyjnych           |
| `just prod-manage <cmd>` | Wykonanie komendy `manage.py`         |

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

Po uzupełnieniu tłumaczeń skompiluj pliki `.po`:

```bash
just manage compilemessages
```

### Parametry

| Parametr | Opis | Domyślna wartość |
| --- | --- | --- |
| `--url` | URL endpointu API (schemat `http://` jest opcjonalny) | *wymagany* |
| `--model` | Nazwa modelu | `translategemma` |
| `--language` | Kod języka docelowego (np. `pl`, `en`) | wszystkie języki |
| `--source-lang` | Kod języka źródłowego stringów `msgid` | `en` |
| `--locale-dir` | Ścieżka do katalogu locale | `LOCALE_PATHS[0]` z ustawień Django |
| `--all` | Przetłumacz też już wypełnione wpisy | `false` |
| `--dry-run` | Wyświetl wynik bez zapisu | `false` |
| `--api-key` | Klucz API (dla lokalnych modeli zwykle zbędny) | `nokey` |

---

## Struktura projektu

```
Suchar-Overflow/
├── compose/                  # Konfiguracja Docker
│   ├── local/                #   └─ development (Django, rqworker+scheduler)
│   └── production/           #   └─ produkcja (Django, Nginx, Traefik, Postgres, rqworker+scheduler)
├── config/                   # Konfiguracja Django
│   ├── settings/             #   └─ base.py, local.py, production.py, test.py
│   ├── urls.py               #   └─ główny routing
│   ├── api.py                #   └─ Django Ninja – rejestracja routerów API
│   └── wsgi.py
├── suchar_overflow/          # Kod aplikacji
│   ├── achievements/         #   └─ system osiągnięć (engine, signals, middleware, inbox)
│   ├── suchary/              #   └─ główna apka – żarty, głosowanie, API
│   ├── stats/                #   └─ statystyki i leaderboard
│   ├── users/                #   └─ zarządzanie użytkownikami (ActivationToken, RQ tasks)
│   ├── contrib/              #   └─ współdzielone narzędzia i mixiny
│   ├── static/               #   └─ CSS, JS, obrazy, czcionki
│   └── templates/            #   └─ szablony Django (HTML)
├── locale/                   # Tłumaczenia (PL, EN)
├── tests/                    # Testy narzędziowe (root-level)
├── .devcontainer/            # Konfiguracja VS Code Dev Container
├── .github/                  # GitHub Actions CI + Dependabot
├── docker-compose.local.yml  # Compose – development
├── docker-compose.production.yml  # Compose – produkcja
├── justfile                  # Skróty komend
├── pyproject.toml            # Zależności i konfiguracja narzędzi
└── uv.lock                   # Zablokowane wersje zależności
```

---

## Testy

Testy uruchamiane są wewnątrz kontenera Docker:

```bash
just test
```

Lub bezpośrednio:

```bash
docker compose -f docker-compose.local.yml run --rm django pytest
```

Z pokryciem kodu:

```bash
docker compose -f docker-compose.local.yml run --rm django coverage run -m pytest
docker compose -f docker-compose.local.yml run --rm django coverage report
```

Konfiguracja pytest (w `pyproject.toml`) używa `--reuse-db` dla szybszych przebiegów oraz `factory-boy` do tworzenia danych testowych. Wyniki testów w formacie JUnit XML są generowane w CI automatycznie.

---

## Dev Container

Projekt zawiera konfigurację [VS Code Dev Container](https://code.visualstudio.com/docs/devcontainers/containers) (`.devcontainer/`).
Po otwarciu projektu w VS Code z zainstalowanym rozszerzeniem Dev Containers środowisko uruchomi się automatycznie z:

- Python 3.13, uv, Ruff, Pylance, mypy
- podłączonym do lokalnego `docker-compose.local.yml`
- zamontowanym `.ssh` i historią bash

---

## Pre-commit

Projekt używa [pre-commit](https://pre-commit.com/) do automatycznego sprawdzania kodu.

### Instalacja hooków (wymagany lokalny `.venv`):

```bash
uv sync
source .venv/bin/activate
pre-commit install
```

### Ręczne uruchomienie:

```bash
pre-commit run --all-files
```

Konfiguracja hooków: [`.pre-commit-config.yaml`](.pre-commit-config.yaml)

---

## Licencja

Projekt udostępniony na licencji [MIT](LICENSE).

© 2026 Miłosz Białczak
