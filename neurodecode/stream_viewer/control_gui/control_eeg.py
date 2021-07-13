import math
from pathlib import Path
from configparser import RawConfigParser

from PyQt5 import QtCore
from PyQt5.QtWidgets import QHeaderView, QTableWidgetItem

from ._control import _ControlGUI
from ._ui_control import UI_MainWindow


class ControlGUI_EEG(_ControlGUI):
    """
    Controller GUI for EEG LSL Stream.

    Parameters
    ----------
    scope : stream_viewer.scope._scope._Scope
        Scope connected to a stream receiver acquiring the data and applying
        filtering. The scope has a buffer of _scope._BUFFER_DURATION.
    backend : str
        One of the supported backend's name. Supported 'vispy', 'pyqt5'.
    """

    def __init__(self, scope, backend):
        super().__init__(scope, backend)
        config_file = 'settings_scope_eeg.ini'

        self._load_configuration(config_file)
        self._load_gui()
        self._init_backend(backend)
        self._connect_signals_to_slots()
        self._set_configuration(config_file)

        self._backend.start_timer()

    def _load_gui(self):
        """
        Loads the UI created with QtCreator.
        """
        self._ui = UI_MainWindow(self)

        for yRange in self._yRanges:
            self._ui.comboBox_signal_yRange.addItem(str(yRange))

        # Set table channels row/col
        self._nb_table_columns = 8 if self._scope.nb_channels > 64 else 4
        self._nb_table_rows = math.ceil(
            self._scope.nb_channels / self._nb_table_columns)
        self._ui.table_channels.setRowCount(self._nb_table_rows)
        self._ui.table_channels.setColumnCount(self._nb_table_columns)

        # Set table channels elements
        for idx in range(self._scope.nb_channels):
            row = idx // self._nb_table_columns
            col = idx % self._nb_table_columns
            self._ui.table_channels.setItem(
                row, col, QTableWidgetItem(idx))
            self._ui.table_channels.item(row, col).setTextAlignment(
                QtCore.Qt.AlignCenter)
            self._ui.table_channels.item(row, col).setText(
                self._scope.channels_labels[idx])

        # Table channels header
        self._ui.table_channels.verticalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self._ui.table_channels.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)

        # Set position on the screen
        self.setGeometry(100, 100,
                         self.geometry().width(),
                         self.geometry().height())
        self.setFixedSize(self.geometry().width(),
                          self.geometry().height())
        self.show()  # Display

    def _load_configuration(self, file):
        """
        Load default configuration for the ranges.
        """
        path2settings_folder = Path(__file__).parent / 'settings'
        scope_settings = RawConfigParser(
            allow_no_value=True, inline_comment_prefixes=('#', ';'))
        scope_settings.read(str(path2settings_folder/file))

        # yRange (amplitude)
        self._yRanges = {'1uV': 1, '10uV': 10, '25uV': 25,
                         '50uV': 50, '100uV': 100, '250uV': 250,
                         '500uV': 500, '1mV': 1000, '2.5mV': 2500,
                         '10mV': 10000}
        try:
            self._yRange = float(scope_settings.get("plot", "yRange"))
            if not self._yRange in self._yRanges.values:
                raise ValueError
        except Exception:  # Default to 25 uV
            self._yRange = 25.

        # xRange (time)
        try:
            self._xRange = int(scope_settings.get("plot", "xRange"))
        except Exception:  # Default to 10s
            self._xRange = 10

    def _set_configuration(self, file):
        """
        Load and set a default configuration for the GUI.
        """
        path2settings_folder = Path(__file__).parent / 'settings'
        scope_settings = RawConfigParser(
            allow_no_value=True, inline_comment_prefixes=('#', ';'))
        scope_settings.read(str(path2settings_folder/file))

        # yRange
        init_idx = list(self._yRanges.values()).index(self._yRange)
        self._ui.comboBox_signal_yRange.setCurrentIndex(init_idx)

        # xRange
        try:
            self._ui.spinBox_signal_xRange.setValue(self._xRange)
        except:  # 10s by default
            self._ui.spinBox_signal_xRange.setValue(10)

        # CAR
        try:
            self._ui.checkBox_car.setChecked(bool(
                scope_settings.get("filtering", "apply_car_filter")))
        except Exception:
            self._ui.checkBox_car.setChecked(False)

        # BP Filters
        self._ui.checkBox_bandpass.setChecked(True)
        self._ui.checkBox_bandpass.setEnabled(False)
        try:
            self._ui.doubleSpinBox_bandpass_low.setValue(float(
                scope_settings.get(
                    "filtering", "bandpass_cutoff_frequency").split(' ')[0]))
            self._ui.doubleSpinBox_bandpass_high.setValue(float(
                scope_settings.get(
                    "filtering", "bandpass_cutoff_frequency").split(' ')[1]))
        except Exception:
            # Default to [1, 40] Hz.
            self._ui.doubleSpinBox_bandpass_low.setValue(1.)
            self._ui.doubleSpinBox_bandpass_high.setValue(40.)

        self._ui.doubleSpinBox_bandpass_high.setMinimum(
            self._ui.doubleSpinBox_bandpass_low.value()+1)
        self._ui.doubleSpinBox_bandpass_low.setMaximum(
            self._ui.doubleSpinBox_bandpass_high.value()-1)
        self._scope.init_bandpass_filter(
            low=self._ui.doubleSpinBox_bandpass_low.value(),
            high=self._ui.doubleSpinBox_bandpass_high.value())

        # Trigger events
        try:
            self._ui.checkBox_show_LPT_trigger_events.setChecked(
                bool(scope_settings.get("plot", "show_LPT_events")))
        except Exception:
            self._ui.checkBox_show_LPT_trigger_events.setChecked(False)

        # Table channels
        for idx in range(self._scope.nb_channels):
            row = idx // self._nb_table_columns
            col = idx % self._nb_table_columns
            self._ui.table_channels.item(row, col).setSelected(True)

        # Status bar
        self._ui.statusBar.showMessage("[Not recording]")

    def _init_backend(self, backend):
        """
        Initialize the backend.
        """
        backend = _ControlGUI._check_backend(backend)
        geometry = (self.geometry().x()+self.width(), self.geometry().y(),
                    self.width()*2, self.height())
        self._backend = backend(
            self._scope, geometry, self._xRange, self._yRange)

    # --------------------------------------------------------------------
    def _connect_signals_to_slots(self):
        """
        Event handler. Connect QT signals to slots.
        """
        super()._connect_signals_to_slots()
        # Scales
        self._ui.comboBox_signal_yRange.activated.connect(
            self.onActivated_comboBox_signal_yRange)
        self._ui.spinBox_signal_xRange.valueChanged.connect(
            self.onValueChanged_spinBox_signal_xRange)

        # CAR / Filters
        self._ui.checkBox_car.stateChanged.connect(
            self.onClicked_checkBox_car)
        self._ui.checkBox_bandpass.stateChanged.connect(
            self.onClicked_checkBox_bandpass)
        self._ui.doubleSpinBox_bandpass_low.valueChanged.connect(
            self.onValueChanged_doubleSpinBox_bandpass_low)
        self._ui.doubleSpinBox_bandpass_high.valueChanged.connect(
            self.onValueChanged_doubleSpinBox_bandpass_high)

        # Trigger events
        self._ui.checkBox_show_LPT_trigger_events.stateChanged.connect(
            self.onClicked_checkBox_show_LPT_trigger_events)

        # Channel table
        self._ui.table_channels.itemSelectionChanged.connect(
            self.onSelectionChanged_table_channels)

    @QtCore.pyqtSlot()
    def onActivated_comboBox_signal_yRange(self):
        self._yRange = float(list(self._yRanges.values())[
            self._ui.comboBox_signal_yRange.currentIndex()])
        self._backend.yRange = self._yRange

    @QtCore.pyqtSlot()
    def onValueChanged_spinBox_signal_xRange(self):
        self._xRange = int(self._ui.spinBox_signal_xRange.value())
        self._backend.xRange = self._xRange

    @QtCore.pyqtSlot()
    def onClicked_checkBox_car(self):
        self._scope.apply_car = self._ui.checkBox_car.isChecked()

    @QtCore.pyqtSlot()
    def onClicked_checkBox_bandpass(self):
        self._scope.apply_bandpass = self._ui.checkBox_bandpass.isChecked()

    @QtCore.pyqtSlot()
    def onValueChanged_doubleSpinBox_bandpass_low(self):
        self._ui.doubleSpinBox_bandpass_high.setMinimum(
            self._ui.doubleSpinBox_bandpass_low.value()+1)
        self._scope.init_bandpass_filter(
            low=self._ui.doubleSpinBox_bandpass_low.value(),
            high=self._ui.doubleSpinBox_bandpass_high.value())

    @QtCore.pyqtSlot()
    def onValueChanged_doubleSpinBox_bandpass_high(self):
        self._ui.doubleSpinBox_bandpass_low.setMaximum(
            self._ui.doubleSpinBox_bandpass_high.value()-1)
        self._scope.init_bandpass_filter(
            low=self._ui.doubleSpinBox_bandpass_low.value(),
            high=self._ui.doubleSpinBox_bandpass_high.value())

    @QtCore.pyqtSlot()
    def onClicked_checkBox_show_LPT_trigger_events(self):
        self._backend.show_LPT_trigger_events = bool(
            self._ui.checkBox_show_LPT_trigger_events.isChecked())

    @QtCore.pyqtSlot()
    def onSelectionChanged_table_channels(self):
        selected = self._ui.table_channels.selectedItems()
        self._scope.selected_channels = [
            item.row()*self._nb_table_columns + item.column()
            for item in selected]
        self._backend.selected_channels = self._scope.selected_channels

    def closeEvent(self, event):
        """
        Event called when closing the _ScopeControllerUI window.
        """
        if self._ui.pushButton_stop_recording.isEnabled():
            self.onClicked_pushButton_stop_recording()
        self._backend.close()
        super().closeEvent(event)

    # --------------------------------------------------------------------
    @property
    def backend(self):
        """
        Display backend.
        """
        return self._backend

    @property
    def ui(self):
        """
        Control UI.
        """
        return self._ui

    @property
    def xRange(self):
        """
        Selected X range (time) [seconds].
        """
        return self._xRange

    @property
    def yRange(self):
        """
        Selected Y range (amplitude) [uV].
        """
        return self._yRange