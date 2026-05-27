# Add-Joke View Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix correctness issues in the add-joke form/view pipeline, add UX polish (char counter, loading state), and remove the dead `vote_suchar` view.

**Architecture:** All backend changes are in the `suchary` app — form, model, view, and URL files. Frontend changes are in the `suchar_form.html` template, `suchar_form.js`, and `suchar_form.css`. No new files created except one migration.

**Tech Stack:** Django 5.2, async class-based views with `sync_to_async`, Django Ninja (API), Jinja2 templates, vanilla JS, CSS custom properties.

---

## File Map

| File | Change |
|------|--------|
| `suchar_overflow/suchary/forms.py` | Restructure `save()`, add `clean_text()`, `clean_tags_input()` |
| `suchar_overflow/suchary/models.py` | Add `max_length=2000` to `Suchar.text` |
| `suchar_overflow/suchary/migrations/0007_suchar_text_max_length.py` | New auto-generated migration |
| `suchar_overflow/suchary/views.py` | Update `SucharCreateView.post()`; remove `vote_suchar` and its import |
| `suchar_overflow/suchary/urls.py` | Remove `vote` URL pattern and `vote_suchar` import |
| `suchar_overflow/suchary/tests.py` | Remove `test_vote_suchar` and `test_vote_suchar_edge_cases` |
| `suchar_overflow/suchary/test_forms.py` | Update tag tests to use `save_m2m()`; add `clean_text` and `clean_tags_input` tests |
| `suchar_overflow/templates/suchary/suchar_form.html` | Add `data-placeholder`, `data-tags-url`, char counter `<small>` |
| `suchar_overflow/static/js/pages/suchar_form.js` | Read data attrs; add char counter logic; add submit loading state |
| `suchar_overflow/static/css/pages/suchar_form.css` | Add `.char-counter` and `.btn.is-loading` styles |

---

## Task 1: Refactor `SucharForm.save()` to expose `save_m2m`

Removes the `# noqa: SLF001` from the create view and from all tag tests by making `save(commit=False)` set a proper `save_m2m` callable.

**Files:**
- Modify: `suchar_overflow/suchary/forms.py`
- Modify: `suchar_overflow/suchary/views.py`
- Modify: `suchar_overflow/suchary/test_forms.py`

- [ ] **Step 1: Write a failing test that uses `save_m2m()`**

Append to `suchar_overflow/suchary/test_forms.py`:

```python
@pytest.mark.django_db
def test_save_m2m_applies_tags():
    """save(commit=False) + save_m2m() must apply tags without calling _save_tags directly."""
    user = make_user()
    form = SucharForm(data=form_data(tags_input="it, python"))
    assert form.is_valid(), form.errors
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()
    slugs = set(instance.tags.values_list("slug", flat=True))
    assert slugs == {"it", "python"}
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
just test suchar_overflow/suchary/test_forms.py::test_save_m2m_applies_tags
```

Expected: FAIL — `form.save_m2m()` doesn't apply tags (current `save()` only sets them when `commit=True`).

- [ ] **Step 3: Restructure `SucharForm.save()` in `forms.py`**

Replace the current `save()` method (lines 63–67 of `suchar_overflow/suchary/forms.py`):

```python
    def save(self, commit=True):  # noqa: FBT002
        instance = super().save(commit=commit)
        if commit:
            self._save_tags(instance)
        return instance
```

With:

```python
    def save(self, commit=True):  # noqa: FBT002
        instance = super().save(commit=False)
        if commit:
            instance.save()
            self._save_tags(instance)
        else:
            _base_save_m2m = self.save_m2m  # set by Django's ModelForm.save(commit=False)
            def save_m2m():
                _base_save_m2m()
                self._save_tags(instance)
            self.save_m2m = save_m2m
        return instance
```

- [ ] **Step 4: Update `SucharCreateView.post()` in `views.py`**

Replace the `_save` inner function (lines 118–122 of `suchar_overflow/suchary/views.py`):

