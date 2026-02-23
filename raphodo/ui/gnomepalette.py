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
    ("mint-l", "#92b372"),
    ("mint-l-aqua", "#6cabcd"),
    ("mint-l-blue", "#5b73c4"),
    ("mint-l-brown", "#aa876a"),
    ("mint-l-dark", "#92b372"),
    ("mint-l-dark-aqua", "#6cabcd"),
    ("mint-l-dark-blue", "#5b73c4"),
    ("mint-l-dark-brown", "#aa876a"),
    ("mint-l-darker", "#92b372"),
    ("mint-l-darker-aqua", "#6cabcd"),
    ("mint-l-darker-blue", "#5b73c4"),
    ("mint-l-darker-brown", "#aa876a"),
    ("mint-l-darker-grey", "#9d9d9d"),
    ("mint-l-darker-orange", "#db9d61"),
    ("mint-l-darker-pink", "#c76199"),
    ("mint-l-darker-purple", "#8c6ec9"),
    ("mint-l-darker-red", "#c15b58"),
    ("mint-l-darker-sand", "#c8ac69"),
    ("mint-l-darker-teal", "#5aaa9a"),
    ("mint-l-dark-grey", "#9d9d9d"),
    ("mint-l-dark-orange", "#db9d61"),
    ("mint-l-dark-pink", "#c76199"),
    ("mint-l-dark-purple", "#8c6ec9"),
    ("mint-l-dark-red", "#c15b58"),
    ("mint-l-dark-sand", "#c8ac69"),
    ("mint-l-dark-teal", "#5aaa9a"),
    ("mint-l-grey", "#9d9d9d"),
    ("mint-l-orange", "#db9d61"),
    ("mint-l-pink", "#c76199"),
    ("mint-l-purple", "#8c6ec9"),
    ("mint-l-red", "#c15b58"),
    ("mint-l-sand", "#c8ac69"),
    ("mint-l-teal", "#5aaa9a"),
    ("mint-x", "#78aeed"),
    ("mint-x", "#9ab87c"),
    ("mint-x-aqua", "#6cabcd"),
    ("mint-x-aqua", "#78aeed"),
    ("mint-x-blue", "#5b73c4"),
    ("mint-x-blue", "#78aeed"),
    ("mint-x-brown", "#78aeed"),
    ("mint-x-brown", "#aa876a"),
    ("mint-x-grey", "#78aeed"),
    ("mint-x-grey", "#9d9d9d"),
    ("mint-x-orange", "#78aeed"),
    ("mint-x-orange", "#db9d61"),
    ("mint-x-pink", "#78aeed"),
    ("mint-x-pink", "#c76199"),
    ("mint-x-purple", "#78aeed"),
    ("mint-x-purple", "#8c6ec9"),
    ("mint-x-red", "#78aeed"),
    ("mint-x-red", "#c15b58"),
    ("mint-x-sand", "#78aeed"),
    ("mint-x-sand", "#c8ac69"),
    ("mint-x-teal", "#5aaa9a"),
    ("mint-x-teal", "#78aeed"),
    ("mint-y", "#35a854"),
    ("mint-y-aqua", "#1f9ede"),
    ("mint-y-blue", "#0c75de"),
    ("mint-y-dark", "#35a854"),
    ("mint-y-dark-aqua", "#1f9ede"),
    ("mint-y-dark-blue", "#0c75de"),
    ("mint-y-dark-grey", "#70737a"),
    ("mint-y-dark-orange", "#ff7139"),
    ("mint-y-dark-pink", "#e54980"),
    ("mint-y-dark-purple", "#8c5dd9"),
    ("mint-y-dark-red", "#e82127"),
    ("mint-y-dark-sand", "#c5a07c"),
    ("mint-y-dark-teal", "#199ca8"),
    ("mint-y-grey", "#70737a"),
    ("mint-y-orange", "#ff7139"),
    ("mint-y-pink", "#e54980"),
    ("mint-y-purple", "#8c5dd9"),
    ("mint-y-red", "#e82127"),
    ("mint-y-sand", "#c5a07c"),
    ("mint-y-teal", "#199ca8"),
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
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, accent)
    return palette


def darkPalette(accent_color: str = "") -> QPalette:
    """
    Applies KDE plasma dark palette, with accent from Gnome settings.

    :param accent_color: accent color in English form, e.g. "blue", or "yaru-olive"
    """

    palette = QPalette()
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor("#202326"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Base, QColor("#141618"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase, QColor("#1d1f22"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipBase, QColor("#292c30"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Button, QColor("#292c30"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor("#3daee9"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Link, QColor("#1d99f3"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.LinkVisited, QColor("#9b59b6"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Light, QColor("#40464c"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight, QColor("#33383c"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Dark, QColor("#101112"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Mid, QColor("#1c1e21"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Shadow, QColor("#0b0c0d"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor("#202326"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor("#141618"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.AlternateBase, QColor("#1d1f22"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase, QColor("#292c30"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor("#292c30"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#1b4155"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor("#1d99f3"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.LinkVisited, QColor("#9b59b6"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Light, QColor("#40464c"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Midlight, QColor("#33383c"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Dark, QColor("#101112"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Mid, QColor("#1c1e21"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Shadow, QColor("#0b0c0d"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.PlaceholderText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor("#1f2124"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#686a6c"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#131517"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.AlternateBase, QColor("#1c1e20"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipBase, QColor("#292c30"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor("#fcfcfc"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#606263"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#272a2e"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#6d6f72"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#1f2124"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor("#686a6c"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor("#164160"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.LinkVisited, QColor("#402b4c"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light, QColor("#3f454b"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Midlight, QColor("#32363b"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Dark, QColor("#0f1012"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Mid, QColor("#1a1d1f"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Shadow, QColor("#0b0c0d"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, QColor("#fcfcfc"))
    if accent_color:
        palette = accentPalette(palette=palette, accent_color=accent_color)
    return palette


def standardPalette(accent_color: str = "") -> QPalette:
    """
    Applies Ubuntu palette, with accent from Gnome settings.

    :param accent_color: accent color in English form, e.g. "blue", or "yaru-olive"
    """

    palette = QPalette()
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor("#efefef"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase, QColor("#f7f7f7"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipBase, QColor("#ffffdc"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Button, QColor("#efefef"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor("#308cc6"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Link, QColor("#0000ff"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.LinkVisited, QColor("#ff00ff"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Light, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight, QColor("#cacaca"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Dark, QColor("#9f9f9f"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Mid, QColor("#b8b8b8"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Shadow, QColor("#767676"))
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor("#efefef"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.AlternateBase, QColor("#f7f7f7"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase, QColor("#ffffdc"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor("#efefef"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#308cc6"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor("#0000ff"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.LinkVisited, QColor("#ff00ff"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Light, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Midlight, QColor("#cacaca"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Dark, QColor("#9f9f9f"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Mid, QColor("#b8b8b8"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Shadow, QColor("#767676"))
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.PlaceholderText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor("#efefef"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#bebebe"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#efefef"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.AlternateBase, QColor("#f7f7f7"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipBase, QColor("#ffffdc"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor("#000000"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#bebebe"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#efefef"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#bebebe"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#919191"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor("#0000ff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.LinkVisited, QColor("#ff00ff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Midlight, QColor("#cacaca"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Dark, QColor("#bebebe"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Mid, QColor("#b8b8b8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Shadow, QColor("#b1b1b1"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, QColor("#000000"))
    if accent_color:
        palette = accentPalette(palette=palette, accent_color=accent_color)
    return palette
