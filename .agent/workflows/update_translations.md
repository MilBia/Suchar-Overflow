---
description: Uzupełnianie i aktualizacja tłumaczeń po dodaniu nowych funkcji (Django).
---
# Workflow dla tłumaczeń (Django i Frontend)

Ten workflow przypomina o konieczności pamiętania o tłumaczeniach (i18n) podczas pracy nad backendem i frontendem w Django.

## 1. Pamiętaj podczas pracy nad kodem (Frontend i widoki Django)
- Zawsze oznaczaj każdą widoczną dla użytkownika treść do tłumaczenia.
- **W szablonach Django (`.html`):** Używaj tagów `{% trans "Tekst" %}` lub `{% blocktrans %}`.
- **W kodzie Pythona (`views.py`, `forms.py`, itp.):** Używaj funkcji `gettext_lazy` zaimportowanej jako `_` (np. `_("Tekst")`).
- Zanim wyślesz zmianę, upewnij się, że opisy na błędach, nowe powiadomienia, czy etykiety formularzy też są poprawnie opatrzone tekstami obsługującymi tłumaczenia.

## 2. Pod koniec pracy z nowym feature'em (aktualizacja plików .po)
Na sam koniec tworzenia nowej funkcjonalności (widocznej z zewnątrz) wymuszone jest zaktualizowanie plików tłumaczeń w oparciu o nowe modyfikacje.

Krok 1: Uruchom `makemessages` dla języka polskiego i angielskiego w kontenerze Django.
// turbo
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py makemessages -l pl -l en
```

Krok 2: Otwórz zaktualizowane pliki `.po` (w katalogu `locale/pl/LC_MESSAGES/django.po` itd.) używając wyszukiwarki lub edytora i po kolei uzupełnij brakujące pozycje `msgstr ""` nowymi tekstami.

Krok 3: Kiedy wszystkie stringi `msgid` otrzymają pasujące tłumaczenia `msgstr`, dokonaj kompilacji tłumaczeń poprzez proces `compilemessages`.
// turbo
```bash
docker compose -f docker-compose.local.yml run --rm django python manage.py compilemessages
```

Krok 4: Sprawdź lokalnie i wrzuć do Git wszystkie zaktualizowane (i poprawnie uzupełnione) pliki z tłumaczeniami.
