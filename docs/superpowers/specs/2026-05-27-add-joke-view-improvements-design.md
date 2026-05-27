# Add-Joke View Improvements — Design Spec

**Date:** 2026-05-27
**Scope:** Approach B — fix correctness, add UX polish, clean up dead code. No CDN removal.

---

## Background

The `SucharCreateView` + `SucharForm` + `suchar_form.js` pipeline has several correctness issues (private method access, hardcoded strings, dead code) and missing UX signals (no char counter, no loading state). This spec covers the full set of changes.

---

## Backend

### 1. Fix `SucharForm.save()` — remove `noqa: SLF001`

**Problem:** `SucharCreateView.post()` calls `form._save_tags(suchar)` directly after `form.save(commit=False)`, bypassing the normal Django `ModelForm` contract and requiring a `noqa` suppression.

**Fix:** Restructure `SucharForm.save()` to set `self.save_m2m` when called with `commit=False`, mirroring how Django's own `ModelForm` handles deferred M2M saves:

```python
def save(self, commit=True):
    instance = super().save(commit=False)
    if commit:
        instance.save()
        self._save_tags(instance)
    else:
        _base_save_m2m = getattr(self, 'save_m2m', None)
        def save_m2m():
            if _base_save_m2m:
                _base_save_m2m()
            self._save_tags(instance)
        self.save_m2m = save_m2m
    return instance
```

`SucharCreateView.post()` changes to:
```python
def _save():
    suchar = form.save(commit=False)
    suchar.author = request.user
    suchar.save()
    form.save_m2m()   # replaces form._save_tags(suchar)  # noqa: SLF001
```

`SucharUpdateView.post()` calls `form.save()` with `commit=True` — no change needed.

### 2. Text length validation

- Add `max_length=2000` to `Suchar.text` field.
- Add a migration (Postgres stores `TextField` and `CharField` identically but enforces the constraint).
- Add `clean_text()` to `SucharForm` to raise a `ValidationError` with a user-visible message before hitting the DB.

### 3. Tag length validation

- Add `clean_tags_input()` to `SucharForm`.
- After splitting on spaces/commas, check each tag name is ≤ 50 chars (matching `Tag.name.max_length`).
- Raise `ValidationError` listing the offending tags; no silent truncation or DB error.

### Tests

- Delete `test_vote_suchar` and `test_vote_suchar_edge_cases` from `suchary/tests.py` (they test the dead `suchary:vote` URL).
- Add tests for `clean_text()` (at limit, over limit) and `clean_tags_input()` (tag too long) to `suchary/test_forms.py`.

---

## Frontend — Correctness

### 4. Decouple preview placeholder from JS

**Problem:** `setupTextPreview()` in `suchar_form.js` hardcodes Polish: `'Tutaj pojawi się treść Twojego suchara...'`.

**Fix:**
- Template: add `data-placeholder="{% trans 'Your joke content will appear here...' %}"` on `#previewText`.
- JS: read `previewText.dataset.placeholder` instead of the hardcoded string.

### 5. Decouple tags API URL from JS

**Problem:** `fetchTags()` hardcodes `/api/suchary/tags`.

**Fix:**
- Template: add `data-tags-url="/api/suchary/tags"` on `#id_tags_input`.
- JS: read `tagsInput.dataset.tagsUrl` and append `?q=...` to it.

---

## Frontend — UX

### 6. Character counter

- Add `<small id="charCounter" class="char-counter"></small>` below the textarea in the template (no Bootstrap classes).
- `suchar_form.css` defines `.char-counter` using `var(--color-text-muted)` and adds `--char-counter-color-warn` / `--char-counter-color-error` states.
- JS updates the counter text (`0 / 2000`) on every `input` event. Colour changes:
  - Default: muted (`var(--color-text-muted)`)
  - ≥ 1700 chars: amber warning
  - ≥ 2000 chars: red (at limit)

### 7. Submit loading state

- On form `submit`, JS adds an `is-loading` class to the submit button and disables it.
- `suchar_form.css` defines `.btn.is-loading` with a CSS `::after` spinner (border-animation, no Bootstrap).
- On full-page re-render (form errors), `DOMContentLoaded` re-fires and the button re-initialises cleanly — no teardown needed.

---

## Cleanup

### 8. Remove dead `vote_suchar` view

`voting.js` calls `/api/suchary/{id}/vote` (confirmed). The `vote_suchar` function-based view in `views.py` is never reached.

Changes:
- Remove `vote_suchar` function from `suchary/views.py`.
- Remove `@login_required` import if it has no remaining uses.
- Remove the `path("<int:pk>/vote/", vote_suchar, name="vote")` pattern from `suchary/urls.py`.
- Remove `vote_suchar` import in `suchary/urls.py`.

---

## Files changed

| File | Change |
|------|--------|
| `suchar_overflow/suchary/models.py` | `max_length=2000` on `Suchar.text` |
| `suchar_overflow/suchary/migrations/0007_suchar_text_max_length.py` | New migration |
| `suchar_overflow/suchary/forms.py` | Restructure `save()`, add `clean_text()`, add `clean_tags_input()` |
| `suchar_overflow/suchary/views.py` | Remove `vote_suchar`, update `SucharCreateView.post()` |
| `suchar_overflow/suchary/urls.py` | Remove `vote` URL pattern |
| `suchar_overflow/suchary/tests.py` | Remove dead vote view tests |
| `suchar_overflow/suchary/test_forms.py` | Add validation tests |
| `suchar_overflow/templates/suchary/suchar_form.html` | Add `data-placeholder`, `data-tags-url`, char counter element |
| `suchar_overflow/static/js/pages/suchar_form.js` | Read data attrs, add counter + loading state |
| `suchar_overflow/static/css/pages/suchar_form.css` | Add `.char-counter` and `.btn.is-loading` styles |

---

## Out of scope

- CDN removal (Flatpickr) — deferred to a future Approach C.
- Any changes to `SucharUpdateView` logic beyond what falls out of the `save()` refactor.
- Voting JS or API changes.
