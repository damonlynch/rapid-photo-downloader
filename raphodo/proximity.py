# Copyright (C) 2015-2018 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Rapid Photo Downloader is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Rapid Photo Downloader.  If not,
# see <http://www.gnu.org/licenses/>.

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2015-2018, Damon Lynch"

from collections import (namedtuple, defaultdict, deque, Counter)
from operator import attrgetter
import locale
from datetime import datetime
import logging
from itertools import groupby
import pickle
from pprint import pprint
import math
from typing import Dict, List, Tuple, Set, Optional, DefaultDict

import arrow.arrow
from arrow.arrow import Arrow

from gettext import gettext as _

from PyQt5.QtCore import (
    QAbstractTableModel, QModelIndex, Qt, QSize, QRect, QItemSelection, QItemSelectionModel,
    QBuffer, QIODevice, pyqtSignal, pyqtSlot, QRectF, QPoint,
)
from PyQt5.QtWidgets import (
    QTableView, QStyledItemDelegate, QSlider, QLabel, QVBoxLayout, QStyleOptionViewItem, QStyle,
    QAbstractItemView, QWidget, QHBoxLayout, QSizePolicy, QSplitter, QScrollArea, QStackedWidget,
    QToolButton, QAction
)
from PyQt5.QtGui import (
    QPainter, QFontMetrics, QFont, QColor, QGuiApplication, QPixmap, QPalette, QMouseEvent, QIcon
)

from raphodo.constants import (
    FileType, Align, proximity_time_steps, TemporalProximityState, fileTypeColor, CustomColors,
    DarkGray, MediumGray, DoubleDarkGray
)
from raphodo.rpdfile import FileTypeCounter
from raphodo.preferences import Preferences
from raphodo.viewutils import ThumbnailDataForProximity, QFramedWidget, QFramedLabel
from raphodo.timeutils import locale_time, strip_zero, make_long_date_format, strip_am, strip_pm
from raphodo.utilities import runs
from raphodo.constants import Roles

ProximityRow = namedtuple(
    'ProximityRow', 'year, month, weekday, day, proximity, new_file, tooltip_date_col0, '
                    'tooltip_date_col1, tooltip_date_col2'
)

UidTime = namedtuple('UidTime', 'ctime, arrowtime, uid, previously_downloaded')


def humanize_time_span(start: Arrow, end: Arrow,
                       strip_leading_zero_from_time: bool=True,
                       insert_cr_on_long_line: bool=False,
                       long_format: bool=False) -> str:
    r"""
    Make times and time spans human readable.

    To run the doc test, install language packs for Russian, German and Chinese
    in addition to English. See details in doctest.

    :param start: start time
    :param end: end time
    :param strip_leading_zero_from_time: strip all leading zeros
    :param insert_cr_on_long_line: insert a carriage return on long
     lines
    :param long_format: if True, return result in long format  
    :return: tuple of time span to be read by humans, in short and long format

    >>> locale.setlocale(locale.LC_ALL, ('en_US', 'utf-8'))
    'en_US.UTF-8'
    >>> start = arrow.Arrow(2015,11,3,9)
    >>> end = start
    >>> print(humanize_time_span(start, end))
    9:00 AM
    >>> print(humanize_time_span(start, end, long_format=True))
    Nov 3 2015, 9:00 AM
    >>> print(humanize_time_span(start, end, False))
    09:00 AM
    >>> print(humanize_time_span(start, end, False, long_format=True))
    Nov 3 2015, 09:00 AM
    >>> start = arrow.Arrow(2015,11,3,9,1,23)
    >>> end = arrow.Arrow(2015,11,3,9,1,24)
    >>> print(humanize_time_span(start, end))
    9:01 AM
    >>> print(humanize_time_span(start, end, long_format=True))
    Nov 3 2015, 9:01 AM
    >>> start = arrow.Arrow(2015,11,3,9)
    >>> end = arrow.Arrow(2015,11,3,10)
    >>> print(humanize_time_span(start, end))
    9:00 - 10:00 AM
    >>> print(humanize_time_span(start, end, long_format=True))
    Nov 3 2015, 9:00 - 10:00 AM
    >>> start = arrow.Arrow(2015,11,3,9)
    >>> end = arrow.Arrow(2015,11,3,13)
    >>> print(humanize_time_span(start, end))
    9:00 AM - 1:00 PM
    >>> print(humanize_time_span(start, end, long_format=True))
    Nov 3 2015, 9:00 AM - 1:00 PM
    >>> start = arrow.Arrow(2015,11,3,12)
    >>> print(humanize_time_span(start, end))
    12:00 - 1:00 PM
    >>> print(humanize_time_span(start, end, long_format=True))
    Nov 3 2015, 12:00 - 1:00 PM
    >>> start = arrow.Arrow(2015,11,3,12, 59)
    >>> print(humanize_time_span(start, end))
    12:59 - 1:00 PM
    >>> print(humanize_time_span(start, end, long_format=True))
    Nov 3 2015, 12:59 - 1:00 PM
    >>> start = arrow.Arrow(2015,10,31,11,55)
    >>> end = arrow.Arrow(2015,11,2,15,15)
    >>> print(humanize_time_span(start, end))
    Oct 31, 11:55 AM - Nov 2, 3:15 PM
    >>> print(humanize_time_span(start, end, long_format=True))
    Oct 31 2015, 11:55 AM - Nov 2 2015, 3:15 PM
    >>> start = arrow.Arrow(2014,10,31,11,55)
    >>> print(humanize_time_span(start, end))
    Oct 31 2014, 11:55 AM - Nov 2 2015, 3:15 PM
    >>> print(humanize_time_span(start, end, long_format=True))
    Oct 31 2014, 11:55 AM - Nov 2 2015, 3:15 PM
    >>> print(humanize_time_span(start, end, False))
    Oct 31 2014, 11:55 AM - Nov 2 2015, 03:15 PM
    >>> print(humanize_time_span(start, end, False, long_format=True))
    Oct 31 2014, 11:55 AM - Nov 2 2015, 03:15 PM
    >>> print(humanize_time_span(start, end, False, True))
    Oct 31 2014, 11:55 AM -
    Nov 2 2015, 03:15 PM
    >>> print(humanize_time_span(start, end, False, True, long_format=True))
    Oct 31 2014, 11:55 AM - Nov 2 2015, 03:15 PM
    >>> locale.setlocale(locale.LC_ALL, ('ru_RU', 'utf-8'))
    'ru_RU.UTF-8'
    >>> start = arrow.Arrow(2015,11,3,9)
    >>> end = start
    >>> print(humanize_time_span(start, end))
    9:00
    >>> start = arrow.Arrow(2015,11,3,13)
    >>> end = start
    >>> print(humanize_time_span(start, end))
    13:00
    >>> print(humanize_time_span(start, end, long_format=True))
    ноя 3 2015, 13:00
    >>> locale.setlocale(locale.LC_ALL, ('de_DE', 'utf-8'))
    'de_DE.UTF-8'
    >>> start = arrow.Arrow(2015,12,18,13,15)
    >>> end = start
    >>> print(humanize_time_span(start, end))
    13:15
    >>> print(humanize_time_span(start, end, long_format=True))
    Dez 18 2015, 13:15
    >>> end = start.shift(hours=1)
    >>> print(humanize_time_span(start, end))
    13:15 - 14:15
    >>> locale.setlocale(locale.LC_ALL, ('zh_CN', 'utf-8'))
    'zh_CN.UTF-8'
    >>> start = arrow.Arrow(2015,12,18,19,59,33)
    >>> end = start
    >>> print(humanize_time_span(start, end))
    下午 07时59分
    >>> end = start.shift(hours=1)
    >>> print(humanize_time_span(start, end))
    07时59分 - 下午 08时59分
    """

    strip = strip_leading_zero_from_time

    if start.floor('minute') == end.floor('minute'):
        short_format = strip_zero(locale_time(start.datetime), strip)
        if not long_format:
            return short_format
        else:
            # Translators: for example Nov 3 2015, 11:25 AM
            return _('%(date)s, %(time)s') % dict(
                date=make_long_date_format(start),
                time=short_format
            )

    if start.floor('day') == end.floor('day'):
        # both dates are on the same day
        start_time = strip_zero(locale_time(start.datetime), strip)
        end_time = strip_zero(locale_time(end.datetime), strip)

        if (start.hour < 12 and end.hour < 12):
            # both dates are in the same morning
            start_time = strip_am(start_time)
        elif (start.hour >= 12 and end.hour >= 12):
            start_time = strip_pm(start_time)

        time_span = _('%(starttime)s - %(endtime)s') % dict(
            starttime=start_time,
            endtime=end_time
        )
        if not long_format:
            # Translators: for example 9:00 AM - 3:55 PM
            return time_span
        else:
            # Translators: for example Nov 3 2015, 11:25 AM
            return _('%(date)s, %(time)s') % dict(
                date=make_long_date_format(start),
                time=time_span
            )

    # The start and end dates are on a different day

    # Translators: for example Nov 3 or Dec 31
    start_date = _('%(month)s %(numeric_day)s') % dict(
        month=start.datetime.strftime('%b'),
        numeric_day=start.format('D')
    )
    end_date = _('%(month)s %(numeric_day)s') % dict(
        month=end.datetime.strftime('%b'),
        numeric_day=end.format('D')
    )

    if start.floor('year') != end.floor('year') or long_format:
        # Translators: for example Nov 3 2015
        start_date = _('%(date)s %(year)s') % dict(date=start_date, year=start.year)
        end_date = _('%(date)s %(year)s') % dict(date=end_date, year=end.year)

    # Translators: for example, Nov 3, 12:15 PM
    start_datetime = _('%(date)s, %(time)s') % dict(
        date=start_date, time=strip_zero(locale_time(start.datetime), strip)
    )
    end_datetime = _('%(date)s, %(time)s') % dict(
        date=end_date, time=strip_zero(locale_time(end.datetime), strip)
    )

    if not insert_cr_on_long_line or long_format:
        # Translators: for example, Nov 3, 12:15 PM - Nov 4, 1:00 AM
        return _('%(earlier_time)s - %(later_time)s') % dict(
            earlier_time=start_datetime, later_time=end_datetime
        )
    else:
        # Translators, for example:
        # Nov 3 2012, 12:15 PM -
        # Nov 4 2012, 1:00 AM
        # (please keep the line break signified by \n)
        return _('%(earlier_time)s -\n%(later_time)s') % dict(
            earlier_time=start_datetime, later_time=end_datetime
        )

