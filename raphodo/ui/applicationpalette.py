#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: GPL-3.0-or-later


from PyQt6.QtGui import (
    QColor,
    QPalette,
)


def darkPalette(accent: QColor) -> QPalette:
    """
    Applies KDE plasma dark palette, with accent from desktop settings.

    :param accent: theme accent color
    """

    palette = QPalette()
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor("#202326")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Base, QColor("#141618")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase, QColor("#1d1f22")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipBase, QColor("#292c30")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipText, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Button, QColor("#292c30")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.BrightText, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor("#3daee9")
    )
    palette.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.HighlightedText,
        QColor("#fcfcfc"),
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Link, QColor("#1d99f3")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.LinkVisited, QColor("#9b59b6")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Light, QColor("#40464c")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight, QColor("#33383c")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Dark, QColor("#101112")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Mid, QColor("#1c1e21")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Shadow, QColor("#0b0c0d")
    )
    palette.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.PlaceholderText,
        QColor("#fcfcfc"),
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor("#202326")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor("#141618")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.AlternateBase,
        QColor("#1d1f22"),
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase, QColor("#292c30")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor("#292c30")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.BrightText, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#1b4155")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.HighlightedText,
        QColor("#fcfcfc"),
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor("#1d99f3")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.LinkVisited, QColor("#9b59b6")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Light, QColor("#40464c")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Midlight, QColor("#33383c")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Dark, QColor("#101112")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Mid, QColor("#1c1e21")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Shadow, QColor("#0b0c0d")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.PlaceholderText,
        QColor("#fcfcfc"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor("#1f2124")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#686a6c")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#131517")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.AlternateBase,
        QColor("#1c1e20"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipBase, QColor("#292c30")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor("#fcfcfc")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#606263")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#272a2e")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#6d6f72")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.BrightText, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#1f2124")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.HighlightedText,
        QColor("#686a6c"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor("#164160")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.LinkVisited, QColor("#402b4c")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light, QColor("#3f454b")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Midlight, QColor("#32363b")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Dark, QColor("#0f1012")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Mid, QColor("#1a1d1f")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Shadow, QColor("#0b0c0d")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.PlaceholderText,
        QColor("#fcfcfc"),
    )
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, accent)
    return palette


def standardPalette(accent: QColor) -> QPalette:
    """
    Applies Ubuntu palette, with accent from Gnome settings.

    :param accent: theme accent color
    """

    palette = QPalette()
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QColor("#efefef")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Base, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase, QColor("#f7f7f7")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipBase, QColor("#ffffdc")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ToolTipText, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Text, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Button, QColor("#efefef")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.BrightText, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, QColor("#308cc6")
    )
    palette.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.HighlightedText,
        QColor("#ffffff"),
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Link, QColor("#0000ff")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.LinkVisited, QColor("#ff00ff")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Light, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight, QColor("#cacaca")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Dark, QColor("#9f9f9f")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Mid, QColor("#b8b8b8")
    )
    palette.setColor(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Shadow, QColor("#767676")
    )
    palette.setColor(
        QPalette.ColorGroup.Active,
        QPalette.ColorRole.PlaceholderText,
        QColor("#000000"),
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window, QColor("#efefef")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.WindowText, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Base, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.AlternateBase,
        QColor("#f7f7f7"),
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase, QColor("#ffffdc")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Text, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Button, QColor("#efefef")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.ButtonText, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.BrightText, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, QColor("#308cc6")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.HighlightedText,
        QColor("#ffffff"),
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Link, QColor("#0000ff")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.LinkVisited, QColor("#ff00ff")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Light, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Midlight, QColor("#cacaca")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Dark, QColor("#9f9f9f")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Mid, QColor("#b8b8b8")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Shadow, QColor("#767676")
    )
    palette.setColor(
        QPalette.ColorGroup.Inactive,
        QPalette.ColorRole.PlaceholderText,
        QColor("#000000"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, QColor("#efefef")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#bebebe")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#efefef")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.AlternateBase,
        QColor("#f7f7f7"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipBase, QColor("#ffffdc")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ToolTipText, QColor("#000000")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#bebebe")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor("#efefef")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#bebebe")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.BrightText, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#919191")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.HighlightedText,
        QColor("#ffffff"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Link, QColor("#0000ff")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.LinkVisited, QColor("#ff00ff")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Light, QColor("#ffffff")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Midlight, QColor("#cacaca")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Dark, QColor("#bebebe")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Mid, QColor("#b8b8b8")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Shadow, QColor("#b1b1b1")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.PlaceholderText,
        QColor("#000000"),
    )
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorGroup.Inactive, QPalette.ColorRole.Highlight, accent)
    return palette
