"""The webpack toolchain and its Django side (#466).

- ``base.html`` renders the ``project`` bundle's tag (``FakeWebpackLoader`` under the test
  settings, the real loader and a stats file written here for the rest).
- A page that renders two entries gets the shared runtime chunk once: it is the guard for
  ``SKIP_COMMON_CHUNKS``, without which every module in a shared chunk would run twice.
- The Node image tag follows ``.nvmrc`` in all three places that name it.
- The dev server never uses an ``eval*`` devtool (the CSP has no ``'unsafe-eval'``).
- Build output stays out of git and out of the Django image's build context, and
  ``package.json`` stays in it (the node image and ``client-builder`` run ``npm ci`` from it).

Only files are read for the Docker parts; that the stack comes up is checked by hand.
"""

import json
import re
from pathlib import Path

import pytest
import webpack_loader.config
import yaml
from django.template import Context
from django.template import Template
from django.test import Client
from django.test import RequestFactory
from django.urls import reverse
from webpack_loader.utils import get_loader

_ROOT = Path(__file__).resolve().parent.parent
_NODE_FROM_RE = re.compile(r"^FROM\s+docker\.io/node:(\S+)", re.MULTILINE)


def _lines(path: str) -> list[str]:
    return (_ROOT / path).read_text(encoding="utf-8").splitlines()


@pytest.fixture
def real_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """The real ``WebpackLoader`` reading a stats file with two entries and one shared chunk."""
    assets = {
        name: {"name": name, "publicPath": f"/static/webpack_bundles/{name}"}
        for name in (
            "js/runtime.aaaaaaaaaaaa.js",
            "js/project.bbbbbbbbbbbb.js",
            "js/leaderboard.cccccccccccc.js",
            "css/project.dddddddddddd.css",
        )
    }
    stats = {
        "status": "done",
        "assets": assets,
        "chunks": {
            "project": ["js/runtime.aaaaaaaaaaaa.js", "js/project.bbbbbbbbbbbb.js", "css/project.dddddddddddd.css"],
            "leaderboard": ["js/runtime.aaaaaaaaaaaa.js", "js/leaderboard.cccccccccccc.js"],
        },
    }
    stats_file = tmp_path / "webpack-stats.json"
    stats_file.write_text(json.dumps(stats), encoding="utf-8")
    config = webpack_loader.config.user_config["DEFAULT"]
    monkeypatch.setitem(config, "LOADER_CLASS", "webpack_loader.loaders.WebpackLoader")
    monkeypatch.setitem(config, "STATS_FILE", str(stats_file))
    monkeypatch.setitem(config, "CACHE", False)  # noqa: FBT003
    get_loader.cache_clear()
    yield
    get_loader.cache_clear()


def _render(source: str) -> str:
    request = RequestFactory().get("/")
    return Template("{% load webpack_loader %}" + source).render(Context({"request": request}))


@pytest.mark.django_db
def test_base_template_renders_the_project_bundle_tag(client: Client) -> None:
    html = client.get(reverse("home")).content.decode()
    assert re.search(r"<script src=\"[^\"]*webpack_bundles/[^\"]+\.js\" defer></script>", html)


def test_render_bundle_adds_defer_and_the_css_link(real_loader: None) -> None:  # noqa: ARG001
    scripts = _render("{% render_bundle 'project' 'js' attrs='defer' %}")
    assert 'src="/static/webpack_bundles/js/project.bbbbbbbbbbbb.js" defer' in scripts
    styles = _render("{% render_bundle 'project' 'css' %}")
    assert 'href="/static/webpack_bundles/css/project.dddddddddddd.css" rel="stylesheet"' in styles


def test_second_entry_on_a_page_does_not_repeat_the_shared_runtime(real_loader: None) -> None:  # noqa: ARG001
    html = _render(
        "{% render_bundle 'project' 'js' attrs='defer' %}{% render_bundle 'leaderboard' 'js' attrs='defer' %}",
    )
    assert html.count("runtime.aaaaaaaaaaaa.js") == 1
    assert html.count("leaderboard.cccccccccccc.js") == 1
    assert html.index("runtime.") < html.index("project.")


def test_source_maps_are_not_rendered(real_loader: None) -> None:  # noqa: ARG001
    assert ".map" not in _render("{% render_bundle 'project' attrs='defer' %}")


def test_node_image_tag_follows_nvmrc() -> None:
    major = (_ROOT / ".nvmrc").read_text(encoding="utf-8").strip().removeprefix("v").split(".")[0]
    for dockerfile in ("compose/local/node/Dockerfile", "compose/production/django/Dockerfile"):
        tags = _NODE_FROM_RE.findall((_ROOT / dockerfile).read_text(encoding="utf-8"))
        assert tags, f"{dockerfile} has no docker.io/node stage"
        for tag in tags:
            assert tag.startswith(f"{major}-"), f"{dockerfile}: node:{tag} does not follow .nvmrc ({major})"
    engines = json.loads((_ROOT / "package.json").read_text(encoding="utf-8"))["engines"]["node"]
    assert engines == f">={major}"


def test_dev_server_does_not_use_an_eval_devtool() -> None:
    dev = (_ROOT / "webpack/dev.config.js").read_text(encoding="utf-8")
    match = re.search(r"devtool:\s*'([^']+)'", dev)
    assert match, "dev.config.js must set devtool explicitly (webpack's development default is eval)"
    assert not match.group(1).startswith("eval")


def test_node_service_is_wired_into_local_compose() -> None:
    compose = yaml.safe_load((_ROOT / "docker-compose.local.yml").read_text(encoding="utf-8"))
    node = compose["services"]["node"]
    assert node["build"]["dockerfile"] == "./compose/local/node/Dockerfile"
    assert "3000:3000" in node["ports"]
    assert "/app/node_modules" in node["volumes"]
    assert "healthcheck" in node


def test_build_output_stays_out_of_git_and_the_image_context() -> None:
    gitignore = _lines(".gitignore")
    dockerignore = _lines(".dockerignore")
    for pattern in ("webpack-stats.json", "suchar_overflow/static/webpack_bundles/"):
        assert pattern in gitignore
        assert pattern in dockerignore
    assert "node_modules/" in dockerignore
    # The node image and the client-builder stage run `npm ci` from these.
    assert "package.json" not in dockerignore
    assert "package-lock.json" not in dockerignore


def test_production_image_builds_the_bundles_in_a_client_builder_stage() -> None:
    dockerfile = (_ROOT / "compose/production/django/Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^FROM docker\.io/node:\S+ AS client-builder$", dockerfile, re.MULTILINE)
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "COPY --from=client-builder /app/webpack-stats.json" in dockerfile
    # NODE_ENV=production before `npm ci` would skip webpack itself (a devDependency).
    assert "NODE_ENV" not in dockerfile.split("AS client-builder")[1].split("FROM docker.io/python")[0].replace(
        "NODE_ENV stays",
        "",
    )
