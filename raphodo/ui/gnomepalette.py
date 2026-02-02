#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later

from collections import defaultdict

from PyQt5.QtGui import (
    QColor,
    QPalette,
)

standard_blue = "#3584e4"
colors = (
    ("blue", standard_blue),
    ("teal", "#2190a4"),
    ("green", "#3a944a"),
    ("yellow", "#c88800"),
    ("orange", "#ed5b00"),
    ("red", "#e62d42"),
    ("pink", "#d56199"),
    ("purple", "#9141ac"),
    ("slate", "#6f8396"),
    ("adwaita", standard_blue),
    ("yaru", "#e95420"),
    ("yaru-dark", "#e95420"),
    ("yaru-bark", "#787859"),
    ("yaru-bark-dark", "#787859"),
    ("yaru-sage", "#657b69"),
    ("yaru-sage-dark", "#657b69"),
    ("yaru-olive", "#4b8501"),
    ("yaru-olive-dark", "#4b8501"),
    ("yaru-viridian", "#03875b"),
    ("yaru-viridian-dark", "#03875b"),
    ("yaru-prussiangreen", "#308280"),
    ("yaru-prussiangreen-dark", "#308280"),
    ("yaru-blue", "#0073e5"),
    ("yaru-blue-dark", "#0073e5"),
    ("yaru-purple", "#7764d8"),
    ("yaru-purple-dark", "#7764d8"),
    ("yaru-magenta", "#b34cb3"),
    ("yaru-magenta-dark", "#b34cb3"),
    ("yaru-red", "#da3450"),
    ("yaru-red-dark", "#da3450"),
)
GnomeAccentColor = defaultdict(lambda: standard_blue)
for k, v in colors:
    GnomeAccentColor[k] = v


def accentPalette(palette: QPalette | None = None, accent_color: str = "") -> QPalette:
    """
    Sets active and inactive highlights to match Gnome accent.

    :param palette: palette to modify. If empty, returns a new palette derived
      from the default.
    :param accent_color: accent color in English form, e.g. "blue", or "yaru-olive"
    """

    if palette is None:
        palette = QPalette()
    accent = QColor(GnomeAccentColor[accent_color])
    palette.setColor(QPalette.Active, QPalette.Highlight, accent)
    palette.setColor(QPalette.Inactive, QPalette.Highlight, accent)
    return palette