FontKerning = namedtuple('FontKerning', 'font, kerning')


def monthFont() -> FontKerning:
    font = QFont()
    kerning = 1.2
    font.setPointSize(font.pointSize() - 2)
    font.setLetterSpacing(QFont.PercentageSpacing, kerning * 100)
    font.setStretch(QFont.SemiExpanded)
    return FontKerning(font, kerning)


def weekdayFont() -> QFont:
    font = QFont()
    font.setPointSize(font.pointSize() - 3)
    return font


def dayFont() -> QFont:
    font = QFont()
    font.setPointSize(font.pointSize() + 1)
    return font


def proximityFont() -> QFont:
    font = QFont()  # type: QFont
    font.setPointSize(font.pointSize() - 2)
    return font


def invalidRowFont() -> QFont:
    font = QFont()
    font.setPointSize(font.pointSize() - 3)
    return font


class ProximityDisplayValues:
    """
    Temporal Proximity cell sizes.

    Calculated in different process to that of main window.
    """

    def __init__(self):
        self.depth = None
        self.row_heights = []  # type: List[int]
        self.col_widths = None  # type: Optional[Tuple[int]]

        # row : (width, height)
        self.col0_sizes = {}  # type: Dict[int, Tuple[int, int]]
        self.c2_alignment = {}  # type: Dict[int, Align]
        self.c2_end_of_day = set()  # type: Set[int]
        self.c2_end_of_month = set()  # type: Set[int]
        self.c1_end_of_month = set()  # type: Set[int]

        self.assign_fonts()

        # Column 0 - month + year
        self.col0_padding = 20
        self.col0_center_space = 2
        self.col0_center_space_half = 1

        # Column 1 - weekday + day
        self.col1_center_space = 2
        self.col1_center_space_half = 1
        self.col1_padding = 10
        self.col1_v_padding = 50
        self.col1_v_padding_top = self.col1_v_padding_bot = self.col1_v_padding // 2

        self.calculate_max_col1_size()
        self.day_proportion = self.max_day_height / self.max_col1_text_height
        self.weekday_proportion = self.max_weekday_height / self.max_col1_text_height        

        # Column 2 - proximity value e.g. 1:00 - 1:45 PM
        self.col2_new_file_dot = False
        self.col2_new_file_dot_size = 4
        self.col2_new_file_dot_radius = self.col2_new_file_dot_size / 2
        self.col2_font_descent_adjust = self.proximityMetrics.descent() / 3
        self.col2_font_height_half = self.proximityMetrics.height() / 2
        self.col2_new_file_dot_left_margin = 6

        if self.col2_new_file_dot:
            self.col2_text_left_margin = (
                self.col2_new_file_dot_left_margin * 2 + self.col2_new_file_dot_size
            )
        else:
            self.col2_text_left_margin = 10
        self.col2_right_margin = 10
        self.col2_v_padding = 6
        self.col2_v_padding_half = 3

    def assign_fonts(self) -> None:
        self.proximityFont = proximityFont()
        self.proximityFontPrevious = QFont(self.proximityFont)
        self.proximityFontPrevious.setItalic(True)
        self.proximityMetrics = QFontMetrics(self.proximityFont)
        self.proximityMetricsPrevious = QFontMetrics(self.proximityFontPrevious)
        mf = monthFont()
        self.monthFont = mf.font
        self.month_kerning = mf.kerning
        self.monthMetrics = QFontMetrics(self.monthFont)
        self.weekdayFont = weekdayFont()
        self.dayFont = dayFont()
        self.invalidRowFont = invalidRowFont()
        self.invalidRowFontMetrics = QFontMetrics(self.invalidRowFont)
        self.invalidRowHeightMin = self.invalidRowFontMetrics.height() + \
                                   self.proximityMetrics.height()

    def prepare_for_pickle(self) -> None:
        self.proximityFont = self.proximityMetrics = None
        self.proximityFontPrevious = self.proximityMetricsPrevious = None
        self.monthFont = self.monthMetrics = None
        self.weekdayFont = None
        self.dayFont = None
        self.invalidRowFont = self.invalidRowFontMetrics = None

    def get_month_size(self, month: str) -> QSize:
        boundingRect = self.monthMetrics.boundingRect(month)  # type: QRect
        height = boundingRect.height()
        width = int(boundingRect.width() * self.month_kerning)
        size = QSize(width, height)
        return size

    def get_month_text(self, month, year) -> str:
        if self.depth == 3:
            return _('%(month)s  %(year)s') % dict(month=month.upper(), year=year)
        else:
            return month.upper()

    def column0Size(self, year: str, month: str) -> QSize:
        # Don't return a cell size for empty cells that have been
        # merged into the cell with content.
        month = self.get_month_text(month, year)
        size = self.get_month_size(month)
        # Height and width are reversed because of the rotation
        size.transpose()
        return QSize(size.width() + self.col0_padding, size.height() + self.col0_padding)

    def calculate_max_col1_size(self) -> None:
        """
        Determine largest size for column 1 cells.

        Column 1 cell sizes are fixed.
        """

        dayMetrics = QFontMetrics(dayFont())
        day_width = 0
        day_height = 0
        for day in range(10, 32):
            rect = dayMetrics.boundingRect(str(day))
            day_width = max(day_width, rect.width())
            day_height = max(day_height, rect.height())

        self.max_day_height = day_height
        self.max_day_width = day_width

        weekday_width = 0
        weekday_height = 0
        weekdayMetrics = QFontMetrics(weekdayFont())
        for i in range(1, 7):
            dt = datetime(2015, 11, i)  # Year and month are totally irrelevant, only want day
            weekday = dt.strftime('%a').upper()
            rect = weekdayMetrics.boundingRect(str(weekday))
            weekday_width = max(weekday_width, rect.width())
            weekday_height = max(weekday_height, rect.height())

        self.max_weekday_height = weekday_height
        self.max_weekday_width = weekday_width
        self.max_col1_text_height = weekday_height + day_height + self.col1_center_space
        self.max_col1_text_width = max(weekday_width, day_width)
        self.col1_width = self.max_col1_text_width + self.col1_padding
        self.col1_height = self.max_col1_text_height

    def get_proximity_size(self, text: str) -> QSize:
        text = text.split('\n')
        width = height = 0
        for t in text:
            boundingRect = self.proximityMetrics.boundingRect(t)  # type: QRect
            width = max(width, boundingRect.width())
            height += boundingRect.height()
        size = QSize(
            width  + self.col2_text_left_margin + self.col2_right_margin,
            height + self.col2_v_padding
        )
        return size

    def calculate_row_sizes(self, rows: List[ProximityRow],
                            spans: List[Tuple[int, int, int]],
                            depth: int) -> None:
        """
        Calculate row height and column widths. The latter is trivial,
        the former far more complex.

        Assumptions:
         * column 1 cell size is fixed

        :param rows: list of row details
        :param spans: list of which rows & columns are spanned
        :param depth: table depth
        """

        self.depth = depth

        # Phase 1: (1) identify minimal sizes for columns 0 and 2, and group the cells
        #          (2) assign alignment to column 2 cells

        spans_dict = {(row, column): row_span for column, row, row_span in spans}
        next_span_start_c0 = next_span_start_c1 = 0

        sizes = []  # type: List[Tuple[QSize, List[List[int]]]]
        for row, value in enumerate(rows):
            if next_span_start_c0 == row:
                c0_size = self.column0Size(value.year, value.month)
                self.col0_sizes[row] = (c0_size.width(), c0_size.height())
                c0_children = []
                sizes.append((c0_size, c0_children))
                c0_span = spans_dict.get((row, 0), 1)
                next_span_start_c0 = row + c0_span
                self.c2_end_of_month.add(row + c0_span - 1)
            if next_span_start_c1 == row:
                c1_children = []
                c0_children.append(c1_children)
                c1_span = spans_dict.get((row, 1), 1)
                next_span_start_c1 = row + c1_span

                c2_span = spans_dict.get((row + c1_span - 1, 2))
                if c1_span > 1:
                    self.c2_alignment[row] = Align.bottom
                    if c2_span is None:
                        self.c2_alignment[row + c1_span - 1] = Align.top

                if row + c1_span - 1 in self.c2_end_of_month:
                    self.c1_end_of_month.add(row)

                skip_c2_end_of_day = False
                if c2_span:
                    final_day_in_c2_span = row + c1_span - 2 + c2_span
                    c1_span_in_c2_span_final_day = spans_dict.get((final_day_in_c2_span, 1))
                    skip_c2_end_of_day = c1_span_in_c2_span_final_day is not None

                if not skip_c2_end_of_day:
                    self.c2_end_of_day.add(row + c1_span - 1)

            minimal_col2_size = self.get_proximity_size(value.proximity)
            c1_children.append(minimal_col2_size)

        # Phase 2: determine column 2 cell sizes, and max widths

        c0_max_width = 0
        c2_max_width = 0
        for c0, c0_children in sizes:
            c0_height = c0.height()
            c0_max_width = max(c0_max_width, c0.width())
            c0_children_height = 0
            for c1_children in c0_children:
                c1_children_height = sum(c2.height() for c2 in c1_children)
                c2_max_width = max(c2_max_width, max(c2.width() for c2 in c1_children))
                extra = math.ceil(max(self.col1_height - c1_children_height, 0) / 2)

                # Assign in c1's v_padding to first and last child, and any extra
                c2 = c1_children[0]  # type: QSize
                c2.setHeight(c2.height() + self.col1_v_padding_top + extra)
                c2 = c1_children[-1]  # type: QSize
                c2.setHeight(c2.height() + self.col1_v_padding_bot + extra)

                c1_children_height += self.col1_v_padding_top + self.col1_v_padding_bot + extra * 2
                c0_children_height += c1_children_height

            extra = math.ceil(max(c0_height - c0_children_height, 0) / 2)
            if extra:
                c2 = c0_children[0][0]  # type: QSize
                c2.setHeight(c2.height() + extra)
                c2 = c0_children[-1][-1]  # type: QSize
                c2.setHeight(c2.height() + extra)

            heights = [c2.height() for c1_children in c0_children for c2 in c1_children]
            self.row_heights.extend(heights)

        self.col_widths = (c0_max_width, self.col1_width, c2_max_width)

    def assign_color(self, dominant_file_type: FileType) -> None:
        self.tableColor = fileTypeColor(dominant_file_type)
        self.tableColorDarker = self.tableColor.darker(110)


