# Changelog

Wszystkie znaczące zmiany w projekcie są dokumentowane w tym pliku.

## [Unreleased]

### Token API: prefiks `sot_` i potwierdzenie akcji „regenerate” (#487)

- Nowe tokeny API zaczynają się od `sot_`, więc skanery sekretów rozpoznają zacommitowany token. Wcześniejsze tokeny
  (bez prefiksu) działają bez zmian — nic nie wymaga migracji.
- Akcja „Wygeneruj nowy token…” w adminie pokazuje najpierw ekran potwierdzenia z listą użytkowników.

### Wolumen PostgreSQL na `/var/lib/postgresql` (#464) — wymaga migracji danych

- Wolumen danych ma nową nazwę (`production_postgres_cluster`, lokalnie `suchar_overflow_local_postgres_cluster`)
  i jest montowany na `/var/lib/postgresql` (klaster w `18/docker`), co umożliwia `pg_upgrade --link` (#174).
- **Po `git pull` + `just up` lokalna baza jest pusta** (nowy wolumen). Dane odzyskasz procedurą z README
  („Migracja wolumenu PostgreSQL”: backup na starym układzie, restore na nowym) albo `just prune` i start od zera.
  Stary wolumen `*_postgres_data` zostaje nietknięty do ręcznego usunięcia.
- Produkcja: tylko w oknie serwisowym, wg tej procedury. Obraz Postgresa ma `volume-guard`, który odmawia startu, gdy
  stary wolumen trafi pod nowy mount.

### Frontend na webpack (django-compressor usunięty)

- Style (SCSS) i JavaScript (moduły ES) budowane przez webpack 5 + Babel + Sass + PostCSS i podawane przez
  `django-webpack-loader`; Chart.js i flatpickr pochodzą z npm. Źródła: `webpack/src/`.
- Nowa usługa compose `node` (`http://localhost:3000` — dev-server z live reloadem i proxy do Django).
  Po aktualizacji lokalnej: `just build` i `docker compose up -d --renew-anon-volumes`.
- Zależności `django-compressor`, `rcssmin`, `rjsmin` usunięte; ze `start` produkcji znika `compress --force`
  (bundle powstają w obrazie, w etapie `client-builder`). `just prod-build` wystarcza; nic nie trzeba robić na serwerze.
- Testy E2E wymagają zbudowanych bundli: `just build-js` (CI robi to samo).

### Kolejka zadań (RQ) zamiast APScheduler

- Nowe usługi compose `worker` (RQ) i `cron` (`rqcron`) — **`cron` zawsze w jednej instancji**. Maile
  aktywacyjne i zmiany adresu są wysyłane przez kolejkę (3 ponowienia: 10 s, 1 min, 5 min); błąd SMTP nie
  kończy już żądania błędem 500. Po wyczerpaniu prób admini dostają mail (`mail_admins`).
- Zadania cykliczne nie działają już w procesach web, więc `WEB_CONCURRENCY > 1` jest bezpieczne.
  Zależność `apscheduler` usunięta.
- Nowa, opcjonalna zmienna `REDIS_QUEUE_URL` (domyślnie `REDIS_URL` z bazą `/1`) — kolejka ma osobną bazę
  Redisa, więc wyczyszczenie cache jej nie kasuje. `/healthz/` zwraca też pole `queue`.
- Po aktualizacji lokalnej: `docker compose up -d --renew-anon-volumes`.
- Uwierzytelnianie API tokenem (`Authorization: Bearer`), `GET /api/users/me`, model `AuthToken` (migracja
  `users.0007`); tokeny wystawia się w adminie, w bazie jest tylko ich skrót.

### Zmiany w konfiguracji (wymagają aktualizacji `.envs/.production/.django`)

- Zmienne poczty mają teraz prefiks `DJANGO_`: `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`,
  `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_EMAIL_USE_TLS`,
  `DJANGO_EMAIL_USE_SSL`, `DJANGO_EMAIL_TIMEOUT`. Stare nazwy bez prefiksu (`EMAIL_HOST` itd.)
  są jeszcze czytane jako fallback **tylko w tym wydaniu** — w następnym zostaną usunięte, więc
  zmień nazwy już teraz. Gdy ustawione są obie, wygrywa nazwa z `DJANGO_`. Pusta wartość
  (`DJANGO_EMAIL_HOST=`) liczy się jak brak zmiennej, więc nie przesłania starej nazwy.
- `REDIS_URL` jest wymagane — ustawienia i entrypoint nie mają już wartości domyślnej.
- Adresaci raportów o błędach (`ADMINS`, `MANAGERS`) pochodzą z `DJANGO_ADMINS` (lista po
  przecinku, `Imię <mail>` lub sam adres); domyślnie pusta.
- Nowe, opcjonalne: `DJANGO_STATIC_ROOT` (nadpisuje `STATIC_ROOT`) oraz plik `.envs/.secrets`
  (spoza gita), ładowany przez ustawienia, gdy istnieje. W produkcji compose przekazuje go jako
  opcjonalny `env_file`; wartości z `.envs/.production/.django` i `.postgres` mają przed nim
  pierwszeństwo.
- Statyki serwuje nginx (wolumen `production_django_static`), a nie WhiteNoise — zależność
  `whitenoise` została usunięta. Traefik ma nowy router `/static/` w `traefik.yml` (zmień w nim
  `example.com` jak w routerach istniejących). Po aktualizacji wykonaj `just prod-build` i `just prod-up`.
- Nowy, opcjonalny `DJANGO_API_ENABLE_DOCS` (domyślnie `True`; goła nazwa `API_ENABLE_DOCS` jest czytana
  jako fallback tylko w tym wydaniu): przełącznik `/api/docs`; na produkcji
  zalecane `False`.
- Nowy endpoint `/healthz/` i healthcheck kontenera `django`; Traefik i nginx czekają na `healthy`.
- Ustawienia same składają `DATABASE_URL` z `POSTGRES_*`, gdy nie jest ustawione, więc
  `docker compose exec django python manage.py …` działa bez `/entrypoint`.

## [1.0.2] — 2026-05-28

### Poprawki

- Usunięto zależności od zewnętrznych CDN — aplikacja działa w pełni offline
- Czcionki Inter i Fira Code są teraz hostowane lokalnie (zamiast Google Fonts)
- Chart.js i flatpickr są teraz hostowane lokalnie (zamiast jsDelivr CDN)
- Poprawiono wersję aplikacji w stopce strony (było `1.0.0-beta.1`)

## [1.0.0] — 2026-05-24

### Funkcje

- System głosowania na suchary (funny / dry) z optymistycznym UI i animacjami
- System osiągnięć z silnikiem reguł: odznaki lifetime, periodyczne i streak
- Powiadomienia o osiągnięciach w czasie rzeczywistym (SSE + bell inbox)
- Ukryte osiągnięcia — odblokowane po spełnieniu warunków
- Ranking autorów (leaderboard) z najlepszymi żartami i statystykami
- Profil użytkownika z heatmapą aktywności i wykresem głosów
- Tagowanie sucharów z autouzupełnianiem i filtrowaniem po tagach
- Wyszukiwanie sucharów i sortowanie wyników
- Formularz dodawania suchary z podglądem na żywo i harmonogramem publikacji
- System schedulowania: publikacja sucharów o wybranej godzinie (APScheduler)
- Zmiana adresu e-mail z potwierdzeniem przez bezpieczny token i możliwością cofnięcia
- Reset hasła przez e-mail z dopasowanymi szablonami
- Niestandardowy system autentykacji (bez django-allauth)
- Wyświetlana nazwa użytkownika (display name)
- Tryb ciemny / jasny z persystencją i płynnym przełączaniem
- Pełna internacjonalizacja (PL / EN) z obsługą 50+ języków w selektorze
- Komenda zarządzania do automatycznego uzupełniania tłumaczeń przez lokalny model AI
- Niestandardowy dropdown wyboru języka i sortowania w navbarze
- Udostępnianie sucharów (share link)
- Konfigurowalny link do zgłaszania błędów w stopce

### Infrastruktura / DevOps

- Docker Compose: środowisko lokalne i produkcyjne
- Produkcja: Gunicorn + Traefik 3 (SSL, routing) + Nginx (media proxy)
- Baza danych: PostgreSQL 18 z wbudowanymi skryptami do backupu
- Cache: Redis 7 + django-redis
- Harmonogram cyklicznych zadań: APScheduler + django-apscheduler (wbudowany w Django)
- Maile transakcyjne: Django mail backend (sync_to_async w widokach asynchronicznych)
- Minifikacja CSS/JS: django-compressor + rcssmin + rjsmin (production)
- Zarządzanie zależnościami: uv + uv.lock
- CI: GitHub Actions — lint (pre-commit) + testy jednostkowe + testy E2E
- Pre-commit hooks: ruff, ruff-format, djlint, django-upgrade
- Type checking: mypy + django-stubs
- Dev Container dla VS Code
- Dependabot dla automatycznych aktualizacji zależności
- justfile z komendami skróconymi dla lokalnego i produkcyjnego środowiska

### Dokumentacja

- README z pełną dokumentacją uruchomienia lokalnego i produkcyjnego
- CLAUDE.md — wytyczne dla agentów AI pracujących w projekcie
- Reguły kodowania i przepływ pracy w `.agent/rules.md`
