# Project Coding Guidelines & Rules

This document outlines `.agent/`-specific guidance for Suchar Overflow. `CLAUDE.md`
at the repo root is the source of truth for commands, workflow steps, and code style
rules (execution environment, testing, pre-commit, dependency management, ruff rules,
PR conventions) — read it first. This file adds only what CLAUDE.md doesn't already
cover.

## 1. Execution Environment (**CRITICAL**)

See CLAUDE.md's "Running commands" section: application/tests run in the Docker
`django` service, pre-commit runs via the local `.venv` (see "Running pre-commit").

## 2. Workflow & QA

Before requesting a commit, follow CLAUDE.md's "Workflow — mandatory steps after
every task" section in full (`pre-commit run --all-files` twice, `just test`, and the
migration check when models changed).

### Manual fixes agents commonly need to apply
*   **Inline Styles**: Forbidden (`H021`). Use CSS custom properties and the
    project's component classes — this project does **not** use Bootstrap.
*   **Line Length / local imports**: see CLAUDE.md's ruff rules table (`E501`,
    `PLC0415`).

## 3. Frontend Architecture

### CSS
*   **BEM-like Naming**: `.component__element--modifier`.
*   **No Inline Styles**.
*   **No `!important`**. Refactor specificity instead.
*   **Variables**:
    *   Use global CSS variables (`--color-primary`, `--bg-surface`).
    *   Ensure variables work in both **Light** and **Dark** modes (fallback values).

### JavaScript
*   **Structure**: Object-oriented components initialized on `DOMContentLoaded`.
*   **Visibility**: Toggle CSS classes (`.d-none`, `.show`), do not use `style.display`.
*   **Debug**: Remove `console.log` before commit.

### HTML
*   **Assets**: No manual versioning (`?v=1`).
*   **Dropdowns**: Use the standard structure:
    ```html
    <div class="custom-dropdown">
        <div class="dropdown-trigger">...</div>
        <div class="dropdown-menu">
            <div class="dropdown-item">...</div>
        </div>
    </div>
    ```

## 4. Backend (Django/Python)

### Code Style
*   **Type Hints**: Use `str | None` instead of `Optional[str]`.
*   **Imports**: Sorted alphabetically, top-level only.

### Forms
*   **Hidden Inputs**: Must be `disabled` when hidden to prevent validation blocking.

### Migrations
*   **File Permissions**: When adding an empty migration or generating a new one inside Docker (`makemigrations`), the created files often inherit `root` ownership.
    *   **Action Required**: Always **remind the user** to fix the file permissions (e.g., using `sudo chown -R $USER:$USER .` or changing the file owner to their user account) right after the migration file is generated.

## 5. Translations (i18n)

### Frontend & Views
*   **Mark for Translation**: Always mark any user-visible strings for translation.
    *   **Templates**: Use `{% trans "Text" %}` or `{% blocktrans %}`.
    *   **Python (Views/Forms)**: Use `gettext_lazy` imported as `_`.

### After Implementing a Feature
*   Run the `/update_translations` workflow or manually update translation files using `makemessages` and `compilemessages`.
    *   `docker compose -f docker-compose.local.yml run --rm django python manage.py makemessages -l pl -l en`
    *   `docker compose -f docker-compose.local.yml run --rm django python manage.py compilemessages`