class MetaUid:
    r"""
    Stores unique ids for each table cell.

    Used first when generating the proximity table, and then when
    displaying tooltips containing thumbnails.

    Operations are performed by tuple of (row, column) or simply
    by column.


    >>> m = MetaUid()
    >>> m[(0 , 0)] = [b'0', b'1', b'2']
    >>> print(m)
    MetaUid(({0: 3}, {}, {}) ({0: [b'0', b'1', b'2']}, {}, {}))
    >>> m[[0, 0]]
    [b'0', b'1', b'2']
    >>> m.trim()
    >>> m[[0, 0]]
    [b'0', b'2']
    >>> m.no_uids((0, 0))
    3
    """

    def __init__(self):
        self._uids = tuple({} for i in (0, 1 ,2))  # type: Tuple[Dict[int, List[bytes, ...]]]
        self._no_uids = tuple({} for i in (0, 1, 2))  # type: Tuple[Dict[int, int]]
        self._col2_row_index = dict()  # type: Dict[bytes, int]

    def __repr__(self):
        return 'MetaUid(%r %r)' % (self._no_uids, self._uids)

    def __setitem__(self, key: Tuple[int, int], uids: List[bytes]) -> None:
        row, col = key
        assert row not in self._uids[col]
        self._uids[col][row] = uids
        self._no_uids[col][row] = len(uids)
        for uid in uids:
            self._col2_row_index[uid] = row

    def __getitem__(self, key: Tuple[int, int]) -> List[bytes]:
        row, col = key
        return self._uids[col][row]

    def trim(self) -> None:
        """
        Remove unique ids unnecessary for table viewing.

        Don't, however, remove ids in col 2, as they're useful, e.g.
        when manually marking a file as previously downloaded
        """

        for col in (0, 1):
            for row in self._uids[col]:
                uids = self._uids[col][row]
                if len(uids) > 1:
                    self._uids[col][row] = [uids[0], uids[-1]]

    def no_uids(self, key: Tuple[int, int]) -> int:
        """
        Number of unique ids the cell had before it was trimmed.
        """

        row, col = key
        return self._no_uids[col][row]

    def uids(self, column: int) -> Dict[int, List[bytes]]:
        return self._uids[column]

    def uid_to_col2_row(self, uid) -> int:
        return self._col2_row_index[uid]

    def validate_rows(self, no_rows) -> Tuple[int]:
        """
        Very simple validation test to see if all rows are present
        in cols 2 or 1.

        :param no_rows: number of rows to validate
        :return: Tuple of missing rows
        """
        valid = []

        col0, col1, col2 = self._uids
        no_col0, no_col1, no_col2 = self._no_uids

        for i in range(no_rows):
            msg0 = ''
            msg1 = ''
            if i not in col2 and i not in col1:
                    msg0 = '_uids'
            if i not in no_col2 and i not in col1:
                msg1 = '_no_uids'
            if msg0 or msg1:
                msg = ' and '.join((msg0, msg1))
                logging.error("%s: row %s is missing in %s", self.__class__.__name__, i, msg)
                valid.append(i)

        return tuple(valid)


