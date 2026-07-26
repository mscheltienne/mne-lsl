from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import numpy as np
import pyqtgraph as pg
import pytest
from qtpy.QtWidgets import QToolButton

from mne_lsl.lsl import StreamInfo, StreamOutlet
from mne_lsl.stream import StreamLSL
from mne_lsl.viewer.display import TraceDisplay

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from qtpy.QtWidgets import QApplication, QWidget

# Bound on the wait for a pushed chunk to reach the stream buffer. Generous, as it is
# only ever reached when the local link is broken; a local outlet delivers in ~10 ms.
_PUSH_DEADLINE = 10.0
# Acquisition period of the connected stream, in seconds. Short, so that a pushed chunk
# is picked up without the test having to wait a default 1 ms x n cycles.
_ACQUISITION_DELAY = 0.01


@pytest.fixture
def lsl_stream(
    request: pytest.FixtureRequest,
) -> Generator[Callable[..., tuple[StreamLSL, Callable[..., None]]]]:
    """Yield a factory creating a connected stream fed by a real outlet.

    Rendering, the stim edge detection and the x-mapping all need actual samples, thus
    the silent outlet of 'tests/viewer/backend/' is no longer enough here -- but a
    'PlayerLSL', a subprocess and a testing dataset still are not needed: an outlet and
    'push_chunk' cover every assertion and are far less flaky.

    The factory returns the connected stream and a ``push`` callable. Teardown
    disconnects the stream and destroys the outlet, in the fixture rather than in the
    test bodies, so that a failing assertion still tears both down.
    """
    created: list[tuple[StreamLSL, StreamOutlet]] = []

    def _start(
        n_channels: int = 8,
        sfreq: float = 100.0,
        n_stim: int = 1,
        units: str = "uv",
        bufsize: float = 2.0,
    ) -> tuple[StreamLSL, Callable[..., None]]:
        """Create one outlet, connect a stream to it and return ``(stream, push)``.

        The channel names are explicit and unique: MNE's 'create_info' warns on a dup
        names during 'connect()', and this suite turns warnings into errors. The last
        'n_stim' channels are stim channels.

        The LSL name is suffixed with the creation count, not only with the test name:
        a test asking the factory twice would otherwise publish two outlets under one
        name, and 'StreamLSL.connect()' resolves on the name and the type before the
        'source_id', so the second connection could land on the first outlet.

        'bufsize' carries the mne-lsl semantics: seconds for a regularly sampled stream,
        samples when 'sfreq' is 0, i.e. for the irregular stream the render loop has its
        own branch for.
        """
        name = f"mne-lsl-viewer-{request.node.name}-{len(created)}"
        source_id = str(uuid.uuid4())
        sinfo = StreamInfo(name, "eeg", n_channels, sfreq, "float32", source_id)
        n_data = n_channels - n_stim
        ch_names = [f"ch{k}" for k in range(n_data)]
        ch_names += [f"STI{k}" for k in range(n_stim)]
        sinfo.set_channel_names(ch_names)
        sinfo.set_channel_types(["eeg"] * n_data + ["stim"] * n_stim)
        sinfo.set_channel_units([units] * n_data + ["none"] * n_stim)
        outlet = StreamOutlet(sinfo)
        stream = StreamLSL(
            bufsize,
            name=name,
            stype="eeg",
            source_id=source_id,
        ).connect(acquisition_delay=_ACQUISITION_DELAY, timeout=10.0)
        created.append((stream, outlet))

        def _push(n_samples: int = 50, stim_at: int | None = None) -> None:
            """Push a synthesized block and block until it reached the buffer."""
            rng = np.random.default_rng(101)
            # an irregular stream declares 'sfreq == 0': the sample index is the time.
            times = np.arange(n_samples) / sfreq if sfreq else np.arange(n_samples)
            data = np.empty((n_samples, n_channels), dtype=np.float32)
            for k in range(n_data):
                data[:, k] = np.sin(
                    2 * np.pi * (5 + k) * times
                ) + 0.05 * rng.standard_normal(n_samples)
            data[:, n_data:] = 0.0
            if stim_at is not None:
                data[stim_at, n_data:] = 3.0
            outlet.push_chunk(data)
            deadline = time.monotonic() + _PUSH_DEADLINE
            while time.monotonic() < deadline:
                if stream.n_new_samples > 0:
                    return
                time.sleep(0.01)
            pytest.fail(f"The chunk pushed to {name} never reached the buffer.")

        return stream, _push

    yield _start
    for stream, outlet in reversed(created):
        if stream.connected:  # a test may have disconnected it on purpose
            stream.disconnect()
        outlet._del()
    created.clear()


