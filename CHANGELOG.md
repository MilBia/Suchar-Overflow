# Changelog

Wszystkie znaczące zmiany w projekcie są dokumentowane w tym pliku.

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
