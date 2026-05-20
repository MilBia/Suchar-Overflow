"""Management command to fill empty .po translation strings using a local AI model."""

import re
from pathlib import Path
from typing import Any

import httpx
import polib
from django.conf import settings
from django.core.management.base import BaseCommand
from openai import OpenAI

LANGUAGE_NAMES: dict[str, str] = {
    "ar": "Arabic",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "ca": "Catalan",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "kn": "Kannada",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "ml": "Malayalam",
    "mr": "Marathi",
    "nb": "Norwegian",
    "nl": "Dutch",
    "pa": "Punjabi",
    "pl": "Polish",
    "pt": "Portuguese",
    "pt_BR": "Brazilian Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sr": "Serbian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "zh_Hans": "Chinese (Simplified)",
    "zh_Hant": "Chinese (Traditional)",
}

# Prompt for models that support chat/completions (non-translategemma).
CHAT_SYSTEM_PROMPT = (
    "You are a professional translator working on a Django web application UI. "
    "Translate the given UI string from {source_language} to {target_language}. "
    "Rules: "
    "1. Output ONLY the translated string — no explanations, no quotes, nothing extra. "
    "2. Keep translations short and natural, matching the original tone and length. "
    "3. Preserve ALL format specifiers and markup exactly: %(name)s, {{0}}, %s, %d, "
    "<strong>, <br />, <a href=...>, and any other HTML tags. Never use Markdown. "
    "4. Never translate proper names and brand names (e.g. 'Suchar Overflow'). "
    "5. Treat words like 'Slug', 'Tier', 'Draft' as technical Django/web terms"
    " — do not translate them literally if they serve as UI labels. "
    "6. Pick one best translation — never output alternatives separated by '/' or '|'."
)

# Few-shot prompt template for translategemma via /v1/completions.
# The examples teach the model to produce concise UI labels, not definitions.
# Rules embedded in the template:
#   - preserve HTML tags verbatim, never convert to Markdown
#   - do not translate proper/brand names (e.g. "Suchar Overflow")
#   - output one translation only, never slash-separated alternatives
COMPLETIONS_PROMPT_TEMPLATE = """\
Translate {source_language} UI text to {target_language}. \
Output only the translation. Preserve HTML tags. \
Do not translate brand names. Pick one translation only.

Text: Home
Translation: {home_translation}

Text: Cancel
Translation: {cancel_translation}

Text: Save Changes
Translation: {save_changes_translation}

Text: {msgid}
Translation:"""