@pytest.fixture
def default_stream(
    lsl_stream: Callable[..., tuple[StreamLSL, Callable[..., None]]],
) -> tuple[StreamLSL, Callable[..., None]]:
    """Return the default 8-channel stream and its push callable."""
    return lsl_stream()


@pytest.fixture
def stream(default_stream: tuple[StreamLSL, Callable[..., None]]) -> StreamLSL:
    """Return the default 8-channel stream, without any sample pushed yet."""
    return default_stream[0]


@pytest.fixture
def push(
    default_stream: tuple[StreamLSL, Callable[..., None]],
) -> Callable[..., None]:
    """Return the callable pushing a synthesized block onto the default stream."""
    return default_stream[1]


@pytest.fixture
def make_display(app: QApplication) -> Generator[Callable[[StreamLSL], TraceDisplay]]:
    """Yield a factory building trace displays, closed at teardown.

    Same shape as the 'lsl_stream' factory, and for the same reason: the tests needing a
    non-default stream built their display in the body, and a hand-rolled 'try/finally'
    per test is what this replaces.
    """
    created: list[TraceDisplay] = []

    def _make(stream: StreamLSL, width: int = 1000, height: int = 600) -> TraceDisplay:
        """Build one display over ``stream`` and register it for teardown."""
        widget = TraceDisplay(stream)
        widget.resize(width, height)
        created.append(widget)
        return widget

    yield _make
    for widget in reversed(created):
        widget.stop()
        widget.close()
        widget.deleteLater()
    app.processEvents()
    created.clear()


@pytest.fixture
def display(
    make_display: Callable[[StreamLSL], TraceDisplay], stream: StreamLSL
) -> TraceDisplay:
    """Return a trace display over the default stream, closed afterwards."""
    return make_display(stream)


@pytest.fixture
def pg_background() -> Generator[Callable[[str], None]]:
    """Yield a setter for pyqtgraph's background configuration, restored afterwards.

    The 'controller' fixture deliberately leaves the pyqtgraph configuration alone, as
    no test may assert a default application look; a test which pushes a color no theme
    ever sets therefore has to put the previous one back itself.
    """
    previous = pg.getConfigOption("background")
    yield lambda color: pg.setConfigOption("background", color)
    pg.setConfigOption("background", previous)


@pytest.fixture
def tool_button() -> Callable[[QWidget, str], QToolButton]:
    """Return a helper looking a tool button up by its tooltip.

    The bar identifies its steppers by tooltip alone -- there is no object name and no
    accessor -- thus both the control-bar tests and the display's icon tests need this
    lookup.
    """

    def _button(widget: QWidget, tip: str) -> QToolButton:
        """Return the tool button of ``widget`` whose tooltip is ``tip``."""
        for button in widget.findChildren(QToolButton):
            if button.toolTip() == tip:
                return button
        pytest.fail(f"No tool button with the tooltip {tip!r}.")

    return _button


@pytest.fixture
def shown_display(app: QApplication, display: TraceDisplay) -> Generator[TraceDisplay]:
    """Yield a displayed trace display, for the assertions which need real painting.

    'AxisItem.drawPicture' only runs when the item is actually painted, thus a test
    covering it has to show the widget and let the scene render.
    """
    display.show()
    app.processEvents()
    yield display
    display.hide()