class TemporalProximityGroups:
    """
    Generates values to be displayed in Timeline view.

    The Timeline has 3 columns:

    Col 0: the year and month
    Col 1: the day of the month
    C0l 3: the proximity groups
    """

    # @profile
    def __init__(self, thumbnail_rows: List[ThumbnailDataForProximity],
                 temporal_span: int = 3600):
        self.rows = []  # type: List[ProximityRow]

        self.invalid_rows = tuple()  # type: Tuple[int]

        # Store uids for each table cell
        self.uids = MetaUid()

        self.file_types_in_cell = dict()  # type: Dict[Tuple[int, int], str]
        times_by_proximity = defaultdict(list)  # type: DefaultDict[int, Arrow]

        # The rows the user sees in column 2 can span more than one row of the Timeline.
        # Each day always spans at least one row in the Timeline, possibly more.

        # group_no: no days spanned
        day_spans_by_proximity = dict()  # type: Dict[int, int]
        # group_no: (
        uids_by_day_in_proximity_group = dict()  # type: Dict[int, Tuple[[Tuple[int, int, int], List[bytes]]]

        # uid: (year, month, day)
        year_month_day = dict()  # type: Dict[bytes, Tuple[int, int, int]]

        # group_no: List[uid]
        uids_by_proximity = defaultdict(list)  # type: Dict[int, List[bytes, ...]]
        # Determine if proximity group contains any files have not been previously downloaded
        new_files_by_proximity = defaultdict(set)  # type: Dict[int, Set[bool]]

        # Text that will appear in column 2 -- they proximity groups
        text_by_proximity = deque()

        # (year, month, day): [uid, uid, ...]
        self.day_groups = defaultdict(list)  # type: DefaultDict[Tuple[int, int, int], List[bytes]]
        # (year, month): [uid, uid, ...]
        self.month_groups = defaultdict(list)  # type: DefaultDict[Tuple[int, int], List[bytes]]
        # year: [uid, uid, ...]
        self.year_groups = defaultdict(list)  # type: DefaultDict[int, List[bytes]]

        # How many columns the Timeline will display - don't display year when the only dates
        # are from this year, for instance.
        self._depth = None  # type: Optional[int]
        # Compared to right now, does the Timeline contain an entry from the previous year?
        self._previous_year = False
        # Compared to right now, does the Timeline contain an entry from the previous month?
        self._previous_month = False

        # Tuple of (column, row, row_span):
        self.spans = []  # type: List[Tuple[int, int, int]]
        self.row_span_for_column_starts_at_row = {}  # type: Dict[Tuple[int, int], int]

        # Associate Timeline cells with uids
        # Timeline row: id
        self.proximity_view_cell_id_col1 = {}  # type: Dict[int, int]
        # Timeline row: id
        self.proximity_view_cell_id_col2 = {}  # type: Dict[int, int]
        # col1, col2, uid
        self.col1_col2_uid = []   # type: List[Tuple[int, int, bytes]]

        if len(thumbnail_rows) == 0:
            return

        file_types = (row.file_type for row in thumbnail_rows)
        self.dominant_file_type = Counter(file_types).most_common()[0][0]

        self.display_values = ProximityDisplayValues()

        thumbnail_rows.sort(key=attrgetter('ctime'))

        # Generate an arrow date time for every timestamp we have
        uid_times = [
            UidTime(
                tr.ctime, arrow.get(tr.ctime).to('local'), tr.uid, tr.previously_downloaded
            )
            for tr in thumbnail_rows
        ]

        self.thumbnail_types = tuple(row.file_type for row in thumbnail_rows)

        now = arrow.now().to('local')
        current_year = now.year
        current_month = now.month

        # Phase 1: Associate unique ids with their year, month and day
        for x in uid_times:
            t = x.arrowtime  # type: Arrow
            year = t.year
            month = t.month
            day = t.day

            # Could use arrow.floor here, but it's extremely slow
            self.day_groups[(year, month, day)].append(x.uid)
            self.month_groups[(year, month)].append(x.uid)
            self.year_groups[year].append(x.uid)
            if year != current_year:
                # the Timeline contains an entry from the previous year to now
                self._previous_year = True
            if month != current_month or self._previous_year:
                # the Timeline contains an entry from the previous month to now
                self._previous_month = True
            # Remember this extracted value
            year_month_day[x.uid] = year, month, day

        # Phase 2: Identify the proximity groups
        group_no = 0
        prev = uid_times[0]

        times_by_proximity[group_no].append(prev.arrowtime)
        uids_by_proximity[group_no].append(prev.uid)
        new_files_by_proximity[group_no].add(not prev.previously_downloaded)

        if len(uid_times) > 1:
            for current in uid_times[1:]:
                ctime = current.ctime
                if ctime - prev.ctime > temporal_span:
                    group_no += 1
                times_by_proximity[group_no].append(current.arrowtime)
                uids_by_proximity[group_no].append(current.uid)
                new_files_by_proximity[group_no].add(not current.previously_downloaded)
                prev = current

        # Phase 3: Generate the proximity group's text that will appear in
        # the right-most column and its tooltips.

        # Also calculate the days spanned by each proximity group.
        # If the days spanned is greater than 1, meaning the number of calendar days
        # in the proximity group is more than 1, then also keep a copy of the group
        # where it is broken into separate calendar days

        # The iteration order doesn't really matter here, so can get away with the
        # potentially unsorted output of dict.items()
        for group_no, group in times_by_proximity.items():
            start = group[0]  # type: Arrow
            end = group[-1]  # type: Arrow

            # Generate the text
            short_form = humanize_time_span(start, end, insert_cr_on_long_line=True)
            long_form = humanize_time_span(start, end, long_format=True)
            text_by_proximity.append((short_form, long_form))

            # Calculate the number of calendar days spanned by this proximity group
            # e.g. 2015-12-1 12:00 - 2015-12-2 15:00 = 2 days
            if len(group) > 1:
                span = len(Arrow.span_range('day', start, end))
                day_spans_by_proximity[group_no] = span
                if span > 1:
                    # break the proximity group members into calendar days
                    uids_by_day_in_proximity_group[group_no] = tuple(
                        (y_m_d, list(day))
                        for y_m_d, day in groupby(
                            uids_by_proximity[group_no], year_month_day.get
                        )
                    )
            else:
                # start == end
                day_spans_by_proximity[group_no] = 1

        # Phase 4: Generate the rows to be displayed in the Timeline

        # Keep in mind, the rows the user sees in column 2 can span more than
        # one calendar day. In such cases, column 1 will be associated with
        # one or more Timeline rows, one or more of which may be visible only in
        # column 1.

        timeline_row = -1  # index into each row in the Timeline
        thumbnail_index = 0 # index into the
        self.prev_row_month = (0, 0)
        self.prev_row_day = (0, 0, 0)

        # Iterating through the groups in order is critical. Cannot use dict.items() here.
        for group_no in range(len(day_spans_by_proximity)):

            span = day_spans_by_proximity[group_no]

            timeline_row += 1

            proximity_group_times = times_by_proximity[group_no]
            atime = proximity_group_times[0]  # type: Arrow
            uid = uids_by_proximity[group_no][0]  # type: bytes
            y_m_d = year_month_day[uid]

            col2_text, tooltip_col2_text = text_by_proximity.popleft()
            new_file = any(new_files_by_proximity[group_no])

            self.rows.append(
                self.make_row(
                    atime=atime,
                    col2_text=col2_text,
                    new_file=new_file,
                    y_m_d= y_m_d,
                    timeline_row=timeline_row,
                    thumbnail_index=thumbnail_index,
                    tooltip_col2_text=tooltip_col2_text,
                )
            )

            uids = uids_by_proximity[group_no]
            self.uids[(timeline_row, 2)] = uids

            # self.dump_row(group_no)

            if span == 1:
                thumbnail_index += len(proximity_group_times)
                continue

            thumbnail_index += len(uids_by_day_in_proximity_group[group_no][0])

            # For any proximity groups that span more than one Timeline row because they span
            # more than one calender day, add the day to the Timeline, with blank values
            # for the proximity group (column 2).
            i = 0
            for y_m_d, day in uids_by_day_in_proximity_group[group_no][1:]:
                i += 1

                timeline_row += 1
                thumbnail_index += len(uids_by_day_in_proximity_group[group_no][i])
                atime = arrow.get(*y_m_d)

                self.rows.append(
                    self.make_row(
                        atime=atime,
                        col2_text='',
                        new_file=new_file,
                        y_m_d=y_m_d,
                        timeline_row=timeline_row,
                        thumbnail_index=1,
                        tooltip_col2_text=''
                    )
                )
                # self.dump_row(group_no)

        # Phase 5: Determine the row spans for each column
        column = -1
        for c in (0, 2, 4):
            column += 1
            start_row = 0
            for timeline_row_index, row in enumerate(self.rows):
                if row[c]:
                    row_count = timeline_row_index - start_row
                    if row_count > 1:
                        self.spans.append((column, start_row, row_count))
                    start_row = timeline_row_index
                self.row_span_for_column_starts_at_row[(timeline_row_index, column)] = start_row

            if start_row != len(self.rows) - 1:
                self.spans.append((column, start_row, len(self.rows) - start_row))
                for timeline_row_index in range(start_row, len(self.rows)):
                    self.row_span_for_column_starts_at_row[(timeline_row_index, column)] = start_row

        assert len(self.row_span_for_column_starts_at_row) == len(self.rows) * 3

        # Phase 6: Determine the height and width of each row
        self.display_values.calculate_row_sizes(self.rows, self.spans, self.depth())

        # Phase 7: Assign appropriate color to table
        self.display_values.assign_color(self.dominant_file_type)

        # Phase 8: associate proximity table cells with uids

        uid_rows_c1 = {}
        for proximity_view_cell_id, timeline_row_index in enumerate(self.uids.uids(1)):
            self.proximity_view_cell_id_col1[timeline_row_index] = proximity_view_cell_id
            uids = self.uids.uids(1)[timeline_row_index]
            for uid in uids:
                uid_rows_c1[uid] = proximity_view_cell_id

        uid_rows_c2 = {}

        for proximity_view_cell_id, timeline_row_index in enumerate(self.uids.uids(2)):
            self.proximity_view_cell_id_col2[timeline_row_index] = proximity_view_cell_id
            uids = self.uids.uids(2)[timeline_row_index]
            for uid in uids:
                uid_rows_c2[uid] = proximity_view_cell_id

        assert len(uid_rows_c2) == len(uid_rows_c1) == len(thumbnail_rows)

        self.col1_col2_uid = [
            (uid_rows_c1[row.uid], uid_rows_c2[row.uid], row.uid) for row in thumbnail_rows
        ]

        # Assign depth before wiping values used to determine it
        self.depth()
        self.display_values.prepare_for_pickle()

        # Reduce memory use before pickle. Can save about 100MB with
        # when working with approximately 70,000 thumbnails.

        self.uids.trim()

        self.day_groups = None
        self.month_groups = None
        self.year_groups = None

        self.thumbnail_types = None

        self.invalid_rows = self.validate()
        if len(self.invalid_rows):
            logging.error('Timeline validation failed')
        else:
            logging.info('Timeline validation passed')

    def make_file_types_in_cell_text(self, slice_start: int, slice_end: int) -> str:
        c = FileTypeCounter(self.thumbnail_types[slice_start:slice_end])
        return c.summarize_file_count()[0]

    def make_row(self, atime: Arrow,
                 col2_text: str,
                 new_file: bool,
                 y_m_d: Tuple[int, int, int],
                 timeline_row: int,
                 thumbnail_index: int,
                 tooltip_col2_text: str) -> ProximityRow:

        atime_month = y_m_d[:2]
        if atime_month != self.prev_row_month:
            self.prev_row_month = atime_month
            month = atime.datetime.strftime('%B')
            year = atime.year
            uids = self.month_groups[atime_month]
            slice_end = thumbnail_index + len(uids)
            self.file_types_in_cell[(timeline_row, 0)] = self.make_file_types_in_cell_text(
                slice_start=thumbnail_index, slice_end=slice_end
            )
            self.uids[(timeline_row, 0)] = uids
        else:
            month = year = ''

        if y_m_d != self.prev_row_day:
            self.prev_row_day = y_m_d
            numeric_day = atime.format('D')
            weekday = atime.datetime.strftime('%a')

            self.uids[(timeline_row, 1)] = self.day_groups[y_m_d]
        else:
            weekday = numeric_day = ''

        month_day = _('%(month)s %(numeric_day)s') % dict(
            month=atime.datetime.strftime('%b'),
            numeric_day=atime.format('D')
        )
        # Translators: for example Nov 2 2015
        tooltip_col1 = _('%(date)s %(year)s') % dict(date= month_day, year=atime.year)
        # Translators: for example Nov 2015
        tooltip_col0 = _('%(month)s %(year)s') % dict(
            month=atime.datetime.strftime('%b'),
            year=atime.year
        )

        return ProximityRow(
            year=year, month=month, weekday=weekday, day=numeric_day, proximity=col2_text,
            new_file=new_file, tooltip_date_col0=tooltip_col0, tooltip_date_col1=tooltip_col1,
            tooltip_date_col2=tooltip_col2_text
        )

    def __len__(self) -> int:
        return len(self.rows)

    def dump_row(self, group_no, extra='') -> None:
        row = self.rows[-1]
        print(group_no, extra, row.day, row.proximity.replace('\n', ' '))

    def __getitem__(self, row_number) -> ProximityRow:
        return self.rows[row_number]

    def __setitem__(self, row_number, proximity_row: ProximityRow) -> None:
        self.rows[row_number] = proximity_row

    def __iter__(self):
        return iter(self.rows)

    def depth(self) -> int:
        if self._depth is None:
            if len(self.year_groups) > 1 or self._previous_year:
                self._depth = 3
            elif len(self.month_groups) > 1 or self._previous_month:
                self._depth = 2
            elif len(self.day_groups) > 1:
                self._depth = 1
            else:
                self._depth = 0
        return self._depth

    def __repr__(self) -> str:
        return 'TemporalProximityGroups with {} rows and depth of {}'.format(
            len(self.rows), self.depth()
        )

    def validate(self, thumbnailModel=None) -> Tuple[int]:
        """
        Partial validation of proximity values
        :return:
        """

        return self.uids.validate_rows(len(self.rows))

    def uid_to_row(self, uid: bytes) -> int:
        return self.uids.uid_to_col2_row(uid=uid)

    def row_uids(self, row: int) -> List[bytes]:
        return self.uids[row, 2]