# Language-specific few-shot answers so the model sees the expected output style.
_FEW_SHOT_ANSWERS: dict[str, dict[str, str]] = {
    "ar": {"home": "الرئيسية", "cancel": "إلغاء", "save_changes": "حفظ التغييرات"},
    "bg": {"home": "Начало", "cancel": "Отказ", "save_changes": "Запазете промените"},
    "bn": {"home": "হোম", "cancel": "বাতিল করুন", "save_changes": "পরিবর্তন সংরক্ষণ করুন"},
    "ca": {"home": "Inici", "cancel": "Cancel·la", "save_changes": "Desa els canvis"},
    "cs": {"home": "Domů", "cancel": "Zrušit", "save_changes": "Uložit změny"},
    "da": {"home": "Hjem", "cancel": "Annuller", "save_changes": "Gem ændringer"},
    "de": {
        "home": "Startseite",
        "cancel": "Abbrechen",
        "save_changes": "Änderungen speichern",
    },
    "el": {"home": "Αρχική", "cancel": "Ακύρωση", "save_changes": "Αποθήκευση αλλαγών"},
    "es": {"home": "Inicio", "cancel": "Cancelar", "save_changes": "Guardar cambios"},
    "et": {
        "home": "Avaleht",
        "cancel": "Tühista",
        "save_changes": "Salvesta muudatused",
    },
    "fa": {"home": "خانه", "cancel": "لغو", "save_changes": "ذخیره تغییرات"},
    "fi": {
        "home": "Etusivu",
        "cancel": "Peruuta",
        "save_changes": "Tallenna muutokset",
    },
    "fr": {
        "home": "Accueil",
        "cancel": "Annuler",
        "save_changes": "Enregistrer les modifications",
    },
    "he": {"home": "דף הבית", "cancel": "ביטול", "save_changes": "שמור שינויים"},
    "hi": {"home": "होम", "cancel": "रद्द करें", "save_changes": "परिवर्तन सहेजें"},
    "hr": {"home": "Početna", "cancel": "Otkaži", "save_changes": "Spremi promjene"},
    "hu": {
        "home": "Főoldal",
        "cancel": "Mégse",
        "save_changes": "Változtatások mentése",
    },
    "id": {"home": "Beranda", "cancel": "Batal", "save_changes": "Simpan Perubahan"},
    "is": {"home": "Heim", "cancel": "Hætta við", "save_changes": "Vista breytingar"},
    "it": {"home": "Home", "cancel": "Annulla", "save_changes": "Salva modifiche"},
    "ja": {"home": "ホーム", "cancel": "キャンセル", "save_changes": "変更を保存"},
    "kn": {"home": "ಮನೆ", "cancel": "ರದ್ದುಮಾಡಿ", "save_changes": "ಬದಲಾವಣೆಗಳನ್ನು ಉಳಿಸಿ"},
    "ko": {"home": "홈", "cancel": "취소", "save_changes": "변경 사항 저장"},
    "lt": {
        "home": "Pagrindinis",
        "cancel": "Atšaukti",
        "save_changes": "Išsaugoti pakeitimus",
    },
    "lv": {"home": "Sākums", "cancel": "Atcelt", "save_changes": "Saglabāt izmaiņas"},
    "ml": {"home": "ഹോം", "cancel": "റദ്ദാക്കുക", "save_changes": "മാറ്റങ്ങൾ സംരക്ഷിക്കുക"},
    "mr": {"home": "मुखपृष्ठ", "cancel": "रद्द करा", "save_changes": "बदल जतन करा"},
    "nb": {"home": "Hjem", "cancel": "Avbryt", "save_changes": "Lagre endringer"},
    "nl": {
        "home": "Startpagina",
        "cancel": "Annuleren",
        "save_changes": "Wijzigingen opslaan",
    },
    "pa": {"home": "ਘਰ", "cancel": "ਰੱਦ ਕਰੋ", "save_changes": "ਬਦਲਾਅ ਸੁਰੱਖਿਅਤ ਕਰੋ"},
    "pl": {
        "home": "Strona główna",
        "cancel": "Anuluj",
        "save_changes": "Zapisz zmiany",
    },
    "pt": {
        "home": "Início",
        "cancel": "Cancelar",
        "save_changes": "Guardar alterações",
    },
    "pt_BR": {
        "home": "Início",
        "cancel": "Cancelar",
        "save_changes": "Salvar alterações",
    },
    "ro": {
        "home": "Acasă",
        "cancel": "Anulați",
        "save_changes": "Salvați modificările",
    },
    "ru": {
        "home": "Главная",
        "cancel": "Отмена",
        "save_changes": "Сохранить изменения",
    },
    "sk": {"home": "Domov", "cancel": "Zrušiť", "save_changes": "Uložiť zmeny"},
    "sl": {"home": "Domov", "cancel": "Prekliči", "save_changes": "Shrani spremembe"},
    "sr": {"home": "Почетна", "cancel": "Откажи", "save_changes": "Сачувај измене"},
    "sv": {"home": "Hem", "cancel": "Avbryt", "save_changes": "Spara ändringar"},
    "sw": {
        "home": "Nyumbani",
        "cancel": "Ghairi",
        "save_changes": "Hifadhi Mabadiliko",
    },
    "ta": {"home": "முகப்பு", "cancel": "ரத்து", "save_changes": "மாற்றங்களை சேமிக்கவும்"},
    "te": {"home": "హోమ్", "cancel": "రద్దు చేయి", "save_changes": "మార్పులు సేవ్ చేయి"},
    "th": {"home": "หน้าแรก", "cancel": "ยกเลิก", "save_changes": "บันทึกการเปลี่ยนแปลง"},
    "tr": {
        "home": "Ana Sayfa",
        "cancel": "İptal",
        "save_changes": "Değişiklikleri Kaydet",
    },
    "uk": {"home": "Головна", "cancel": "Скасувати", "save_changes": "Зберегти зміни"},
    "ur": {
        "home": "ہوم",
        "cancel": "منسوخ کریں",
        "save_changes": "تبدیلیاں محفوظ کریں",
    },
    "vi": {"home": "Trang chủ", "cancel": "Hủy", "save_changes": "Lưu thay đổi"},
    "zh": {"home": "首页", "cancel": "取消", "save_changes": "保存更改"},
    "zh_Hans": {"home": "首页", "cancel": "取消", "save_changes": "保存更改"},
    "zh_Hant": {"home": "首頁", "cancel": "取消", "save_changes": "儲存變更"},
}
_FEW_SHOT_FALLBACK = {
    "home": "Home",
    "cancel": "Cancel",
    "save_changes": "Save Changes",
}

