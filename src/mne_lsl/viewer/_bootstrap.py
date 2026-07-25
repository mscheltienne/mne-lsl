"""Runtime guards, application creation and the Qt-ADS binding shim.

Qt is imported lazily inside the functions: :mod:`mne_lsl.viewer` imports this module
before it knows whether a Qt binding is installed, so importing it must never import
:mod:`qtpy`.
"""

from __future__ import annotations

import sys
import sysconfig
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

    from qtpy.QtWidgets import QApplication

_INSTALL_HINT = (
    "Install one of the complete Qt stacks: 'pip install mne-lsl[pyqt6]' or "
    "'pip install mne-lsl[pyside6]'."
)

# Strong reference to the application created by 'ensure_application'. PyQt6/sip
# destroys the underlying C++ application together with its last Python reference, so a
# caller which discards the returned object would crash the next Qt object built
# ('Must construct a QApplication before a QWidget'). pyqtgraph.mkQApp keeps an
# equivalent module-global for this reason.
_app: QApplication | None = None


def _ensure_not_free_threaded() -> None:
    """Raise if the interpreter is a free-threaded (GIL-disabled) CPython build."""
    if not sysconfig.get_config_var("Py_GIL_DISABLED"):
        return
    gil = getattr(sys, "_is_gil_enabled", lambda: True)()
    raise RuntimeError(
        "'mne_lsl.viewer' requires a Python build with the GIL: Qt, pyqtgraph and "
        "their bindings are not free-threading safe. This interpreter is a "
        f"free-threaded build of Python {sys.version.split()[0]} (the GIL is currently "
        f"{'enabled' if gil else 'disabled'}). Run the viewer on a regular CPython "
        "build; the rest of mne-lsl supports free-threaded Python."
    )


def _ensure_qt_binding() -> str:
    """Import qtpy and return the name of the resolved Qt binding."""
    try:
        import qtpy
    except ImportError as error:  # includes qtpy.QtBindingsNotFoundError
        raise ImportError(
            "'mne_lsl.viewer' requires a Qt 6 binding, which is missing. "
            f"{_INSTALL_HINT}"
        ) from error
    return qtpy.API_NAME


def assert_binding_coherence() -> None:
    """Raise if qtpy and pyqtgraph resolved different Qt bindings."""
    import pyqtgraph as pg
    import qtpy

    if pg.Qt.QT_LIB != qtpy.API_NAME:
        raise RuntimeError(
            f"Qt binding mismatch: qtpy resolved {qtpy.API_NAME} while pyqtgraph "
            f"resolved {pg.Qt.QT_LIB}. Importing 'mne_lsl.viewer' sets "
            "'PYQTGRAPH_QT_LIB' from qtpy, thus this mismatch comes from an explicit "
            "'QT_API'/'PYQTGRAPH_QT_LIB' pair or from pyqtgraph being imported first."
        )


def ensure_application(name: str = "mne-lsl viewer") -> QApplication:
    """Return the running ``QApplication``, creating one if needed.

    Parameters
    ----------
    name : str
        Application name, set on the returned application.

    Returns
    -------
    app : QApplication
        The reused or newly created application instance.
    """
    from qtpy.QtWidgets import QApplication

    global _app
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(name)
    _app = app  # keep a strong reference alive, see the module-level comment
    return app


def install_exception_policy() -> None:
    """Install a consistent unhandled-exception policy across the Qt bindings."""
    # An unhandled exception raised inside a slot behaves differently per binding, and
    # neither default is acceptable: PyQt6 calls 'qFatal()' and aborts the process with
    # SIGABRT, while PySide6 either swallows it silently, when the slot is invoked
    # through the event loop, or re-raises it, when it is called synchronously. The same
    # bug is therefore a hard crash on one binding and an invisible no-op on the other.
    # This is the seam where the viewer installs one behaviour for both, e.g. log the
    # traceback, surface it in the error area and keep the event loop alive.
    # 'ensure_application' will call it once the policy is implemented.


def import_ads() -> ModuleType:
    """Return the Qt Advanced Docking System module matching the active binding.

    Qt-ADS ships one distribution per binding under a different module name
    (``PyQt6Ads`` for PyQt6, ``PySide6QtAds`` for PySide6). This function is the single
    place in the viewer where that difference is resolved; consumers do
    ``ads = import_ads()`` at module level.

    Always use the **scoped** enum form, e.g. ``ads.DockWidgetArea.TopDockWidgetArea``:
    the flat form used by the PySide6-QtAds examples, e.g. ``ads.TopDockWidgetArea``,
    does not exist in ``PyQt6Ads``, thus only the scoped form works under both bindings.

    Returns
    -------
    ads : module
        The Qt-ADS binding module.
    """
    import qtpy

    if qtpy.PYQT6:
        import PyQt6Ads as ads
    elif qtpy.PYSIDE6:
        import PySide6QtAds as ads
    else:
        raise RuntimeError(
            f"'mne_lsl.viewer' requires PyQt6 or PySide6, while qtpy resolved "
            f"{qtpy.API_NAME}. {_INSTALL_HINT}"
        )
    return ads
