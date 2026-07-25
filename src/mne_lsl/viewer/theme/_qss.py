"""Thin, palette-role-based style sheets and the Qt-ADS icon slots.

Every color goes through the QSS ``palette(<role>)`` function instead of a hardcoded
hex value, so one sheet serves both modes and survives a theme flip.
"""

from __future__ import annotations

# TODO: port the reviewed control skin from 'brief/scripts/palette/palette.py' (_QSS):
# toolbars, tool/push buttons, text fields, combo boxes, tabs, item views, headers,
# scrollbars, group boxes and tooltips. 4 px radius, 1 px borders, padding on a small
# grid; checkbox/radio indicators are left to Fusion.
_QSS = ""

# TODO: port the reviewed Qt-ADS chrome skin from 'brief/scripts/shell/main.py'
# (_ADS_QSS): dock container/area background, splitter handles, title bar, flat tabs
# with the accent underline on the focused area, the per-tab close button and the
# title-bar buttons. It replaces Qt-ADS's own bundled style sheet.
_ADS_QSS = ""

# Qt-ADS title-bar glyphs, keyed by the name of the 'ads.eIcon' slot they replace, so
# this module stays free of the docking dependency (the consumer resolves the slot).
_ADS_ICONS: dict[str, str] = {
    "TabCloseIcon": "mdi6.close",
    "DockAreaCloseIcon": "mdi6.close",
    "DockAreaMenuIcon": "mdi6.chevron-down",
    "DockAreaUndockIcon": "mdi6.dock-window",
}
