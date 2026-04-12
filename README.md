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
- [Struktura projektu](#struktura-projektu)
- [Testy](#testy)
- [Pre-commit](#pre-commit)
- [Licencja](#licencja)

---

## O projekcie

Suchar Overflow to platforma do dzielenia się żartami (sucharami) – z systemem głosowania,
rankingiem użytkowników, osiągnięciami i statystykami. Projekt wspiera dwa języki
(polski i angielski) i używa Celery do zadań w tle (np. przyznawanie osiągnięć).

### Główne funkcje

- 📝 **Dodawanie i przeglądanie żartów** – z paginacją i sortowaniem
- 👍👎 **System głosowania** – oceniaj suchary (i obserwuj jak lecą w dół)
- 🏆 **Ranking / Leaderboard** – najlepsi twórcy sucharów
- 🎖️ **Osiągnięcia** – system achievement'ów z ukrytymi odznaczeniami
- 📊 **Statystyki** – wykresy aktywności użytkowników
- 🌙 **Dark / Light mode** – przełączanie motywu
- 🌍 **Internationalizacja** – pełne wsparcie PL / EN

---

## Technologie

| Warstwa          | Technologia                                        |
| ---------------- | -------------------------------------------------- |
| **Język**        | Python 3.13                                        |
| **Framework**    | Django 5.2                                         |
| **Baza danych**  | PostgreSQL 18                                      |
| **Cache/Broker** | Redis 7                                            |
| **Task Queue**   | Celery 5.4                                         |
| **Serwer WSGI** | Gunicorn                                           |
| **Reverse Proxy** | Traefik 3 (produkcja)                             |
| **Media Proxy**  | Nginx (produkcja)                                  |
| **Konteneryzacja** | Docker & Docker Compose                          |
| **Zarządzanie zależnościami** | [uv](https://docs.astral.sh/uv/)     |
| **Linting**      | Ruff, djLint                                       |
| **Testy**        | pytest, pytest-django                              |

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

| Usługa      | URL                       |
| ----------- | ------------------------- |
| Aplikacja   | http://127.0.0.1:8000     |
| Mailpit     | http://127.0.0.1:8025     |
| Admin       | http://127.0.0.1:8000/admin/ |

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

> Migracje bazy danych i `collectstatic` wykonują się automatycznie przy starcie kontenera Django.

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

### Produkcyjne

| Komenda                  | Opis                                  |
| ------------------------ | ------------------------------------- |
| `just prod-build`        | Budowanie obrazów produkcyjnych       |
| `just prod-up`           | Uruchomienie produkcji                |
| `just prod-down`         | Zatrzymanie produkcji                 |
| `just prod-logs [serwis]`| Podgląd logów produkcyjnych           |
| `just prod-manage <cmd>` | Wykonanie komendy `manage.py`         |

---

## Struktura projektu

```
Suchar-Overflow/
├── compose/                  # Konfiguracja Docker
│   ├── local/                #   └─ development (Django, Celery)
│   └── production/           #   └─ produkcja (Django, Nginx, Traefik, Postgres)
├── config/                   # Konfiguracja Django
│   ├── settings/             #   └─ base.py, local.py, production.py, test.py
│   ├── urls.py               #   └─ główny routing
│   ├── celery_app.py         #   └─ konfiguracja Celery
│   └── wsgi.py
├── suchar_overflow/          # Kod aplikacji
│   ├── achievements/         #   └─ system osiągnięć
│   ├── suchary/              #   └─ główna apka – żarty, głosowanie
│   ├── stats/                #   └─ statystyki i leaderboard
│   ├── users/                #   └─ zarządzanie użytkownikami
│   ├── static/               #   └─ CSS, JS, obrazy
│   └── templates/            #   └─ szablony Django (HTML)
├── locale/                   # Tłumaczenia (PL, EN)
├── tests/                    # Testy
├── docker-compose.local.yml  # Compose – development
├── docker-compose.production.yml  # Compose – produkcja
├── justfile                  # Skróty komend
└── pyproject.toml            # Zależności i konfiguracja narzędzi
```

---

## Testy

Testy uruchamiane są wewnątrz kontenera Docker:

```bash
docker compose -f docker-compose.local.yml run --rm django pytest
```

Z pokryciem kodu:

```bash
docker compose -f docker-compose.local.yml run --rm django coverage run -m pytest
docker compose -f docker-compose.local.yml run --rm django coverage report
```

---

## Pre-commit

Projekt używa [pre-commit](https://pre-commit.com/) do automatycznego sprawdzania kodu.

### Instalacja hooków (wymagany lokalny `.venv`):

```bash
python -m venv .venv
source .venv/bin/activate
pip install pre-commit
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