# Responses longer than this multiple of the msgid are considered hallucinations.
# Only applied when msgid is longer than _MIN_MSGID_FOR_RATIO chars to avoid
# false positives on short strings (e.g. "The" → ratio would allow only 12 chars).
_MAX_LENGTH_RATIO = 4
_MIN_MSGID_FOR_RATIO = 20
_MAX_RESPONSE_CHARS = 500

# Pattern that indicates the model returned slash-separated alternatives.
_ALTERNATIVES_MARKERS = (" / ", " | ", " OR ", " LUB ", " lub ")
# Matches unspaced slash between words (e.g. "Ten/Ta/To") in short responses.
_UNSPACED_SLASH_RE = re.compile(r"\w/\w")

# Matches Python format specifiers: %(name)s, %s, %d, %f, %(key)r, etc.
_FORMAT_SPECIFIER_RE = re.compile(r"%(?:\(\w+\))?[sdfrx%]")

# Terms that must never be translated — copied verbatim from msgid.
_PROTECTED_TERMS: frozenset[str] = frozenset({"Suchar Overflow"})


def _is_translategemma(model: str) -> bool:
    return "translategemma" in model.lower()


def _looks_like_hallucination(msgid: str, response: str) -> bool:
    """Return True if the response is suspiciously long."""
    return len(response) > _MAX_RESPONSE_CHARS or (
        len(msgid) >= _MIN_MSGID_FOR_RATIO
        and len(response) > len(msgid) * _MAX_LENGTH_RATIO
    )


def _has_multiple_alternatives(response: str) -> bool:
    """Return True if the model returned slash/pipe-separated alternatives."""
    if any(marker in response for marker in _ALTERNATIVES_MARKERS):
        return True
    # Also catch unspaced slash alternatives like "Ten/Ta/To".
    return bool(_UNSPACED_SLASH_RE.search(response))


def _has_markdown_html_corruption(msgid: str, response: str) -> bool:
    """Return True if the msgid has HTML tags but the response used Markdown instead."""
    if "<strong>" not in msgid and "<em>" not in msgid:
        return False
    return "**" in response and "<strong>" not in response


def _has_format_specifier_corruption(msgid: str, response: str) -> bool:
    """Return True if format specifiers from msgid are missing or corrupted in response.

    Catches cases like %(name)s becoming % (name)s (space injected by model).
    """
    expected = _FORMAT_SPECIFIER_RE.findall(msgid)
    if not expected:
        return False
    actual = _FORMAT_SPECIFIER_RE.findall(response)
    return sorted(expected) != sorted(actual)


