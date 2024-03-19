# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Toggle Switch reminiscent of Android On/off switches:
https://www.google.com/design/spec/components/selection-controls.html

Visual style is rounded. However, by adjusting the style sheet it can be
made like a rounded square, close to how Gnome handles it, albeit
without the "ON"/"OFF text.

Inspiration:
http://stackoverflow.com/questions/14780517/toggle-switch-in-qt
http://thesmithfam.org/blog/2010/03/10/fancy-qslider-stylesheet/
"""

from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPalette
from PyQt5.QtWidgets import QAbstractSlider, QApplication, QSlider


class QToggleSwitch(QSlider):
    """
    Toggle Switch reminiscent of Android On/off switches.

    Connect to signal valueChanged to react to user setting the switch.
    """

    def __init__(
        self, background: QColor | None = None, parent=None, size: int = 2
    ) -> None:
        """
        Toggle switch that can be dragged or clicked to change value

        :param background: background color
        :param parent: parent widget
        :param size: size of widget as multiplier, where base widget height is half
         that of font height
        """
        super().__init__(Qt.Horizontal, parent)

        self.base_height = QFontMetrics(QFont()).height() // 2 * size
        self.radius = self.base_height // 2

        width = self.base_height * 2
        self.widgetWidth = width
        self.handleWidth = width // 2
        self.sliderRange = width
        self.sliderMidPoint = width // 2
        self.setRange(0, self.sliderRange)

        self.setMaximumWidth(self.widgetWidth)
        self.setFixedHeight(self.base_height + 6)

        # Track if button was dragged in the control
        self.dragged = False

        self.setStyleSheet(self.stylesheet(background))

        self.actionTriggered.connect(self.onActionTriggered)
        self.sliderReleased.connect(self.onSliderRelease)

    def stylesheet(self, background: QColor | None) -> str:
        shading_intensity = 104
        windowColor: QColor = QPalette().color(QPalette().Window)

        if background is None:
            backgroundName = windowColor.name()
        else:
            backgroundName = QColor(background).name()

        handleLightName: str = (QPalette().color(QPalette().Light)).name()
        handleDarkName: str = (QPalette().color(QPalette().Dark)).name()
        handleHoverLightName = (
            (QPalette().color(QPalette().Light)).lighter(shading_intensity).name()
        )
        handleHoverDarkName = (
            (QPalette().color(QPalette().Dark)).darker(shading_intensity).name()
        )

        insetDarkName = windowColor.darker(108).name()
        insetLightName = windowColor.darker(102).name()

        highlightColor: QColor = QPalette().color(QPalette().Highlight)
        highlightLightName = highlightColor.lighter(110).name()
        highlightDarkName = highlightColor.darker(130).name()

        return f"""
            QSlider::groove:horizontal {{
                background-color: {backgroundName};
                height: {self.base_height}px;
            }}

            QSlider::sub-page:horizontal {{
            background: qlineargradient(x1: 0, y1: 0.2, x2: 1, y2: 1,
                stop: 0 {highlightDarkName}, stop: 1 {highlightLightName});
            border: 1px solid #777;
            border-top-left-radius: {self.radius}px;
            border-bottom-left-radius: {self.radius}px;
            }}

            QSlider::add-page:horizontal {{
            background: qlineargradient(x1: 0, y1: 0.2, x2: 1, y2: 1,
                stop: 0 {insetDarkName}, stop: 1 {insetLightName});
            border: 1px solid #777;
            border-top-right-radius: {self.radius}px;
            border-bottom-right-radius: {self.radius}px;
            }}

            QSlider::handle:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {handleLightName}, stop:1 {handleDarkName});
            border: 1px solid #777;
            width: {self.handleWidth}px;
            border-radius: {self.radius}px;
            }}

            QSlider::handle:horizontal:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {handleHoverLightName}, stop:1 {handleHoverDarkName});
            border: 1px solid #444;
            border-radius: {self.radius}px;
            }}

            QSlider::sub-page:horizontal:disabled {{
            background: #bbb;
            border-color: #999;
            }}

            QSlider::add-page:horizontal:disabled {{
            background: #eee;
            border-color: #999;
            }}

            QSlider::handle:horizontal:disabled {{
            background: #eee;
            border: 1px solid #aaa;
            border-radius: {self.radius}px;
            }}
        """

    @pyqtSlot(int)
    def onActionTriggered(self, action: int) -> None:
        if action == QAbstractSlider.SliderMove:
            self.dragged = True
        else:
            if action % 2:
                self.setValue(self.sliderRange)
            else:
                self.setValue(0)

    @pyqtSlot()
    def onSliderRelease(self) -> None:
        if self.dragged:
            if self.sliderPosition() >= self.sliderMidPoint:
                self.setValue(self.sliderRange)
            else:
                self.setValue(0)
            self.dragged = False
        else:
            # Account for user pressing the button itself
            if self.value() == self.sliderRange:
                self.setValue(0)
            else:
                self.setValue(self.sliderRange)

    def on(self) -> bool:
        return self.value() == self.sliderRange

    def setOn(self, on: bool = True) -> None:
        if on:
            self.setValue(self.sliderRange)
        else:
            self.setValue(0)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    b = QToggleSwitch(size=10)
    b.show()
    sys.exit(app.exec_())
