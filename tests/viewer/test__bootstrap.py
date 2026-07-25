from __future__ import annotations

import importlib
import os
import pkgutil
import subprocess
import sys
import sysconfig

import pyqtgraph as pg
import pytest
import qtpy
from qtpy.QtWidgets import QApplication

import mne_lsl.viewer
from mne_lsl.viewer._bootstrap import (
    _ensure_not_free_threaded,
    _ensure_qt_binding,
    assert_binding_coherence,
    ensure_application,
    import_ads,
)

# Safe at module level: 'tests/viewer/conftest.py' keeps this whole package out of
# collection (via 'collect_ignore_glob') before any module here is ever imported, on a
# free-threaded build or without a Qt binding -- see the comment there.


def _module_names() -> list[str]:
    """Return the name of every module of 'mne_lsl.viewer', subpackages included."""
    return [
        name
        for _, name, _ in pkgutil.walk_packages(
            mne_lsl.viewer.__path__, prefix="mne_lsl.viewer."
        )
    ]


def test_module_names() -> None:
    """Test that the module walk finds the subpackages."""
    names = _module_names()
    assert "mne_lsl.viewer._bootstrap" in names
    for subpackage in ("backend", "controller", "display", "theme", "widgets"):
        assert f"mne_lsl.viewer.{subpackage}" in names, subpackage


@pytest.mark.parametrize("name", _module_names())
def test_import_module(name: str) -> None:
    """Test that every module imports without side effect.

    'tools/stubgen.py' imports every module to generate the stub files, thus a module
    which builds a QApplication, a widget or applies the theme on import would break the
    stub generation.
    """
    importlib.import_module(name)


def test_ensure_not_free_threaded() -> None:
    """Test the free-threaded Python guard."""
    # a free-threaded build never reaches this point, the package is not collected
    assert not sysconfig.get_config_var("Py_GIL_DISABLED")
    _ensure_not_free_threaded()  # no-op on a build with the GIL


def test_ensure_qt_binding() -> None:
    """Test that the Qt binding guard reports the binding resolved by qtpy."""
    assert _ensure_qt_binding() == qtpy.API_NAME
    assert qtpy.API_NAME in ("PyQt6", "PySide6")


def test_pyqtgraph_binding() -> None:
    """Test that qtpy and pyqtgraph agree on the Qt binding."""
    assert os.environ["PYQTGRAPH_QT_LIB"] == qtpy.API_NAME
    assert_binding_coherence()


def test_assert_binding_coherence_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a qtpy/pyqtgraph binding mismatch raises."""
    monkeypatch.setattr(pg.Qt, "QT_LIB", "PyQt5")
    with pytest.raises(RuntimeError, match="Qt binding mismatch"):
        assert_binding_coherence()


def test_ensure_application(app: QApplication) -> None:
    """Test that the application is created once and reused."""
    assert ensure_application() is app
    assert QApplication.instance() is app


def test_import_ads() -> None:
    """Test that the Qt-ADS shim resolves the binding-specific module."""
    ads = import_ads()
    assert ads.__name__ in ("PyQt6Ads", "PySide6QtAds")
    assert hasattr(ads, "CDockManager")
    assert hasattr(ads, "CDockWidget")


def test_viewer_public_api() -> None:
    """Test that only 'Viewer' is public and that it is exported."""
    assert mne_lsl.viewer.__all__ == ("Viewer",)
    assert isinstance(mne_lsl.viewer.Viewer, type)


def test_import_mne_lsl_is_qt_free() -> None:
    """Test that 'import mne_lsl' does not import Qt, in a fresh interpreter."""
    code = (
        "import sys; import mne_lsl; "
        "assert not {'qtpy', 'pyqtgraph', 'PyQt6', 'PySide6'} & set(sys.modules), "
        "sorted(set(sys.modules))"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
