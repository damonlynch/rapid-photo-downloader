# -*- coding: utf-8 -*-
#
# Copyright 2012 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# In addition, as a special exception, the copyright holders give
# permission to link the code of portions of this program with the
# OpenSSL library under certain conditions as described in each
# individual source file, and distribute linked combinations
# including the two.
# You must obey the GNU General Public License in all respects
# for all of the code used other than OpenSSL.  If you modify
# file(s) with this exception, you may extend this exception to your
# version of the file(s), but you are not obligated to do so.  If you
# do not wish to do so, delete this exception statement from your
# version.  If you delete this exception statement from all source
# files in the program, then also delete it here.

# 2015: Lightly modified by Damon Lynch to use Qt 5

"""Widget written in Qt that works as a GtkArrow."""

from PyQt5.QtGui import (QPainter)
from PyQt5.QtWidgets import (QStyle, QStyleOption, QWidget)


class QArrow(QWidget):
    """Custom widget."""

    UP = 0
    DOWN = 1
    LEFT = 2
    RIGHT = 3

    def __init__(self, direction, parent=None):
        """Create a new instance."""
        super().__init__(parent)
        self._set_direction(direction)
        self.setFixedWidth(16)

    # pylint: disable=C0103
    def paintEvent(self, event):
        """Paint the widget."""
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        if self._direction == QArrow.UP:
            primitive = QStyle.PE_IndicatorArrowUp
        elif self._direction == QArrow.DOWN:
            primitive = QStyle.PE_IndicatorArrowDown
        elif self._direction == QArrow.LEFT:
            primitive = QStyle.PE_IndicatorArrowLeft
        else:
            primitive = QStyle.PE_IndicatorArrowRight
        painter.translate(-5, 0)
        painter.setViewTransformEnabled(True)
        self.style().drawPrimitive(primitive, opt, painter, self)
    # pylint: enable=C0103

    def _get_direction(self):
        """Return the direction used."""
        return self._direction

    # pylint: disable=W0201
    def _set_direction(self, direction):
        """Set the direction."""
        if direction not in (QArrow.UP, QArrow.DOWN,
                             QArrow.LEFT, QArrow.RIGHT):
            raise ValueError('Wrong arrow direction.')
        self._direction = direction
        self.repaint()
    # pylint: enable=W0201

    direction = property(_get_direction, _set_direction)
