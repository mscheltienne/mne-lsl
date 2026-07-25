from __future__ import annotations

import os
import sysconfig
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from qtpy.QtWidgets import QApplication

# render offscreen unless the environment asks for something else, so the tests run on a
# headless machine without a display server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Gate the entire package: the viewer is not free-threading safe, and 'mne_lsl.viewer'
# raises on such a build, while a missing Qt binding makes every test unrunnable.
#
# 'collect_ignore_glob' is the right tool: pytest's own default 'pytest_ignore_collect'
# hook implementation (see '_pytest/main.py') is *driven by* this list, so a custom hook
# here would just reimplement it. Per that same source, a file matched by
# 'collect_ignore_glob' is skipped strictly before 'pytest_collect_file' -- the hook
# that imports the module -- ever runs. That ordering is what makes plain, module-level
# 'qtpy'/'pyqtgraph' imports in 'tests/viewer/test_*.py' safe: those modules are only
# ever imported once this conftest has already confirmed Qt is importable.
#
# 'pytest.importorskip("qtpy")' is not usable here, for two independent reasons. First,
# qtpy imports successfully and only then raises 'QtBindingsNotFoundError' (an
# 'ImportError' subclass, but not a 'ModuleNotFoundError') when no binding is installed;
# pytest's 'importorskip' defaults its 'exc_type' to 'ModuleNotFoundError' since 9.1, so
# it no longer catches that and re-raises instead of skipping (passing
# 'exc_type=ImportError' would catch it, but see the second reason). Second, and more
# fundamentally, 'importorskip' skips one test module/function by raising 'Skipped';
# calling it here, at conftest module level, would abort loading this conftest instead
# of quietly excluding the directory, which is what 'collect_ignore_glob' does instead.
collect_ignore_glob: list[str] = []
if sysconfig.get_config_var("Py_GIL_DISABLED"):
    collect_ignore_glob = ["*"]
else:
    try:
        import qtpy  # noqa: F401
    except ImportError:
        collect_ignore_glob = ["*"]


@pytest.fixture(scope="session")
def app() -> Generator[QApplication, None, None]:
    """Yield the session-wide offscreen QApplication."""
    from mne_lsl.viewer._bootstrap import ensure_application

    application = ensure_application("mne-lsl viewer (tests)")
    yield application
    application.processEvents()