class Command(BaseCommand):
    help = "Fill empty .po translation strings using a local OpenAI-compatible AI model"

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            type=str,
            required=True,
            help="Base URL of the OpenAI-compatible API (e.g. http://localhost:11434/v1)",
        )
        parser.add_argument(
            "--model",
            type=str,
            default="translategemma",
            help="Model name to use for translation (default: translategemma)",
        )
        parser.add_argument(
            "--language",
            type=str,
            default=None,
            metavar="LANG_CODE",
            help="Target language code to process (e.g. pl, en). Defaults to all.",
        )
        parser.add_argument(
            "--source-lang",
            type=str,
            default="en",
            metavar="LANG_CODE",
            help="Source language code of the msgid strings (default: en).",
        )
        parser.add_argument(
            "--locale-dir",
            type=str,
            default=None,
            help="Path to the locale directory. Defaults to Django's LOCALE_PATHS[0].",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="translate_all",
            help="Re-translate all entries, including already-translated ones.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be translated without writing any changes.",
        )
        parser.add_argument(
            "--api-key",
            type=str,
            default="nokey",
            help="API key for the endpoint (default: 'nokey' for local models).",
        )

    def handle(self, *args, **options):
        locale_dir = self._resolve_locale_dir(options["locale_dir"])
        if locale_dir is None:
            return

        url = options["url"]
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"

        model = options["model"]
        api_key = options["api_key"]
        source_lang = options["source_lang"]

        # For translategemma we bypass the OpenAI SDK because its content part schema
        # strips unknown fields (source_lang_code, target_lang_code) before sending.
        if _is_translategemma(model):
            openai_client = None
            http_client = httpx.Client(
                base_url=url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=120.0,
            )
        else:
            openai_client = OpenAI(base_url=url, api_key=api_key)
            http_client = None

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("DRY RUN — no files will be modified."),
            )

        po_glob = (
            f"{options['language']}/LC_MESSAGES/*.po"
            if options["language"]
            else "*/LC_MESSAGES/*.po"
        )
        po_files = sorted(locale_dir.glob(po_glob))

        if not po_files:
            self.stdout.write(self.style.WARNING(f"No .po files found in {locale_dir}"))
            if http_client:
                http_client.close()
            return

        total = 0
        try:
            total = self._process_po_files(
                po_files=po_files,
                openai_client=openai_client,
                http_client=http_client,
                model=model,
                source_lang=source_lang,
                translate_all=options["translate_all"],
                dry_run=options["dry_run"],
            )
        finally:
            if http_client:
                http_client.close()

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Total entries translated: {total}"),
        )
        if not options["dry_run"] and total > 0:
            self.stdout.write(
                "Run 'manage.py compilemessages' to compile the updated .po files.",
            )

    def _process_po_files(  # noqa: PLR0913
        self,
        po_files: list[Path],
        openai_client: OpenAI | None,
        http_client: httpx.Client | None,
        model: str,
        source_lang: str,
        *,
        translate_all: bool,
        dry_run: bool,
    ) -> int:
        total = 0
        for po_path in po_files:
            lang_code = po_path.parts[-3]
            if lang_code == source_lang:
                self.stdout.write(
                    f"\nSkipping {po_path.name} [{lang_code}]"
                    f" — same as source language.",
                )
                continue
            lang_name = LANGUAGE_NAMES.get(lang_code, lang_code)
            self.stdout.write(
                f"\nProcessing {po_path.name} [{lang_code} — {lang_name}]",
            )
            total += self._translate_file(
                openai_client=openai_client,
                http_client=http_client,
                model=model,
                po_path=po_path,
                lang_code=lang_code,
                lang_name=lang_name,
                source_lang=source_lang,
                translate_all=translate_all,
                dry_run=dry_run,
            )
        return total

    def _resolve_locale_dir(self, locale_dir_option: str | None) -> Path | None:
        if locale_dir_option:
            path = Path(locale_dir_option)
        else:
            locale_paths = getattr(settings, "LOCALE_PATHS", [])
            if not locale_paths:
                self.stderr.write(
                    self.style.ERROR("No LOCALE_PATHS configured in Django settings."),
                )
                return None
            path = Path(locale_paths[0])

        if not path.exists():
            self.stderr.write(self.style.ERROR(f"Locale directory not found: {path}"))
            return None

        return path

    def _translate_file(  # noqa: PLR0913, C901
        self,
        openai_client: OpenAI | None,
        http_client: httpx.Client | None,
        model: str,
        po_path: Path,
        lang_code: str,
        lang_name: str,
        source_lang: str,
        *,
        translate_all: bool,
        dry_run: bool,
    ) -> int:
        try:
            po = polib.pofile(str(po_path))
        except OSError as exc:
            self.stderr.write(self.style.ERROR(f"  Cannot read {po_path}: {exc}"))
            return 0

        entries = [e for e in po if e.msgid and (translate_all or not e.msgstr)]

        if not entries:
            self.stdout.write("  Nothing to translate.")
            return 0

        self.stdout.write(f"  {len(entries)} entries to translate.")
        translated = 0
        skipped = 0

        for entry in entries:
            if entry.msgid in _PROTECTED_TERMS:
                if dry_run:
                    self.stdout.write(
                        f"  [dry] {entry.msgid!r}\n"
                        f"       -> {entry.msgid!r} (protected)",
                    )
                else:
                    entry.msgstr = entry.msgid
                    self.stdout.write(
                        f"  {entry.msgid!r} -> {entry.msgid!r}"
                        " (protected, verbatim copy)",
                    )
                translated += 1
                continue

            location_hint = entry.occurrences[0][0] if entry.occurrences else ""
            translation = self._translate_entry(
                openai_client=openai_client,
                http_client=http_client,
                model=model,
                msgid=entry.msgid,
                source_lang=source_lang,
                target_lang_code=lang_code,
                lang_name=lang_name,
                location_hint=location_hint,
            )
            if translation is None:
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(f"  [dry] {entry.msgid!r}\n       -> {translation!r}")
            else:
                entry.msgstr = translation
                self.stdout.write(f"  {entry.msgid!r} -> {translation!r}")
            translated += 1

        if skipped:
            self.stdout.write(
                self.style.WARNING(f"  Skipped (errors/hallucinations): {skipped}"),
            )

        if not dry_run and translated > 0:
            try:
                po.save(str(po_path))
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Saved {translated} translations to {po_path.name}",
                    ),
                )
            except OSError as exc:
                self.stderr.write(
                    self.style.ERROR(f"  Failed to save {po_path}: {exc}"),
                )

        return translated

    def _translate_entry(  # noqa: PLR0913
        self,
        openai_client: OpenAI | None,
        http_client: httpx.Client | None,
        model: str,
        msgid: str,
        source_lang: str,
        target_lang_code: str,
        lang_name: str,
        location_hint: str,
    ) -> str | None:
        try:
            if http_client is not None:
                result = self._translate_via_httpx(
                    http_client,
                    model,
                    msgid,
                    source_lang,
                    target_lang_code,
                    lang_name,
                )
            else:
                result = self._translate_via_openai(  # type: ignore[arg-type]
                    openai_client,
                    model,
                    msgid,
                    source_lang,
                    lang_name,
                    location_hint,
                )
        except httpx.HTTPStatusError as exc:
            self.stderr.write(
                self.style.ERROR(f"  API error for {msgid!r}: {exc.response.text}"),
            )
            return None
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.ERROR(f"  API error for {msgid!r}: {exc}"))
            return None

        return self._validate_result(msgid, result)

    def _validate_result(self, msgid: str, result: str | None) -> str | None:
        if result is None:
            return None
        if _looks_like_hallucination(msgid, result):
            self.stderr.write(
                self.style.WARNING(
                    f"  Hallucination for {msgid!r} "
                    f"(len {len(result)} vs {len(msgid)}), skipping.",
                ),
            )
            return None
        if _has_multiple_alternatives(result):
            self.stderr.write(
                self.style.WARNING(
                    f"  Multiple alternatives for {msgid!r}: {result!r}, skipping.",
                ),
            )
            return None
        if _has_markdown_html_corruption(msgid, result):
            self.stderr.write(
                self.style.WARNING(
                    f"  HTML→Markdown corruption for {msgid!r}, skipping.",
                ),
            )
            return None
        if _has_format_specifier_corruption(msgid, result):
            self.stderr.write(
                self.style.WARNING(
                    f"  Format specifier corruption for {msgid!r}: {result!r},"
                    " skipping.",
                ),
            )
            return None
        return result

    def _translate_via_httpx(  # noqa: PLR0913
        self,
        client: httpx.Client,
        model: str,
        msgid: str,
        source_lang: str,
        target_lang_code: str,
        lang_name: str,
    ) -> str | None:
        """Use /v1/completions for translategemma.

        chat/completions breaks its Jinja template in LM Studio.
        """
        source_lang_name = LANGUAGE_NAMES.get(source_lang, source_lang)
        few_shot = _FEW_SHOT_ANSWERS.get(target_lang_code, _FEW_SHOT_FALLBACK)
        prompt = COMPLETIONS_PROMPT_TEMPLATE.format(
            source_language=source_lang_name,
            target_language=lang_name,
            home_translation=few_shot["home"],
            cancel_translation=few_shot["cancel"],
            save_changes_translation=few_shot["save_changes"],
            msgid=msgid,
        )
        # Scale max_tokens to the source length to limit runaway responses.
        max_tokens = max(64, min(len(msgid) * 3, 512))
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "stop": ["\n\nText:", "\nText:", "\n\n"],
        }
        response = client.post("/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["text"].strip()

    def _translate_via_openai(  # noqa: PLR0913
        self,
        client: OpenAI,
        model: str,
        msgid: str,
        source_lang: str,
        lang_name: str,
        location_hint: str,
    ) -> str | None:
        source_lang_name = LANGUAGE_NAMES.get(source_lang, source_lang)
        user_content = msgid
        if location_hint:
            user_content = f"[Context: {location_hint}]\n{msgid}"
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": CHAT_SYSTEM_PROMPT.format(
                        source_language=source_lang_name,
                        target_language=lang_name,
                    ),
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            temperature=0.1,
            max_tokens=max(64, min(len(msgid) * 3, 512)),
        )
        return response.choices[0].message.content.strip()
