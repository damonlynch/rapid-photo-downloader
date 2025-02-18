# SPDX-FileCopyrightText: Copyright 2012-2014 Alexander Turkin
# SPDX-FileCopyrightText: Copyright 2014 William Hallatt
# SPDX-FileCopyrightText: Copyright 2015 Jacob Dawid
# SPDX-FileCopyrightText: Copyright 2016 Luca Weiss
# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch
# SPDX-License-Identifier: MIT

import math

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPaintEvent
from PyQt5.QtWidgets import QWidget

from raphodo.ui.viewconstants import icon_size

number_spinner_lines = 10
revolutions_per_second = 1


# For an enhanced version of this code, see https://github.com/fbjorn/QtWaitingSpinner


class SpinnerWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.spinnerColor = QColor(Qt.GlobalColor.black)
        self._roundness = 100.0
        self._min_trail_opacity = math.pi
        self._trail_fade_percent = 80.0
        size = icon_size()
        self._line_length = max(size // 4, 4)
        self._line_width = self._line_length // 2
        self._inner_radius = size // 2 - self._line_length

        s = int((self._inner_radius + self._line_length) * 2)
        self.setFixedSize(s, s)

        # Update this value to make the spinner rotate
        self._rotation = 0

    @property
    def rotation(self) -> int:
        return self._rotation

    @rotation.setter
    def rotation(self, rotation: int) -> None:
        self._rotation = rotation
        self.update()

    def lineCountDistanceFromPrimary(self, current, primary):
        distance = primary - current
        if distance < 0:
            distance += number_spinner_lines
        return distance

    def currentLineColor(self, count_distance: int) -> QColor:
        # Making a copy of the color is critical
        color = QColor(self.spinnerColor)
        if count_distance == 0:
            return color
        minAlphaF = self._min_trail_opacity / 100.0
        distance_threshold = int(
            math.ceil((number_spinner_lines - 1) * self._trail_fade_percent / 100.0)
        )
        if count_distance > distance_threshold:
            color.setAlphaF(minAlphaF)
        else:
            alphaDiff = color.alphaF() - minAlphaF
            gradient = alphaDiff / float(distance_threshold + 1)
            resultAlpha = color.alphaF() - gradient * count_distance
            # If alpha is out of bounds, clip it.
            resultAlpha = min(1.0, max(0.0, resultAlpha))
            color.setAlphaF(resultAlpha)
        return color

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        for i in range(0, number_spinner_lines):
            painter.save()
            painter.translate(
                self._inner_radius + self._line_length,
                self._inner_radius + self._line_length,
            )
            rotate_angle = float(360 * i) / float(number_spinner_lines)
            painter.rotate(rotate_angle)
            painter.translate(self._inner_radius, 0)
            distance = self.lineCountDistanceFromPrimary(i, self._rotation)
            color = self.currentLineColor(distance)
            painter.setBrush(color)
            rect = QRectF(
                0,
                -self._line_width / 2,
                self._line_length,
                self._line_width,
            )
            painter.drawRoundedRect(
                rect,
                self._roundness,
                self._roundness,
                Qt.RelativeSize,
            )
            painter.restore()