def base64_thumbnail(pixmap: QPixmap, size: QSize) -> str:
    """
    Convert image into format useful for HTML data URIs.

    See https://css-tricks.com/data-uris/

    :param pixmap: image to convert
    :param size: size to scale to
    :return: data in base 64 format
    """

    pixmap = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    # Quality 100 means uncompressed, which is faster.
    pixmap.save(buffer, "PNG", quality=100)
    return bytes(buffer.data().toBase64()).decode()


class TemporalProximityModel(QAbstractTableModel):
    tooltip_image_size = QSize(90, 90)

    def __init__(self, rapidApp, groups: TemporalProximityGroups=None, parent=None) -> None:
        super().__init__(parent)
        self.rapidApp = rapidApp
        self.groups = groups

        self.show_debug = False
        logger = logging.getLogger()
        for handler in logger.handlers:
            # name set in iplogging.setup_main_process_logging()
            if handler.name == 'console':
                self.show_debug = handler.level <= logging.DEBUG

        self.force_show_debug = False  # set to True to always display debug info in Timeline

    def columnCount(self, parent=QModelIndex()) -> int:
        return 3

    def rowCount(self, parent=QModelIndex()) -> int:
        if self.groups:
            return len(self.groups)
        else:
            return 0

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.groups) or row < 0:
            return None

        column = index.column()
        if column < 0 or column > 3:
            return None
        proximity_row = self.groups[row]  # type: ProximityRow

        if role == Qt.DisplayRole:
            invalid_row = self.show_debug and row in self.groups.invalid_rows
            invalid_rows = self.show_debug and len(self.groups.invalid_rows) > 0 or \
                self.force_show_debug
            if column == 0:
                return proximity_row.year, proximity_row.month
            elif column == 1:
                return proximity_row.weekday, proximity_row.day
            else:
                return proximity_row.proximity, proximity_row.new_file, invalid_row, invalid_rows

        elif role == Roles.uids:
            prow = self.groups.row_span_for_column_starts_at_row[(row, 2)]
            uids = self.groups.uids.uids(2)[prow]
            return uids

        elif role == Qt.ToolTipRole:
            thumbnails = self.rapidApp.thumbnailModel.thumbnails

            try:

                if column == 1:
                    uids = self.groups.uids.uids(1)[row]
                    length = self.groups.uids.no_uids((row, 1))
                    date = proximity_row.tooltip_date_col1
                    file_types= self.rapidApp.thumbnailModel.getTypeCountForProximityCell(
                        col1id=self.groups.proximity_view_cell_id_col1[row]
                    )
                elif column == 2:
                    prow = self.groups.row_span_for_column_starts_at_row[(row, 2)]
                    uids = self.groups.uids.uids(2)[prow]
                    length = self.groups.uids.no_uids((prow, 2))
                    date = proximity_row.tooltip_date_col2
                    file_types = self.rapidApp.thumbnailModel.getTypeCountForProximityCell(
                        col2id=self.groups.proximity_view_cell_id_col2[prow]
                    )
                else:
                    assert column == 0
                    uids = self.groups.uids.uids(0)[row]
                    length = self.groups.uids.no_uids((row, 0))
                    date = proximity_row.tooltip_date_col0
                    file_types = self.groups.file_types_in_cell[row, column]

            except KeyError as e:
                logging.exception('Error in Timeline generation')
                self.debugDumpState()
                return None

            pixmap = thumbnails[uids[0]]  # type: QPixmap

            image = base64_thumbnail(pixmap, self.tooltip_image_size)
            html_image1 = '<img src="data:image/png;base64,{}">'.format(image)

            if length == 1:
                center = html_image2 = ''
            else:
                pixmap = thumbnails[uids[-1]]  # type: QPixmap
                image = base64_thumbnail(pixmap, self.tooltip_image_size)
                if length == 2:
                    center = '&nbsp;'
                else:
                    center = '&nbsp;&hellip;&nbsp;'
                html_image2 = '<img src="data:image/png;base64,{}">'.format(image)

            tooltip = '{}<br>{} {} {}<br>{}'.format(
                date, html_image1, center, html_image2, file_types
            )
            return tooltip

    def debugDumpState(self, selected_rows_col1: List[int]=None,
                       selected_rows_col2: List[int]=None) -> None:

        thumbnailModel = self.rapidApp.thumbnailModel
        logging.debug('%r', self.groups)

        # Print rows and values to the debugging output
        if len(self.groups) < 20:
            for row, prow in enumerate(self.groups.rows):
                logging.debug('Row %s', row)
                logging.debug('{} | {} | {}'.format(prow.year, prow.month, prow.day))
                for col in (0, 1, 2):
                    if row in self.groups.uids._uids[col]:
                        uids = self.groups.uids._uids[col][row]
                        files = ', '.join((thumbnailModel.rpd_files[uid].name for uid in uids))
                        logging.debug('Col {}: {}'.format(col, files))

    def updatePreviouslyDownloaded(self, uids: List[bytes]) -> None:
        """
        Examine Timeline data to see if any Timeline rows should have their column 2
        formatting updated to reflect that there are no new files to be downloaded in
        that particular row
        :param uids: list of uids that have been manually marked as previously downloaded
        """

        processed_rows = set()  # type: Set[int]
        rows_to_update = []
        for uid in uids:
            row = self.groups.uid_to_row(uid=uid)
            if row not in processed_rows:
                processed_rows.add(row)
                row_uids = self.groups.row_uids(row)
                logging.debug(
                    'Examining row %s to see if any have not been previously downloaded', row
                )
                if not self.rapidApp.thumbnailModel.anyFileNotPreviouslyDownloaded(uids=row_uids):
                    proximity_row = self.groups[row]  # type: ProximityRow
                    self.groups[row] = proximity_row._replace(new_file=False)
                    rows_to_update.append(row)
                    logging.debug('Row %s will be updated to show it has no new files')

        if rows_to_update:
            for first, last in runs(rows_to_update):
                self.dataChanged.emit(self.index(first, 2), self.index(last, 2))


