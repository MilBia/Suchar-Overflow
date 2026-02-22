# Project Coding Guidelines & Rules

This document outlines the mandatory standards and workflows for the Suchar Overflow project.

## 1. Execution Environment (**CRITICAL**)

>**Strict Rule**: Never run commands directly on the host system unless verifying the environment itself.

*   **Application / Python**: MUST run inside the Docker container.
    ```bash
    docker compose -f docker-compose.local.yml run --rm django <command>
    ```
*   **Tooling (Pre-commit)**: MUST run via the local virtual environment wrapper.
    ```bash
    .venv/bin/pre-commit run --all-files
    ```

## 2. Workflow & QA

### Pre-Commit
Before requesting a commit, **ALWAYS** run the pre-commit checks:
```bash
.venv/bin/pre-commit run --all-files
```
*   **Auto-fixes**: Re-run if Ruff/isort fixes files.
*   **Manual Fixes**:
    *   **Inline Styles**: Forbidden (`H021`). Use Bootstrap utility classes (`d-none`, `bg-primary`, etc.).
    *   **Line Length**: Max 88 chars. Split long comments/lines.
    *   **Imports**: No local imports (`PLC0415`). Move to top-level.

### Testing
Tests must be run in Docker to match CI:
```bash
docker compose -f docker-compose.local.yml run --rm django pytest
```

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