```python
        def _save():
            suchar = form.save(commit=False)
            suchar.author = request.user
            suchar.save()
            form._save_tags(suchar)  # noqa: SLF001
```

With:

```python
        def _save():
            suchar = form.save(commit=False)
            suchar.author = request.user
            suchar.save()
            form.save_m2m()
```

- [ ] **Step 5: Update existing tag tests in `test_forms.py` to use `save_m2m()`**

In `suchar_overflow/suchary/test_forms.py`, there are six tests (`test_tags_comma_separated`, `test_tags_space_separated`, `test_tags_mixed_separators`, `test_tags_empty_input_clears_tags`, `test_tags_deduplication_same_slug`, `test_tags_reuse_existing_tag`, `test_tags_invalid_slug_skipped`) that each contain this pattern:

```python
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form._save_tags(instance)  # noqa: SLF001
```

Replace every occurrence with:

```python
    instance = form.save(commit=False)
    instance.author = user
    instance.save()
    form.save_m2m()
```

(Seven occurrences total — one per test function.)

- [ ] **Step 6: Run all suchary form tests**

```bash
just test suchar_overflow/suchary/test_forms.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add suchar_overflow/suchary/forms.py suchar_overflow/suchary/views.py suchar_overflow/suchary/test_forms.py
git commit -m "refactor: expose save_m2m on SucharForm, remove private _save_tags calls from view"
```

---

## Task 2: Add text length validation

Enforces a 2000-character limit at both the model and form level.

**Files:**
- Modify: `suchar_overflow/suchary/models.py`
- Create: `suchar_overflow/suchary/migrations/0007_suchar_text_max_length.py` (auto-generated)
- Modify: `suchar_overflow/suchary/forms.py`
- Modify: `suchar_overflow/suchary/test_forms.py`

- [ ] **Step 1: Write failing tests**

Append to `suchar_overflow/suchary/test_forms.py`:

```python
# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_text_too_long_is_rejected():
    form = SucharForm(data=form_data(text="a" * 2001))
    assert not form.is_valid()
    assert "text" in form.errors


@pytest.mark.django_db
def test_text_at_limit_is_accepted():
    form = SucharForm(data=form_data(text="a" * 2000))
    assert form.is_valid(), form.errors
```

- [ ] **Step 2: Run to confirm they fail**

```bash
just test suchar_overflow/suchary/test_forms.py::test_text_too_long_is_rejected suchar_overflow/suchary/test_forms.py::test_text_at_limit_is_accepted
```