class TemporalProximityDelegate(QStyledItemDelegate):
    """
    Render table cell for Timeline.

    All cell size calculations are done prior to rendering.

    The table has 3 columns:

     - Col 0: month & year (col will be hidden if all dates are in the current month)
     - Col 1: day e.g. 'Fri 16'
     - Col 2: time(s), e.g. '5:09 AM', or '4:09 - 5:27 PM'
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.darkGray = QColor(DarkGray)
        self.darkerGray = self.darkGray.darker(140)
        # self.darkerGray = QColor(DoubleDarkGray)
        self.midGray = QColor(MediumGray)

        # column 2 cell color is assigned in ProximityDisplayValues

        palette = QGuiApplication.instance().palette()
        self.highlight = palette.highlight().color()
        self.darkerHighlight = self.highlight.darker(110)
        self.highlightText = palette.highlightedText().color()

        self.newFileColor = QColor(CustomColors.color7.value)

        self.dv = None  # type: ProximityDisplayValues

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        row = index.row()
        column = index.column()

        if column == 0:
            # Month and year
            painter.save()

            if option.state & QStyle.State_Selected:
                color = self.highlight
                textColor = self.highlightText
                barColor = self.darkerHighlight
            else:
                color = self.darkGray
                textColor = self.dv.tableColor
                barColor = self.darkerGray
            painter.fillRect(option.rect, color)
            painter.setPen(textColor)

            year, month = index.data()

            month = self.dv.get_month_text(month, year)

            x = option.rect.x()
            y = option.rect.y()

            painter.setFont(self.dv.monthFont)
            painter.setPen(textColor)

            # Set position in the cell
            painter.translate(x, y)
            # Rotate the coming text rendering
            painter.rotate(270.0)

            # Translate positioning to reflect new rotation
            painter.translate(-1 * option.rect.height(), 0)
            rect = QRect(0, 0, option.rect.height(), option.rect.width())

            painter.drawText(rect, Qt.AlignCenter, month)

            painter.setPen(barColor)
            painter.drawLine(1, 0, 1, option.rect.width())

            painter.restore()

        elif column == 1:
            # Day of the month
            painter.save()

            if option.state & QStyle.State_Selected:
                color = self.highlight
                weekdayColor = self.highlightText
                dayColor = self.highlightText
                barColor = self.darkerHighlight
            else:
                color = self.darkGray
                weekdayColor = QColor(221, 221, 221)
                dayColor = QColor(Qt.white)
                barColor = self.darkerGray

            painter.fillRect(option.rect, color)
            weekday, day = index.data()
            weekday = weekday.upper()
            width = option.rect.width()
            height = option.rect.height()

            painter.translate(option.rect.x(), option.rect.y())
            weekday_rect_bottom = int(
                height / 2 - self.dv.max_col1_text_height * self.dv.day_proportion
            ) + self.dv.max_weekday_height
            weekdayRect = QRect(0, 0, width, weekday_rect_bottom)
            day_rect_top = weekday_rect_bottom + self.dv.col1_center_space
            dayRect = QRect(0, day_rect_top, width, height - day_rect_top)

            painter.setFont(self.dv.weekdayFont)
            painter.setPen(weekdayColor)
            painter.drawText(weekdayRect, Qt.AlignHCenter | Qt.AlignBottom, weekday)
            painter.setFont(self.dv.dayFont)
            painter.setPen(dayColor)
            painter.drawText(dayRect, Qt.AlignHCenter | Qt.AlignTop, day)

            if row in self.dv.c1_end_of_month:
                painter.setPen(barColor)
                painter.drawLine(
                    0, option.rect.height() - 1, option.rect.width(), option.rect.height() - 1
                )

            painter.restore()

        elif column == 2:
            # Time during the day
            text, new_file, invalid_row, invalid_rows = index.data()

            painter.save()

            if invalid_row:
                color = self.darkGray
                textColor = QColor(Qt.white)
            elif option.state & QStyle.State_Selected:
                color = self.highlight
                # TODO take into account dark themes
                if new_file:
                    textColor = self.highlightText
                else:
                    textColor = self.darkGray
            else:
                color = self.dv.tableColor
                if new_file:
                    textColor = QColor(Qt.white)
                else:
                    textColor = self.darkGray

            painter.fillRect(option.rect, color)

            align = self.dv.c2_alignment.get(row)

            if new_file and self.dv.col2_new_file_dot:
                # Draw a small circle beside the date (currently unused)
                painter.setPen(self.newFileColor)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setBrush(self.newFileColor)
                rect = QRectF(
                    option.rect.x(),
                    option.rect.y(),
                    self.dv.col2_new_file_dot_size,
                    self.dv.col2_new_file_dot_size
                )
                if align is None:
                    height = option.rect.height() / 2 -self.dv.col2_new_file_dot_radius - \
                             self.dv.col2_font_descent_adjust
                    rect.translate(self.dv.col2_new_file_dot_left_margin, height)
                elif align == Align.bottom:
                    height = (
                        option.rect.height() - self.dv.col2_font_height_half -
                        self.dv.col2_font_descent_adjust - self.dv.col2_new_file_dot_size
                    )
                    rect.translate(self.dv.col2_new_file_dot_left_margin, height)
                else:
                    height = (
                        self.dv.col2_font_height_half - self.dv.col2_font_descent_adjust
                    )
                    rect.translate(self.dv.col2_new_file_dot_left_margin, height)
                painter.drawEllipse(rect)

            rect = QRect(option.rect)
            rect.translate(self.dv.col2_text_left_margin, 0)

            painter.setPen(textColor)

            if invalid_rows:
                # Render the row
                invalidRightRect = QRect(option.rect)
                invalidRightRect.translate(-2, 1)
                painter.setFont(self.dv.invalidRowFont)
                painter.drawText(invalidRightRect, Qt.AlignRight | Qt.AlignTop, str(row))
                if align != Align.top and self.dv.invalidRowHeightMin < option.rect.height():
                    invalidLeftRect = QRect(option.rect)
                    invalidLeftRect.translate(1, 1)
                    painter.drawText(invalidLeftRect, Qt.AlignLeft | Qt.AlignTop, 'Debug mode')

            painter.setFont(self.dv.proximityFont)

            if align is None:
                painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)
            elif align == Align.bottom:
                rect.setHeight(rect.height() - self.dv.col2_v_padding_half)
                painter.drawText(rect, Qt.AlignLeft | Qt.AlignBottom, text)
            else:
                rect.adjust(0, self.dv.col2_v_padding_half, 0, 0)
                painter.drawText(rect, Qt.AlignLeft | Qt.AlignTop, text)

            if row in self.dv.c2_end_of_day:
                if option.state & QStyle.State_Selected:
                    painter.setPen(self.darkerHighlight)
                else:
                    painter.setPen(self.dv.tableColorDarker)
                painter.translate(option.rect.x(), option.rect.y())
                painter.drawLine(
                    0, option.rect.height() - 1, self.dv.col_widths[2], option.rect.height() - 1
                )

            painter.restore()
        else:
            super().paint(painter, option, index)


class TemporalProximityView(QTableView):

    proximitySelectionHasChanged = pyqtSignal()

    def __init__(self, temporalProximityWidget: 'TemporalProximity', rapidApp) -> None:
        super().__init__()
        self.rapidApp = rapidApp
        self.temporalProximityWidget = temporalProximityWidget
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(False)
        # Calling code should set this value to something sensible
        self.setMinimumWidth(200)
        self.horizontalHeader().setStretchLastSection(True)
        self.setWordWrap(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setShowGrid(False)

    def _updateSelectionRowChildColumn2(self, row: int, parent_column: int,
                                        model: TemporalProximityModel) -> None:
        """
        Select cells in column 2, based on selections in column 0 or 1.

        :param row: the row of the cell that has been selected
        :param parent_column: the column of the cell that has been
         selected
        :param model: the model the view operates on
        """

        for parent_row in range(row, row + self.rowSpan(row, parent_column)):
            start_row = model.groups.row_span_for_column_starts_at_row[(parent_row, 2)]
            row_span = self.rowSpan(start_row, 2)

            do_selection = False
            if row_span > 1:
                all_selected = True
                for r in range(start_row, start_row + row_span):
                    if not self.selectionModel().isSelected(model.index(r, 1)):
                        all_selected = False
                        break
                if all_selected:
                    do_selection = True
            else:
                do_selection = True

            if do_selection:
                self.selectionModel().select(model.index(start_row, 2), QItemSelectionModel.Select)
                model.dataChanged.emit(model.index(start_row, 2), model.index(start_row, 2))

    def _updateSelectionRowChildColumn1(self, row: int, model: TemporalProximityModel) -> None:
        """
        Select cells in column 1, based on selections in column 0.

        :param row: the row of the cell that has been selected
        :param model: the model the view operates on
        """

        for r in range(row, row + self.rowSpan(row, 0)):
            self.selectionModel().select(
                model.index(r, 1), QItemSelectionModel.Select
            )
        model.dataChanged.emit(model.index(row, 1), model.index(r, 1))

    def _updateSelectionRowParent(self, row: int,
                                  parent_column: int,
                                  start_column: int,
                                  examined: set,
                                  model: TemporalProximityModel) -> None:
        """
        Select cells in column 0 or 1, based on selections in column 2.

        :param row: the row of the cell that has been selected
        :param parent_column: the column in which to select cells
        :param start_column: the column of the cell that has been
         selected
        :param examined: cells that have already been analyzed to see
         if they should be selected or not
        :param model: the model the view operates on
        """
        start_row = model.groups.row_span_for_column_starts_at_row[(row, parent_column)]
        if (start_row, parent_column) not in examined:
            all_selected = True
            for r in range(start_row, start_row + self.rowSpan(row, parent_column)):
                if not self.selectionModel().isSelected(model.index(r, start_column)):
                    all_selected = False
                    break
            if all_selected:
                i = model.index(start_row, parent_column)
                self.selectionModel().select(i, QItemSelectionModel.Select)
                model.dataChanged.emit(i, i)
            examined.add((start_row, parent_column))

    def updateSelection(self) -> None:
        """
        Modify user selection to include extra columns.

        When the user is selecting table cells, need to mimic the
        behavior of
        setSelectionBehavior(QAbstractItemView.SelectRows)
        However in our case we need to select multiple rows, depending
        on the row spans in columns 0, 1 and 2. Column 2 is a special
        case.
        """

        # auto_scroll = self.temporalProximityWidget.prefs.auto_scroll
        # if auto_scroll:
        #     self.temporalProximityWidget.setTimelineThumbnailAutoScroll(False)

        self.selectionModel().blockSignals(True)

        model = self.model()  # type: TemporalProximityModel
        examined = set()

        for i in self.selectedIndexes():
            row = i.row()
            column = i.column()
            if column == 0:
                examined.add((row, column))
                self._updateSelectionRowChildColumn1(row, model)
                examined.add((row, 1))
                self._updateSelectionRowChildColumn2(row, 0, model)
                examined.add((row, 2))
            if column == 1:
                examined.add((row, column))
                self._updateSelectionRowChildColumn2(row, 1, model)
                self._updateSelectionRowParent(row, 0, 1, examined, model)
                examined.add((row, 2))
            if column == 2:
                for r in range(row, row + self.rowSpan(row, 2)):
                    for parent_column in (1, 0):
                        self._updateSelectionRowParent(r, parent_column, 2, examined, model)

        self.selectionModel().blockSignals(False)

        # if auto_scroll:
        #     self.temporalProximityWidget.setTimelineThumbnailAutoScroll(True)

    @pyqtSlot(QMouseEvent)
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        Checks to see if Timeline selection should be cleared.

        Should be cleared if the cell clicked in already represents
        a selection that cannot be expanded or made smaller with the
        same click.

        A click outside the selection represents a new selection,
        should proceed.

        A click inside a selection, but one that creates a new, smaller
        selection, should also proceed.

        :param event: the mouse click event
        """

        do_selection = True
        do_selection_confirmed = False
        index = self.indexAt(event.pos())  # type: QModelIndex
        if index in self.selectedIndexes():
            clicked_column = index.column()
            clicked_row = index.row()
            row_span = self.rowSpan(clicked_row, clicked_column)
            for i in self.selectedIndexes():
                column = i.column()
                row = i.row()
                # Is any selected column to the left of clicked column?
                if column < clicked_column:
                    # Is the row outside the span of the clicked row?
                    if (row < clicked_row or
                            row + self.rowSpan(row, column) > clicked_row + row_span):
                        do_selection_confirmed = True
                        break
                # Is this the only selected row in the column selected?
                if ((row < clicked_row or row >= clicked_row + row_span) and column ==
                        clicked_column):
                    do_selection_confirmed = True
                    break

            if not do_selection_confirmed:
                self.clearSelection()
                self.rapidApp.proximityButton.setHighlighted(False)
                do_selection = False
                thumbnailView = self.rapidApp.thumbnailView
                model = self.model()
                uids = model.data(index, Roles.uids)
                thumbnailView.scrollToUids(uids=uids)

        if do_selection:
            self.temporalProximityWidget.block_update_device_display = True
            super().mousePressEvent(event)


    @pyqtSlot(QMouseEvent)
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.temporalProximityWidget.block_update_device_display = False
        self.proximitySelectionHasChanged.emit()
        super().mouseReleaseEvent(event)

    @pyqtSlot(int)
    def scrollThumbnails(self, value) -> None:
        index = self.indexAt(QPoint(200, 0))  # type: QModelIndex
        if index.isValid():
            if self.selectedIndexes():
                # It's now possible to scroll the Timeline and there will be
                # no matching thumbnails to which to scroll to in the display,
                # because they are not being displayed. Hence this check:
                 if not index in self.selectedIndexes():
                     return
            thumbnailView = self.rapidApp.thumbnailView
            thumbnailView.setScrollTogether(False)
            model = self.model()
            uids = model.data(index, Roles.uids)
            thumbnailView.scrollToUids(uids=uids)
            thumbnailView.setScrollTogether(True)