def darkPalette(accent_color: str = "") -> QPalette:
    """
    Applies KDE plasma dark palette, with accent from Gnome settings.

    :param accent_color: accent color in English form, e.g. "blue", or "yaru-olive"
    """

    palette = QPalette()
    palette.setColor(QPalette.Active, QPalette.Window, QColor("#202326"))
    palette.setColor(QPalette.Active, QPalette.WindowText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Active, QPalette.Base, QColor("#141618"))
    palette.setColor(QPalette.Active, QPalette.AlternateBase, QColor("#1d1f22"))
    palette.setColor(QPalette.Active, QPalette.ToolTipBase, QColor("#292c30"))
    palette.setColor(QPalette.Active, QPalette.ToolTipText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Active, QPalette.Text, QColor("#fcfcfc"))
    palette.setColor(QPalette.Active, QPalette.Button, QColor("#292c30"))
    palette.setColor(QPalette.Active, QPalette.ButtonText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Active, QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Active, QPalette.Highlight, QColor("#3daee9"))
    palette.setColor(QPalette.Active, QPalette.HighlightedText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Active, QPalette.Link, QColor("#1d99f3"))
    palette.setColor(QPalette.Active, QPalette.LinkVisited, QColor("#9b59b6"))
    palette.setColor(QPalette.Active, QPalette.Light, QColor("#40464c"))
    palette.setColor(QPalette.Active, QPalette.Midlight, QColor("#33383c"))
    palette.setColor(QPalette.Active, QPalette.Dark, QColor("#101112"))
    palette.setColor(QPalette.Active, QPalette.Mid, QColor("#1c1e21"))
    palette.setColor(QPalette.Active, QPalette.Shadow, QColor("#0b0c0d"))
    palette.setColor(QPalette.Active, QPalette.PlaceholderText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Inactive, QPalette.Window, QColor("#202326"))
    palette.setColor(QPalette.Inactive, QPalette.WindowText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Inactive, QPalette.Base, QColor("#141618"))
    palette.setColor(QPalette.Inactive, QPalette.AlternateBase, QColor("#1d1f22"))
    palette.setColor(QPalette.Inactive, QPalette.ToolTipBase, QColor("#292c30"))
    palette.setColor(QPalette.Inactive, QPalette.ToolTipText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Inactive, QPalette.Text, QColor("#fcfcfc"))
    palette.setColor(QPalette.Inactive, QPalette.Button, QColor("#292c30"))
    palette.setColor(QPalette.Inactive, QPalette.ButtonText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Inactive, QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Inactive, QPalette.Highlight, QColor("#1b4155"))
    palette.setColor(QPalette.Inactive, QPalette.HighlightedText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Inactive, QPalette.Link, QColor("#1d99f3"))
    palette.setColor(QPalette.Inactive, QPalette.LinkVisited, QColor("#9b59b6"))
    palette.setColor(QPalette.Inactive, QPalette.Light, QColor("#40464c"))
    palette.setColor(QPalette.Inactive, QPalette.Midlight, QColor("#33383c"))
    palette.setColor(QPalette.Inactive, QPalette.Dark, QColor("#101112"))
    palette.setColor(QPalette.Inactive, QPalette.Mid, QColor("#1c1e21"))
    palette.setColor(QPalette.Inactive, QPalette.Shadow, QColor("#0b0c0d"))
    palette.setColor(QPalette.Inactive, QPalette.PlaceholderText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Disabled, QPalette.Window, QColor("#1f2124"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#686a6c"))
    palette.setColor(QPalette.Disabled, QPalette.Base, QColor("#131517"))
    palette.setColor(QPalette.Disabled, QPalette.AlternateBase, QColor("#1c1e20"))
    palette.setColor(QPalette.Disabled, QPalette.ToolTipBase, QColor("#292c30"))
    palette.setColor(QPalette.Disabled, QPalette.ToolTipText, QColor("#fcfcfc"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#606263"))
    palette.setColor(QPalette.Disabled, QPalette.Button, QColor("#272a2e"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6d6f72"))
    palette.setColor(QPalette.Disabled, QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#1f2124"))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor("#686a6c"))
    palette.setColor(QPalette.Disabled, QPalette.Link, QColor("#164160"))
    palette.setColor(QPalette.Disabled, QPalette.LinkVisited, QColor("#402b4c"))
    palette.setColor(QPalette.Disabled, QPalette.Light, QColor("#3f454b"))
    palette.setColor(QPalette.Disabled, QPalette.Midlight, QColor("#32363b"))
    palette.setColor(QPalette.Disabled, QPalette.Dark, QColor("#0f1012"))
    palette.setColor(QPalette.Disabled, QPalette.Mid, QColor("#1a1d1f"))
    palette.setColor(QPalette.Disabled, QPalette.Shadow, QColor("#0b0c0d"))
    palette.setColor(QPalette.Disabled, QPalette.PlaceholderText, QColor("#fcfcfc"))
    if accent_color:
        palette = accentPalette(palette=palette, accent_color=accent_color)
    return palette


def standardPalette(accent_color: str = "") -> QPalette:
    """
    Applies Ubuntu palette, with accent from Gnome settings.

    :param accent_color: accent color in English form, e.g. "blue", or "yaru-olive"
    """

    palette = QPalette()
    palette.setColor(QPalette.Active, QPalette.Window, QColor("#efefef"))
    palette.setColor(QPalette.Active, QPalette.WindowText, QColor("#000000"))
    palette.setColor(QPalette.Active, QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.Active, QPalette.AlternateBase, QColor("#f7f7f7"))
    palette.setColor(QPalette.Active, QPalette.ToolTipBase, QColor("#ffffdc"))
    palette.setColor(QPalette.Active, QPalette.ToolTipText, QColor("#000000"))
    palette.setColor(QPalette.Active, QPalette.Text, QColor("#000000"))
    palette.setColor(QPalette.Active, QPalette.Button, QColor("#efefef"))
    palette.setColor(QPalette.Active, QPalette.ButtonText, QColor("#000000"))
    palette.setColor(QPalette.Active, QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Active, QPalette.Highlight, QColor("#308cc6"))
    palette.setColor(QPalette.Active, QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Active, QPalette.Link, QColor("#0000ff"))
    palette.setColor(QPalette.Active, QPalette.LinkVisited, QColor("#ff00ff"))
    palette.setColor(QPalette.Active, QPalette.Light, QColor("#ffffff"))
    palette.setColor(QPalette.Active, QPalette.Midlight, QColor("#cacaca"))
    palette.setColor(QPalette.Active, QPalette.Dark, QColor("#9f9f9f"))
    palette.setColor(QPalette.Active, QPalette.Mid, QColor("#b8b8b8"))
    palette.setColor(QPalette.Active, QPalette.Shadow, QColor("#767676"))
    palette.setColor(QPalette.Active, QPalette.PlaceholderText, QColor("#000000"))
    palette.setColor(QPalette.Inactive, QPalette.Window, QColor("#efefef"))
    palette.setColor(QPalette.Inactive, QPalette.WindowText, QColor("#000000"))
    palette.setColor(QPalette.Inactive, QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.Inactive, QPalette.AlternateBase, QColor("#f7f7f7"))
    palette.setColor(QPalette.Inactive, QPalette.ToolTipBase, QColor("#ffffdc"))
    palette.setColor(QPalette.Inactive, QPalette.ToolTipText, QColor("#000000"))
    palette.setColor(QPalette.Inactive, QPalette.Text, QColor("#000000"))
    palette.setColor(QPalette.Inactive, QPalette.Button, QColor("#efefef"))
    palette.setColor(QPalette.Inactive, QPalette.ButtonText, QColor("#000000"))
    palette.setColor(QPalette.Inactive, QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Inactive, QPalette.Highlight, QColor("#308cc6"))
    palette.setColor(QPalette.Inactive, QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Inactive, QPalette.Link, QColor("#0000ff"))
    palette.setColor(QPalette.Inactive, QPalette.LinkVisited, QColor("#ff00ff"))
    palette.setColor(QPalette.Inactive, QPalette.Light, QColor("#ffffff"))
    palette.setColor(QPalette.Inactive, QPalette.Midlight, QColor("#cacaca"))
    palette.setColor(QPalette.Inactive, QPalette.Dark, QColor("#9f9f9f"))
    palette.setColor(QPalette.Inactive, QPalette.Mid, QColor("#b8b8b8"))
    palette.setColor(QPalette.Inactive, QPalette.Shadow, QColor("#767676"))
    palette.setColor(QPalette.Inactive, QPalette.PlaceholderText, QColor("#000000"))
    palette.setColor(QPalette.Disabled, QPalette.Window, QColor("#efefef"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#bebebe"))
    palette.setColor(QPalette.Disabled, QPalette.Base, QColor("#efefef"))
    palette.setColor(QPalette.Disabled, QPalette.AlternateBase, QColor("#f7f7f7"))
    palette.setColor(QPalette.Disabled, QPalette.ToolTipBase, QColor("#ffffdc"))
    palette.setColor(QPalette.Disabled, QPalette.ToolTipText, QColor("#000000"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#bebebe"))
    palette.setColor(QPalette.Disabled, QPalette.Button, QColor("#efefef"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#bebebe"))
    palette.setColor(QPalette.Disabled, QPalette.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor("#919191"))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Link, QColor("#0000ff"))
    palette.setColor(QPalette.Disabled, QPalette.LinkVisited, QColor("#ff00ff"))
    palette.setColor(QPalette.Disabled, QPalette.Light, QColor("#ffffff"))
    palette.setColor(QPalette.Disabled, QPalette.Midlight, QColor("#cacaca"))
    palette.setColor(QPalette.Disabled, QPalette.Dark, QColor("#bebebe"))
    palette.setColor(QPalette.Disabled, QPalette.Mid, QColor("#b8b8b8"))
    palette.setColor(QPalette.Disabled, QPalette.Shadow, QColor("#b1b1b1"))
    palette.setColor(QPalette.Disabled, QPalette.PlaceholderText, QColor("#000000"))
    if accent_color:
        palette = accentPalette(palette=palette, accent_color=accent_color)
    return palette