Expected: `test_text_too_long_is_rejected` FAILS (form is valid when it shouldn't be), `test_text_at_limit_is_accepted` PASSES.

- [ ] **Step 3: Add `max_length=2000` to `Suchar.text` in `models.py`**

In `suchar_overflow/suchary/models.py`, change line 16:

```python
    text = models.TextField(_("Suchar text"))
```

To:

```python
    text = models.TextField(_("Suchar text"), max_length=2000)
```

- [ ] **Step 4: Generate the migration**

```bash
docker-compose -f docker-compose.local.yml exec -T django bash -c \
  "cd /app && python manage.py makemigrations suchary --settings=config.settings.local"
```

This creates `suchar_overflow/suchary/migrations/0007_suchar_text_max_length.py`. Verify the file exists before continuing.

- [ ] **Step 5: Add `clean_text()` to `SucharForm`**

In `suchar_overflow/suchary/forms.py`, add `clean_text()` after `clean_published_at()` (after line 61):

```python
    def clean_text(self):
        text = self.cleaned_data.get("text", "")
        if len(text) > 2000:  # noqa: PLR2004
            raise forms.ValidationError(
                _("Joke cannot exceed 2000 characters (currently %(count)d)."),
                params={"count": len(text)},
            )
        return text
```

- [ ] **Step 6: Run tests**

```bash
just test suchar_overflow/suchary/test_forms.py
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add suchar_overflow/suchary/models.py \
        suchar_overflow/suchary/migrations/0007_suchar_text_max_length.py \
        suchar_overflow/suchary/forms.py \
        suchar_overflow/suchary/test_forms.py
git commit -m "feat: enforce 2000-char limit on joke text at model and form level"
```

---

## Task 3: Add tag length validation

Rejects individual tag names longer than 50 characters (the `Tag.name` column limit) with a user-visible error instead of a silent DB error.

**Files:**
- Modify: `suchar_overflow/suchary/forms.py`
- Modify: `suchar_overflow/suchary/test_forms.py`

- [ ] **Step 1: Write failing tests**

Append to `suchar_overflow/suchary/test_forms.py`:

```python
# ---------------------------------------------------------------------------
# clean_tags_input
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tag_too_long_is_rejected():
    long_tag = "a" * 51
    form = SucharForm(data=form_data(tags_input=long_tag))
    assert not form.is_valid()
    assert "tags_input" in form.errors


@pytest.mark.django_db
def test_tag_at_limit_is_accepted():
    tag_at_limit = "a" * 50
    form = SucharForm(data=form_data(tags_input=tag_at_limit))
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_mixed_tags_one_too_long_is_rejected():
    form = SucharForm(data=form_data(tags_input="python, " + "a" * 51))
    assert not form.is_valid()
    assert "tags_input" in form.errors
```

- [ ] **Step 2: Run to confirm they fail**

```bash
just test suchar_overflow/suchary/test_forms.py::test_tag_too_long_is_rejected suchar_overflow/suchary/test_forms.py::test_tag_at_limit_is_accepted suchar_overflow/suchary/test_forms.py::test_mixed_tags_one_too_long_is_rejected
```

Expected: the two rejection tests FAIL (form is valid when it shouldn't be), the limit test PASSES.

- [ ] **Step 3: Add `clean_tags_input()` to `SucharForm`**

In `suchar_overflow/suchary/forms.py`, add `clean_tags_input()` after `clean_text()`:

```python
    def clean_tags_input(self):
        tags_input = self.cleaned_data.get("tags_input", "")
        normalized = tags_input.replace(",", " ")
        tag_names = [t.strip() for t in normalized.split() if t.strip()]
        too_long = [t for t in tag_names if len(t) > 50]  # noqa: PLR2004
        if too_long:
            raise forms.ValidationError(
                _("Tag names must be 50 characters or fewer: %(tags)s"),
                params={"tags": ", ".join(too_long)},
            )
        return tags_input
```

- [ ] **Step 4: Run tests**

```bash
just test suchar_overflow/suchary/test_forms.py
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add suchar_overflow/suchary/forms.py suchar_overflow/suchary/test_forms.py
git commit -m "feat: validate tag names are at most 50 chars before saving"
```

---

## Task 4: Remove dead `vote_suchar` view

`voting.js` calls `/api/suchary/{id}/vote` exclusively. The `vote_suchar` function-based view and its URL are unreachable.

**Files:**
- Modify: `suchar_overflow/suchary/tests.py`
- Modify: `suchar_overflow/suchary/urls.py`
- Modify: `suchar_overflow/suchary/views.py`

- [ ] **Step 1: Delete the two dead test functions from `tests.py`**

In `suchar_overflow/suchary/tests.py`, delete `test_vote_suchar` (lines 38–83) and `test_vote_suchar_edge_cases` (lines 171–199) in their entirety, including blank lines and decorators.

- [ ] **Step 2: Remove the vote URL pattern and import from `urls.py`**

In `suchar_overflow/suchary/urls.py`:

- Delete line 6: `from .views import vote_suchar`
- Delete the URL pattern: `path("<int:pk>/vote/", vote_suchar, name="vote"),`

The file should look like:

```python
from django.urls import path

from .views import SucharCreateView
from .views import SucharListView
from .views import SucharUpdateView

app_name = "suchary"

urlpatterns = [
    path("", SucharListView.as_view(), name="list"),
    path("add/", SucharCreateView.as_view(), name="add"),
    path("update/<int:pk>/", SucharUpdateView.as_view(), name="update"),
]
```

- [ ] **Step 3: Remove `vote_suchar` from `views.py`**

In `suchar_overflow/suchary/views.py`:

- Delete line 2: `from django.contrib.auth.decorators import login_required` (only used by `vote_suchar`)
- Delete the entire `vote_suchar` function (lines 174–201, from the `@login_required` decorator through `return redirect("suchary:list")`)

- [ ] **Step 4: Run tests to confirm nothing breaks**

```bash
just test suchar_overflow/suchary/
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add suchar_overflow/suchary/tests.py \
        suchar_overflow/suchary/urls.py \
        suchar_overflow/suchary/views.py
git commit -m "chore: remove dead vote_suchar view superseded by API endpoint"
```

---

## Task 5: Frontend — decouple hardcoded strings from JS

Moves the preview placeholder and the tags API URL out of JS and into template `data-` attributes.

**Files:**
- Modify: `suchar_overflow/templates/suchary/suchar_form.html`
- Modify: `suchar_overflow/static/js/pages/suchar_form.js`

- [ ] **Step 1: Add `data-placeholder` to `#previewText` in the template**

In `suchar_overflow/templates/suchary/suchar_form.html`, find the `#previewText` paragraph (line ~115):

```html
            <p class="mb-4 preview-text text-muted fst-italic" id="previewText">
              {% trans "Your joke content will appear here..." %}
            </p>
```

Replace with:

```html
            <p class="mb-4 preview-text text-muted fst-italic"
               id="previewText"
               data-placeholder="{% trans 'Your joke content will appear here...' %}">
              {% trans "Your joke content will appear here..." %}
            </p>
```

- [ ] **Step 2: Add `data-tags-url` to `#id_tags_input` in the template**

Find the tags input (line ~54):

```html
                <input type="text"
                       name="tags_input"
                       class="form-control"
                       placeholder="{% trans 'e.g. it, programming, school' %}"
                       id="id_tags_input"
                       value="{{ form.tags_input.value|default_if_none:'' }}"
                       autocomplete="off" />
```

Replace with:

```html
                <input type="text"
                       name="tags_input"
                       class="form-control"
                       placeholder="{% trans 'e.g. it, programming, school' %}"
                       id="id_tags_input"
                       value="{{ form.tags_input.value|default_if_none:'' }}"
                       data-tags-url="/api/suchary/tags"
                       autocomplete="off" />
```

- [ ] **Step 3: Update `setupTextPreview()` in `suchar_form.js`**

In `suchar_overflow/static/js/pages/suchar_form.js`, find `setupTextPreview()` (lines 27–41). Replace the hardcoded Polish string inside the `else` branch:

```javascript
                    previewText.textContent = 'Tutaj pojawi się treść Twojego suchara...';
```

With:

```javascript
                    previewText.textContent = previewText.dataset.placeholder || '';
```

- [ ] **Step 4: Update `fetchTags()` in `suchar_form.js`**

In the `setupTags()` method, find `fetchTags` (line ~104):

```javascript
            const fetchTags = async (query) => {
                try {
                    const response = await fetch(`/api/suchary/tags?q=${encodeURIComponent(query)}`);
```

Replace with:

```javascript
            const fetchTags = async (query) => {
                try {
                    const tagsUrl = tagsInput.dataset.tagsUrl;
                    const response = await fetch(`${tagsUrl}?q=${encodeURIComponent(query)}`);
```

- [ ] **Step 5: Run pre-commit and unit tests**

```bash
pre-commit run --all-files
pre-commit run --all-files  # second run to confirm clean
just test
```

Expected: all hooks pass, all unit tests pass.

- [ ] **Step 6: Commit**

```bash
git add suchar_overflow/templates/suchary/suchar_form.html \
        suchar_overflow/static/js/pages/suchar_form.js
git commit -m "refactor: move hardcoded placeholder and API URL from JS into template data attrs"
```

---

## Task 6: Character counter

Displays a live `0 / 2000` counter below the textarea, styled with project CSS variables (no Bootstrap).

**Files:**
- Modify: `suchar_overflow/static/css/pages/suchar_form.css`
- Modify: `suchar_overflow/templates/suchary/suchar_form.html`
- Modify: `suchar_overflow/static/js/pages/suchar_form.js`

- [ ] **Step 1: Add CSS for `.char-counter` to `suchar_form.css`**

Append to `suchar_overflow/static/css/pages/suchar_form.css`:

```css
/* Character counter below textarea */
.char-counter {
    display: block;
    text-align: right;
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: 0.25rem;
    transition: color 0.2s ease;
}

.char-counter.is-warning {
    color: var(--bs-warning);
}

.char-counter.is-error {
    color: var(--bs-danger);
    font-weight: 600;
}
```

- [ ] **Step 2: Add `#charCounter` element to the template**

In `suchar_overflow/templates/suchary/suchar_form.html`, find the text field block (lines ~37–47):

```html
            <div class="mb-4">
              <label for="id_text" class="form-label fw-bold">{% trans "Joke Content" %}</label>
              <textarea name="text"
                        cols="40"
                        rows="10"
                        class="form-control form-control-lg"
                        placeholder="{% trans 'Why did the chicken cross the road?' %}"
                        required
                        id="id_text">{{ form.text.value|default_if_none:'' }}</textarea>
              <div class="form-text">{% trans "Remember, the drier the better." %}</div>
            </div>
```

Replace with:

```html
            <div class="mb-4">
              <label for="id_text" class="form-label fw-bold">{% trans "Joke Content" %}</label>
              <textarea name="text"
                        cols="40"
                        rows="10"
                        class="form-control form-control-lg"
                        placeholder="{% trans 'Why did the chicken cross the road?' %}"
                        required
                        maxlength="2000"
                        id="id_text">{{ form.text.value|default_if_none:'' }}</textarea>
              <div class="form-text">{% trans "Remember, the drier the better." %}</div>
              <small id="charCounter" class="char-counter">0 / 2000</small>
            </div>
```

- [ ] **Step 3: Add `charCounter` to the `elements` object in `suchar_form.js`**

In `suchar_overflow/static/js/pages/suchar_form.js`, find the `elements` object (lines ~6–18) and add `charCounter`:

```javascript
        elements: {
            textInput: document.getElementById('id_text'),
            tagsInput: document.getElementById('id_tags_input'),
            tagsDropdown: document.getElementById('tags-dropdown'),
            previewText: document.getElementById('previewText'),
            previewTags: document.getElementById('previewTags'),
            scheduleCheck: document.getElementById('scheduleCheck'),
            scheduleContainer: document.getElementById('scheduleContainer'),
            publishedAtInput: document.getElementById('id_published_at'),
            suggestionsBox: document.getElementById('tags-suggestions'),
            form: document.querySelector('form'),
            dateError: document.getElementById('dateError'),
            charCounter: document.getElementById('charCounter'),
        },
```

- [ ] **Step 4: Add `setupCharCounter()` method to `SucharForm` object and call it from `init()`**

In `suchar_overflow/static/js/pages/suchar_form.js`, add `setupCharCounter()` inside the `SucharForm` object (after `setupTextPreview`, before `setupScheduling`):

```javascript
        setupCharCounter() {
            const { textInput, charCounter } = this.elements;
            if (!textInput || !charCounter) return;

            const MAX = 2000;
            const WARN = 1700;

            const update = () => {
                const len = textInput.value.length;
                charCounter.textContent = `${len} / ${MAX}`;
                charCounter.classList.toggle('is-warning', len >= WARN && len < MAX);
                charCounter.classList.toggle('is-error', len >= MAX);
            };

            // Initialise with current value (edit mode may pre-fill text)
            update();
            textInput.addEventListener('input', update);
        },
```

And call it from `init()`:

```javascript
        init() {
            this.setupTextPreview();
            this.setupCharCounter();
            this.setupScheduling();
            this.setupTags();
            this.setupValidation();
        },
```

- [ ] **Step 5: Run pre-commit and unit tests**

```bash
pre-commit run --all-files
pre-commit run --all-files
just test
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add suchar_overflow/static/css/pages/suchar_form.css \
        suchar_overflow/templates/suchary/suchar_form.html \
        suchar_overflow/static/js/pages/suchar_form.js
git commit -m "feat: add live character counter to joke text field"
```

---

## Task 7: Submit loading state

Disables the submit button and shows a CSS spinner while the form POST is in-flight. On re-render (form errors), `DOMContentLoaded` fires fresh and the button resets automatically.

**Files:**
- Modify: `suchar_overflow/static/css/pages/suchar_form.css`
- Modify: `suchar_overflow/static/js/pages/suchar_form.js`

- [ ] **Step 1: Add CSS for `.btn.is-loading` to `suchar_form.css`**

Append to `suchar_overflow/static/css/pages/suchar_form.css`:

```css
/* Submit button loading state */
.btn.is-loading {
    position: relative;
    pointer-events: none;
}

.btn.is-loading > * {
    visibility: hidden;
}

.btn.is-loading::after {
    content: '';
    position: absolute;
    width: 1rem;
    height: 1rem;
    top: 50%;
    left: 50%;
    margin-top: -0.5rem;
    margin-left: -0.5rem;
    border: 2px solid rgba(255, 255, 255, 0.4);
    border-top-color: white;
    border-radius: 50%;
    animation: btn-spin 0.6s linear infinite;
}

@keyframes btn-spin {
    to { transform: rotate(360deg); }
}
```

- [ ] **Step 2: Add `submitBtn` to the `elements` object in `suchar_form.js`**

In the `elements` object, add:

```javascript
            submitBtn: document.querySelector('button[type="submit"]'),
```

- [ ] **Step 3: Update `setupValidation()` in `suchar_form.js` to add loading state on valid submit**

Find `setupValidation()` (lines ~197–229). Replace the form submit listener with one that also triggers loading state. The full updated method:

```javascript
        setupValidation() {
            const { form, dateError, scheduleCheck, publishedAtInput, submitBtn } = this.elements;
            if (!form) return;

            form.addEventListener('submit', (e) => {
                if (scheduleCheck && scheduleCheck.checked && publishedAtInput.value) {
                    const inputDate = new Date(publishedAtInput.value);
                    const now = new Date();

                    if (inputDate <= now) {
                        e.preventDefault();
                        if (dateError) {
                            dateError.classList.remove('d-none');
                            dateError.classList.add('d-block');
                            dateError.textContent = "Data publikacji nie może być w przeszłości.";
                        }
                        publishedAtInput.classList.add('is-invalid');
                        return;
                    }
                }

                // Form is valid — show loading state
                if (submitBtn) {
                    submitBtn.classList.add('is-loading');
                    submitBtn.disabled = true;
                }
            });

            if (publishedAtInput) {
                publishedAtInput.addEventListener('input', () => {
                    if (dateError) {
                        dateError.classList.add('d-none');
                        dateError.classList.remove('d-block');
                    }
                    publishedAtInput.classList.remove('is-invalid');
                });
            }
        }
```

- [ ] **Step 4: Run pre-commit and unit tests**

```bash
pre-commit run --all-files
pre-commit run --all-files
just test
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add suchar_overflow/static/css/pages/suchar_form.css \
        suchar_overflow/static/js/pages/suchar_form.js
git commit -m "feat: disable submit button and show spinner while form is submitting"
```

---

## Final verification

- [ ] Run the full test suite one last time:

```bash
just test
```

Expected: all pass with no failures or warnings.