class TemporalValuePicker(QWidget):
    """
    Simple composite widget of QSlider and QLabel
    """

    # Emits number of minutes
    valueChanged =  pyqtSignal(int)

    def __init__(self, minutes: int, parent=None) -> None:
        super().__init__(parent)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setToolTip(
            _(
                "The time elapsed between consecutive photos and videos that is used to build the "
                "Timeline"
            )
        )
        self.slider.setMaximum(len(proximity_time_steps) - 1)
        self.slider.setValue(proximity_time_steps.index(minutes))

        self.display = QLabel()
        font = QFont()
        font.setPointSize(font.pointSize() - 2)
        self.display.setFont(font)
        self.display.setAlignment(Qt.AlignCenter)

        # Determine maximum width of display label
        width = 0
        labelMetrics = QFontMetrics(QFont())
        for m in range(len(proximity_time_steps)):
            boundingRect = labelMetrics.boundingRect(self.displayString(m))  # type: QRect
            width = max(width, boundingRect.width())

        self.display.setFixedWidth(width + 6)

        self.slider.valueChanged.connect(self.updateDisplay)
        self.slider.sliderPressed.connect(self.sliderPressed)
        self.slider.sliderReleased.connect(self.sliderReleased)

        self.display.setText(self.displayString(self.slider.value()))

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(QFontMetrics(font).height() // 6)
        self.setLayout(layout)
        layout.addWidget(self.slider)
        layout.addWidget(self.display)

    @pyqtSlot()
    def sliderPressed(self):
        self.pressed_value = self.slider.value()

    @pyqtSlot()
    def sliderReleased(self):
        if self.pressed_value != self.slider.value():
            self.valueChanged.emit(proximity_time_steps[self.slider.value()])

    @pyqtSlot(int)
    def updateDisplay(self, value: int) -> None:
        self.display.setText(self.displayString(value))
        if not self.slider.isSliderDown():
            self.valueChanged.emit(proximity_time_steps[value])

    def displayString(self, index: int) -> str:
        minutes = proximity_time_steps[index]
        if minutes < 60:
            # Translators: e.g. "45m", which is short for 45 minutes.
            # Replace the very last character (after the d) with the correct
            # localized value, keeping everything else. In other words, change
            # only the m character.
            return _("%(minutes)dm") % dict(minutes=minutes)
        elif minutes == 90:
            # Translators: i.e. "1.5h", which is short for 1.5 hours.
            # Replace the entire string with the correct localized value
            return _('1.5h')
        else:
            # Translators: e.g. "5h", which is short for 5 hours.
            # Replace the very last character (after the d) with the correct localized value,
            # keeping everything else. In other words, change only the h character.
            return _('%(hours)dh') % dict(hours=minutes // 60)


class TemporalProximity(QWidget):
    """
    Displays Timeline and tracks its state.

    Main widget to display and control Timeline.
    """

    proximitySelectionHasChanged = pyqtSignal()

    def __init__(self, rapidApp,
                 prefs: Preferences,
                 parent=None) -> None:
        """
        :param rapidApp: main application window
        :type rapidApp: RapidWindow
        :param prefs: program & user preferences
        :param parent: parent widget
        """

        super().__init__(parent)

        self.rapidApp = rapidApp
        self.thumbnailModel = rapidApp.thumbnailModel
        self.prefs = prefs

        self.block_update_device_display = False

        self.state = TemporalProximityState.empty

        self.uids_manually_set_previously_downloaded = []  # type: List[bytes]

        self.temporalProximityView = TemporalProximityView(self, rapidApp=rapidApp)
        self.temporalProximityModel = TemporalProximityModel(rapidApp=rapidApp)
        self.temporalProximityView.setModel(self.temporalProximityModel)
        self.temporalProximityDelegate = TemporalProximityDelegate()
        self.temporalProximityView.setItemDelegate(self.temporalProximityDelegate)
        self.temporalProximityView.selectionModel().selectionChanged.connect(
            self.proximitySelectionChanged
        )

        self.temporalProximityView.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Expanding
        )

        self.temporalValuePicker = TemporalValuePicker(self.prefs.get_proximity())
        self.temporalValuePicker.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        description = _(
            'The Timeline groups photos and videos based on how much time elapsed '
            'between consecutive shots. Use it to identify photos and videos taken at '
            'different periods in a single day or over consecutive days.'
        )
        adjust = _(
            'Use the slider (below) to adjust the time elapsed between consecutive shots '
            'that is used to build the Timeline.'
        )
        generation_pending = _("Timeline build pending...")
        generating = _("Timeline is building...")
        ctime_vs_mtime = _(
            "The Timeline needs to be rebuilt because the file "
            "modification time does not match the time a shot was taken for one or more shots"
            ".<br><br>The Timeline shows when shots were taken. The time a shot was taken is "
            "found in a photo or video's metadata. "
            "Reading the metadata is time consuming, so Rapid Photo Downloader avoids reading the "
            "metadata while scanning files. Instead it uses the time the file was last modified "
            "as a proxy for when the shot was taken. The time a shot was taken is confirmed when "
            "generating thumbnails or downloading, which is when the metadata is read."
        )

        description = '<i>{}</i>'.format(description)
        generation_pending = '<i>{}</i>'.format(generation_pending)
        generating = '<i>{}</i>'.format(generating)
        adjust = '<i>{}</i>'.format(adjust)
        ctime_vs_mtime = '<i>{}</i>'.format(ctime_vs_mtime)

        palette = QPalette()
        palette.setColor(QPalette.Window, palette.color(palette.Base))

        # TODO assign this value from somewhere else - rapidApp.standard_spacing not yet defined
        margin = 6

        self.description = QLabel(description)
        self.adjust = QLabel(adjust)
        self.generating = QLabel(generating)
        self.generationPending = QLabel(generation_pending)
        self.ctime_vs_mtime = QLabel(ctime_vs_mtime)

        self.explanation = QWidget()
        layout = QVBoxLayout()
        border_width = QSplitter().lineWidth()
        layout.setContentsMargins(border_width, border_width, border_width, border_width)
        layout.setSpacing(0)
        self.explanation.setLayout(layout)
        layout.addWidget(self.description)
        layout.addWidget(self.adjust)

        for label in (self.description, self.generationPending, self.generating, self.adjust,
                      self.ctime_vs_mtime):
            label.setMargin(margin)
            label.setWordWrap(True)
            label.setAutoFillBackground(True)
            label.setPalette(palette)

        for label in (self.description, self.generationPending, self.generating,
                      self.ctime_vs_mtime):
            label.setAlignment(Qt.AlignTop)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        self.adjust.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)

        self.stackedWidget = QStackedWidget()

        for label in (self.explanation, self.generationPending, self.generating,
                      self.ctime_vs_mtime):
            scrollArea = QScrollArea()
            scrollArea.setWidgetResizable(True)
            scrollArea.setWidget(label)
            self.stackedWidget.addWidget(scrollArea)

        self.stackedWidget.addWidget(self.temporalProximityView)

        self.stack_index_for_state = {
            TemporalProximityState.empty: 0,
            TemporalProximityState.pending: 1,
            TemporalProximityState.generating: 2,
            TemporalProximityState.regenerate: 2,
            TemporalProximityState.ctime_rebuild: 3,
            TemporalProximityState.ctime_rebuild_proceed: 3,
            TemporalProximityState.generated: 4
        }

        self.autoScrollButton = QToolButton(self)
        icon = QIcon(':/icons/link.svg')
        self.autoScrollButton.setIcon(icon)
        # self.autoScrollButton.setIconSize(QSize(16, 16))
        self.autoScrollButton.setAutoRaise(True)
        self.autoScrollButton.setCheckable(True)
        self.autoScrollButton.setToolTip(
            _('Toggle synchronizing Timeline and thumbnail scrolling (Ctrl-T)')
        )
        self.autoScrollButton.setChecked(not self.prefs.auto_scroll)
        self.autoScrollAct = QAction(
            '', self, shortcut="Ctrl+T",
            triggered=self.autoScrollActed, icon=icon
        )
        self.autoScrollButton.addAction(self.autoScrollAct)
        style = "QToolButton {padding: 2px;} QToolButton::menu-indicator {image: none;}"
        self.autoScrollButton.setStyleSheet(style)
        self.autoScrollButton.clicked.connect(self.autoScrollClicked)

        pickerLayout = QHBoxLayout()
        pickerLayout.setSpacing(0)
        pickerLayout.addWidget(self.temporalValuePicker)
        pickerLayout.addWidget(self.autoScrollButton)

        layout.addWidget(self.stackedWidget)
        layout.addLayout(pickerLayout)

        self.stackedWidget.setCurrentIndex(0)

        self.temporalValuePicker.valueChanged.connect(self.temporalValueChanged)
        if self.prefs.auto_scroll:
            self.setTimelineThumbnailAutoScroll(self.prefs.auto_scroll)

        self.suppress_auto_scroll_after_timeline_select = False

    @pyqtSlot(QItemSelection, QItemSelection)
    def proximitySelectionChanged(self, current: QItemSelection, previous: QItemSelection) -> None:
        """
        Respond to user selections in Temporal Proximity Table.

        User can select / deselect individual cells. Need to:
        1. Automatically update selection to include parent or child
           cells in some cases
        2. Filter display of thumbnails
        """

        self.temporalProximityView.updateSelection()

        groups = self.temporalProximityModel.groups

        selected_rows_col2 = [
            i.row() for i in self.temporalProximityView.selectedIndexes() if i.column() == 2
        ]
        selected_rows_col1 = [
            i.row() for i in self.temporalProximityView.selectedIndexes()
            if i.column() == 1 and groups.row_span_for_column_starts_at_row[(i.row(), 2)]
               not in selected_rows_col2
        ]

        try:
            selected_col1 = [groups.proximity_view_cell_id_col1[row] for row in selected_rows_col1]
            selected_col2 = [groups.proximity_view_cell_id_col2[row] for row in selected_rows_col2]
        except KeyError as e:
            logging.exception('Error in Timeline generation')
            self.temporalProximityModel.debugDumpState(selected_rows_col1, selected_rows_col2)
            return

        # Filter display of thumbnails, or reset the filter if lists are empty
        self.thumbnailModel.setProximityGroupFilter(selected_col1, selected_col2)

        self.rapidApp.proximityButton.setHighlighted(True)

        if not self.block_update_device_display:
            self.proximitySelectionHasChanged.emit()

        self.suppress_auto_scroll_after_timeline_select = True

    def clearThumbnailDisplayFilter(self):
        self.thumbnailModel.setProximityGroupFilter([],[])
        self.rapidApp.proximityButton.setHighlighted(False)

    def setState(self, state: TemporalProximityState) -> None:
        """
        Set the state of the temporal proximity view, updating the displayed message
        :param state: the new state
        """

        if state == self.state:
            return

        if state == TemporalProximityState.ctime_rebuild_proceed:
            if self.state == TemporalProximityState.ctime_rebuild:
                self.state = TemporalProximityState.ctime_rebuild_proceed
                logging.debug("Timeline is ready to be rebuilt after ctime change")
                return
            else:
                logging.error(
                    "Unexpected request to set Timeline state to %s because current state is %s",
                    state.name, self.state.name
                )
        elif self.state == TemporalProximityState.ctime_rebuild and state != \
                TemporalProximityState.empty:
            logging.debug(
                "Ignoring request to set timeline state to %s because current state is ctime "
                "rebuild", state.name
            )
            return

        logging.debug("Updating Timeline state from %s to %s", self.state.name, state.name)

        self.stackedWidget.setCurrentIndex(self.stack_index_for_state[state])
        self.clearThumbnailDisplayFilter()
        self.state = state

    def setGroups(self, proximity_groups: TemporalProximityGroups) -> bool:
        """
        Display the Timeline using data from the generated proximity_groups
        :param proximity_groups: Timeline content and formatting hints
        :return: True if Timeline was updated, False if not updated due to
         current state
        """

        if self.state == TemporalProximityState.regenerate:
            self.rapidApp.generateTemporalProximityTableData(
                reason="a change was made while it was already generating"
            )
            return False
        if self.state == TemporalProximityState.ctime_rebuild:
            return False

        self.temporalProximityModel.groups = proximity_groups

        depth = proximity_groups.depth()
        self.temporalProximityDelegate.depth = depth
        if depth in (0, 1):
            self.temporalProximityView.hideColumn(0)
        else:
            self.temporalProximityView.showColumn(0)

        self.temporalProximityView.clearSpans()
        self.temporalProximityDelegate.row_span_for_column_starts_at_row = \
            proximity_groups.row_span_for_column_starts_at_row
        self.temporalProximityDelegate.dv = proximity_groups.display_values
        self.temporalProximityDelegate.dv.assign_fonts()

        for column, row, row_span in proximity_groups.spans:
            self.temporalProximityView.setSpan(row, column, row_span, 1)

        self.temporalProximityModel.endResetModel()

        for idx, height in enumerate(proximity_groups.display_values.row_heights):
            self.temporalProximityView.setRowHeight(idx, height)
        for idx, width in enumerate(proximity_groups.display_values.col_widths):
            self.temporalProximityView.setColumnWidth(idx, width)

        # Set the minimum width for the timeline to match the content
        # Width of each column
        if depth in (0, 1):
            min_width = sum(proximity_groups.display_values.col_widths[1:])
        else:
            min_width = sum(proximity_groups.display_values.col_widths)
        # Width of each scrollbar
        scrollbar_width = self.style().pixelMetric(QStyle.PM_ScrollBarExtent)
        # Width of frame - without it, the tableview will still be too small
        frame_width = QSplitter().lineWidth() * 2
        self.temporalProximityView.setMinimumWidth(min_width + scrollbar_width + frame_width)

        self.setState(TemporalProximityState.generated)

        # Has the user manually set any files as previously downloaded while the Timeline was
        # generating?
        if self.uids_manually_set_previously_downloaded:
            self.temporalProximityModel.updatePreviouslyDownloaded(
                uids=self.uids_manually_set_previously_downloaded
            )
            self.uids_manually_set_previously_downloaded = []

        return True

    @pyqtSlot(int)
    def temporalValueChanged(self, minutes: int) -> None:
        self.prefs.set_proximity(minutes=minutes)
        if self.state == TemporalProximityState.generated:
            self.setState(TemporalProximityState.generating)
            self.rapidApp.generateTemporalProximityTableData(
                reason="the duration between consecutive shots has changed")
        elif self.state == TemporalProximityState.generating:
            self.state = TemporalProximityState.regenerate

    def previouslyDownloadedManuallySet(self, uids: List[bytes]) -> None:
        """
        Possibly update the formatting of the Timeline to reflect the user
        manually setting files to have been previously downloaded
        """

        logging.debug(
            "Updating Timeline to reflect %s files manually set as previously downloaded",
            len(uids)
        )
        if self.state != TemporalProximityState.generated:
            self.uids_manually_set_previously_downloaded.extend(uids)
        else:
            self.temporalProximityModel.updatePreviouslyDownloaded(uids=uids)

    def scrollToUid(self, uid: bytes) -> None:
        """
        Scroll to this uid in the Timeline.

        :param uid: uid to scroll to
        """

        if self.state == TemporalProximityState.generated:
            if self.suppress_auto_scroll_after_timeline_select:
                self.suppress_auto_scroll_after_timeline_select = False
            else:
                view = self.temporalProximityView
                model = self.temporalProximityModel
                row = model.groups.uid_to_row(uid=uid)
                index = model.index(row, 2)
                view.scrollTo(index, QAbstractItemView.PositionAtTop)

    def setTimelineThumbnailAutoScroll(self, on: bool) -> None:
        """
        Turn on or off synchronized scrolling between thumbnails and Timeline
        :param on: whether to turn on or off
        """

        self.setScrollTogether(on)
        self.rapidApp.thumbnailView.setScrollTogether(on)

    def setScrollTogether(self, on: bool) -> None:
        """
        Turn on or off the linking of scrolling the Timeline with the Thumbnail display
        :param on: whether to turn on or off
        """

        view = self.temporalProximityView
        if on:
            view.verticalScrollBar().valueChanged.connect(view.scrollThumbnails)
        else:
            view.verticalScrollBar().valueChanged.disconnect(view.scrollThumbnails)

    @pyqtSlot(bool)
    def autoScrollClicked(self, checked: bool) -> None:
        self.prefs.auto_scroll = not checked
        self.setTimelineThumbnailAutoScroll(not checked)

    @pyqtSlot(bool)
    def autoScrollActed(self, on: bool) -> None:
        self.autoScrollButton.animateClick()
