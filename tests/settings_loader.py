"""Import a throwaway copy of ``config/settings/base.py`` under a fake environment.

``base.py`` reads its environment at import time, so testing the env conventions
(#453) needs a fresh import per case. Reloading the live ``config.settings.base``
would rebind names other modules already imported from it, and ``read_env``
(``.envs/.secrets``) writes into ``os.environ``. Instead the file is copied into
``tmp_path/config/settings/`` — so its ``BASE_DIR`` is ``tmp_path`` and an
``.envs/.secrets`` there is the one it sees — and executed as an unrelated
module while ``environ.Env.ENVIRON`` is swapped for a plain dict. Neither the
live settings nor the process environment are touched.
"""

import importlib.util
import shutil
from pathlib import Path

# Real imports (not TYPE_CHECKING-guarded): kept plain to match every other test
# module; only referenced in annotations.
from types import ModuleType  # noqa: TC003

import environ
import pytest  # noqa: TC002

from config.settings import base

BASE_SETTINGS_FILE = Path(base.__file__)

# The minimum base.py needs to import at all.
MINIMAL_ENV = {
    "DATABASE_URL": "postgres://user:pass@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
}


def load_base_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    environment: dict[str, str],
    *,
    secrets: str | None = None,
) -> ModuleType:
    """Execute a copy of base.py with exactly ``environment`` as its env.

    ``secrets``, when given, is written to ``tmp_path/.envs/.secrets`` first.
    ``environment`` is copied, so the caller's dict is left as it was.
    """
    settings_dir = tmp_path / "config" / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    target = settings_dir / "base.py"
    shutil.copyfile(BASE_SETTINGS_FILE, target)
    if secrets is not None:
        envs_dir = tmp_path / ".envs"
        envs_dir.mkdir(exist_ok=True)
        (envs_dir / ".secrets").write_text(secrets)

    monkeypatch.setattr(environ.Env, "ENVIRON", dict(environment))
    spec = importlib.util.spec_from_file_location("_base_settings_under_test", target)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
