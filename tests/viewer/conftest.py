from __future__ import annotations

import ast
import os
import sysconfig
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from types import ModuleType

    from qtpy.QtWidgets import QApplication

    from mne_lsl.viewer.theme import ThemeController
    from mne_lsl.viewer.widgets import EditableReadout

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
    # Nested deliberately: this conftest's body runs even when the gate above excludes
    # every test, and importing 'mne_lsl.viewer' raises without a Qt binding. Hoisting
    # this would fail the whole suite at collection on a binding-less machine.
    from mne_lsl.viewer._bootstrap import ensure_application

    application = ensure_application("mne-lsl viewer (tests)")
    yield application
    application.processEvents()


@pytest.fixture
def controller(app: QApplication) -> Generator[ThemeController, None, None]:
    """Yield the module-singleton ThemeController, restoring its state afterwards.

    The name refers to the *theme* controller, not to the 'controller/' subpackage.

    The singleton is instantiated at import time and 'pytest-randomly' shuffles the test
    order, thus any test which installs it or flips its mode must put it back. Only the
    3 privates below are restored, deliberately not the application palette / style
    sheet / pyqtgraph configuration: no test may assert a *default* application look,
    which would be order-dependent by construction. '_following' is not reset either, as
    the connection genuinely persists for the process and resetting it would let the
    next 'install' add a duplicate connection.
    """
    # Nested for the same reason as in 'app': this conftest is imported even on a host
    # with no Qt binding, where 'mne_lsl.viewer' cannot be imported at all.
    from mne_lsl.viewer.theme import theme_controller

    # 'app' is requested, not used: an application must exist before anything is themed.
    state = (theme_controller._app, theme_controller._setting, theme_controller._mode)
    yield theme_controller
    (
        theme_controller._app,
        theme_controller._setting,
        theme_controller._mode,
    ) = state


@pytest.fixture
def module_scan() -> Callable[[ModuleType], tuple[set[str], set[str]]]:
    """Return a factory parsing a module's source into its imports and identifiers.

    The import rules of a viewer subpackage cannot be checked through 'sys.modules':
    importing 'mne_lsl.viewer.backend._config' necessarily imports
    'mne_lsl.viewer.__init__', which imports qtpy, and 'mne_lsl.__init__', which imports
    'mne_lsl.lsl'. The rule is a source-level one, thus it is checked statically, on the
    module's own source only.

    Identifiers come from the syntax tree and not from a text search, so that a
    docstring mentioning a forbidden name -- documentation, not a dependency -- does not
    trip the check.

    An 'ImportFrom' is recorded as the dotted path of every name it binds, not as its
    module alone, which is what catches 'from ... import lsl': its 'node.module' is
    'None', so the module path of that form carries no segment to check at all. The
    leading dots are stripped, so that '...lsl' and 'mne_lsl.lsl' are both caught by the
    same segment check. Attribute access is what makes the 'identifiers' set worth
    asserting on as well: 'import mne_lsl' followed by 'mne_lsl.lsl.resolve_streams()'
    imports nothing forbidden and reaches the forbidden module anyway.
    """

    def _scan(module: ModuleType) -> tuple[set[str], set[str]]:
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imports: set[str] = set()
        identifiers: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
                identifiers.update(alias.name.split(".")[-1] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = (node.module or "").lstrip(".")
                imports.update(
                    f"{prefix}.{alias.name}" if prefix else alias.name
                    for alias in node.names
                )
                identifiers.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
        return imports, identifiers

    return _scan


@pytest.fixture
def finish_edit() -> Callable[[EditableReadout, str], None]:
    """Return a helper typing a value in a read-out editor and committing it.

    'EditableReadout' lives in 'widgets/' and is consumed by the display control bar,
    thus the helper for driving one belongs here rather than in either subdirectory.
    """

    def _finish(readout: EditableReadout, text: str) -> None:
        """Open the editor, type ``text`` and commit it, as the Enter key does."""
        readout.begin_edit()
        readout._edit.setText(text)
        readout._edit.editingFinished.emit()

    return _finish
