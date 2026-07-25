from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from mne_lsl.viewer.theme import theme_controller as controller_singleton

if TYPE_CHECKING:
    from collections.abc import Generator

    from qtpy.QtWidgets import QApplication

    from mne_lsl.viewer.theme import ThemeController


@pytest.fixture
def controller(app: QApplication) -> Generator[ThemeController, None, None]:
    """Yield the module-singleton ThemeController, restoring its state afterwards.

    The singleton is instantiated at import time and 'pytest-randomly' shuffles the test
    order, thus any test which installs it or flips its mode must put it back. Only the
    3 privates below are restored, deliberately not the application palette / style
    sheet / pyqtgraph configuration: no test may assert a *default* application look,
    which would be order-dependent by construction. '_following' is not reset either, as
    the connection genuinely persists for the process and resetting it would let the
    next 'install' add a duplicate connection.
    """
    # 'app' is requested, not used: an application must exist before anything is themed.
    state = (
        controller_singleton._app,
        controller_singleton._setting,
        controller_singleton._mode,
    )
    yield controller_singleton
    (
        controller_singleton._app,
        controller_singleton._setting,
        controller_singleton._mode,
    ) = state


@pytest.fixture
def recorder(controller: ThemeController) -> Generator[list[str], None, None]:
    """Yield the list of modes emitted by 'theme_changed', disconnected afterwards."""
    received: list[str] = []

    def _record(mode: str) -> None:
        received.append(mode)

    controller.theme_changed.connect(_record)
    yield received
    controller.theme_changed.disconnect(_record)
