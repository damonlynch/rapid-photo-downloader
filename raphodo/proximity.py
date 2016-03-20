# Copyright (C) 2015-2016 Damon Lynch <damonlynch@gmail.com>

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
__copyright__ = "Copyright 2015-2016, Damon Lynch"

from collections import (namedtuple, defaultdict, deque, Counter)
import locale
from datetime import datetime
import logging
import pickle
import math
from typing import Dict, List, Tuple, Set, Optional

import arrow.arrow
from arrow.arrow import Arrow

from gettext import gettext as _
from PyQt5.QtCore import (QAbstractTableModel, QModelIndex, Qt, QSize,
                          QRect, QItemSelection, QItemSelectionModel, QBuffer, QIODevice,
                          pyqtSignal, pyqtSlot, QRectF)
from PyQt5.QtWidgets import (QTableView, QStyledItemDelegate, QSlider, QLabel, QVBoxLayout,
                             QStyleOptionViewItem, QStyle, QAbstractItemView, QWidget, QHBoxLayout,
                             QSizePolicy, QSplitter, QStyleOptionFrame)
from PyQt5.QtGui import (QPainter, QFontMetrics, QFont, QColor, QGuiApplication, QPixmap,
                         QPalette, QMouseEvent)

from raphodo.viewutils import SortedListItem
from raphodo.constants import (FileType, Align, proximity_time_steps, TemporalProximityState,
                               FileExtension, fileTypeColor, CustomColors)
from raphodo.rpdfile import FileTypeCounter
from raphodo.preferences import Preferences

ProximityRow = namedtuple('ProximityRow', 'year, month, weekday, day, proximity, new_file')

UniqueIdTime = namedtuple('UniqueIdTime', 'modification_time, arrowtime, unqiue_id')


def locale_time(t: datetime) -> str:
    """
    Attempt to localize the time without displaying seconds
    Adapted from http://stackoverflow.com/questions/2507726/how-to-display
    -locale-sensitive-time-format-without-seconds-in-python
    :param t: time in datetime format
    :return: time in format like "12:08 AM", or locale equivalent
    """

    replacement_fmts = [
        ('.%S', ''),
        (':%S', ''),
        (',%S', ''),
        (':%OS', ''),
        ('ཀསར་ཆ%S', ''),
        (' %S초', ''),
        ('%S秒', ''),
        ('%r', '%I:%M'),
        ('%t', '%H:%M'),
        ('%T', '%H:%M')
    ]

    t_fmt = locale.nl_langinfo(locale.T_FMT_AMPM)

    for fmt in replacement_fmts:
        new_t_fmt = t_fmt.replace(*fmt)
        if new_t_fmt != t_fmt:
            return t.strftime(new_t_fmt)
    return t.strftime(t_fmt)


AM = datetime(2015, 11, 3).strftime('%p')
PM = datetime(2015, 11, 3, 13).strftime('%p')


def humanize_time_span(start: Arrow, end: Arrow,
                       strip_leading_zero_from_time: bool=True,
                       insert_cr_on_long_line: bool=False) -> str:
    r"""
    Make timess and time spans human readable.

    :param start: start time
    :param end: end time
    :param strip_leading_zero_from_time: strip all leading zeros
    :param insert_cr_on_long_line: insert a carriage return on long
     lines
    :return: time span to be read by humans

    >>> locale.setlocale(locale.LC_ALL, ('en_US', 'utf-8'))
    'en_US.UTF-8'
    >>> start = arrow.Arrow(2015,11,3,9)
    >>> end = start
    >>> print(humanize_time_span(start, end))
    9:00 AM
    >>> print(humanize_time_span(start, end, False))
    09:00 AM
    >>> start = arrow.Arrow(2015,11,3,9,1,23)
    >>> end = arrow.Arrow(2015,11,3,9,1,24)
    >>> print(humanize_time_span(start, end))
    9:01 AM
    >>> start = arrow.Arrow(2015,11,3,9)
    >>> end = arrow.Arrow(2015,11,3,10)
    >>> print(humanize_time_span(start, end))
    9:00 - 10:00 AM
    >>> start = arrow.Arrow(2015,11,3,9)
    >>> end = arrow.Arrow(2015,11,3,13)
    >>> print(humanize_time_span(start, end))
    9:00 AM - 1:00 PM
    >>> start = arrow.Arrow(2015,11,3,12)
    >>> print(humanize_time_span(start, end))
    12:00 - 1:00 PM
    >>> start = arrow.Arrow(2015,11,3,12, 59)
    >>> print(humanize_time_span(start, end))
    12:59 - 1:00 PM
    >>> start = arrow.Arrow(2015,10,31,11,55)
    >>> end = arrow.Arrow(2015,11,2,15,15)
    >>> print(humanize_time_span(start, end))
    Oct 31, 11:55 AM - Nov 2, 3:15 PM
    >>> start = arrow.Arrow(2014,10,31,11,55)
    >>> print(humanize_time_span(start, end))
    Oct 31 2014, 11:55 AM - Nov 2 2015, 3:15 PM
    >>> print(humanize_time_span(start, end, False))
    Oct 31 2014, 11:55 AM - Nov 2 2015, 03:15 PM
    >>> print(humanize_time_span(start, end, False, True))
    Oct 31 2014, 11:55 AM -
    Nov 2 2015, 03:15 PM
    """

    def strip_zero(t: str, strip_zero) -> str:
        if not strip_zero:
            return t
        return t.lstrip('0')

    def strip_ampm(t: str) -> str:
        return t.replace(AM, '').replace(PM, '').strip()

    strip = strip_leading_zero_from_time

    if start.floor('minute') == end.floor('minute'):
        return strip_zero(locale_time(start.datetime), strip)

    if start.floor('day') == end.floor('day'):
        # both dates are on the same day
        start_time = strip_zero(locale_time(start.datetime), strip)
        end_time = strip_zero(locale_time(end.datetime), strip)

        if (start.hour < 12 and end.hour < 12) or (start.hour >= 12 and end.hour >= 12):
            # both dates are in the same meridiem
            start_time = strip_ampm(start_time)

        # Translators: for example 9:00 AM - 3:55 PM
        return _('%(starttime)s - %(endtime)s') % {'starttime': start_time, 'endtime': end_time}

    # Translators: for example Nov 3 or Dec 31
    start_date = _('%(month)s %(numeric_day)s') % {
        'month': start.datetime.strftime('%b'),
        'numeric_day': start.format('D')}
    end_date = _('%(month)s %(numeric_day)s') % {
        'month': end.datetime.strftime('%b'),
        'numeric_day': end.format('D')}

    if start.floor('year') != end.floor('year'):
        # Translators: for example Nov 3 2015
        start_date = _('%(date)s %(year)s') % {'date': start_date, 'year': start.year}
        end_date = _('%(date)s %(year)s') % {'date': end_date, 'year': end.year}

    # Translators: for example, Nov 3, 12:15 PM
    start_datetime = _('%(date)s, %(time)s') % {
        'date': start_date, 'time': strip_zero(locale_time(start.datetime), strip)}
    end_datetime = _('%(date)s, %(time)s') % {
        'date': end_date, 'time': strip_zero(locale_time(end.datetime), strip)}

    if not insert_cr_on_long_line:
        # Translators: for example, Nov 3, 12:15 PM - Nov 4, 1:00 AM
        return _('%(earlier_time)s - %(later_time)s') % {
            'earlier_time': start_datetime, 'later_time': end_datetime}
    else:
        # Translators, for example:
        # Nov 3 2012, 12:15 PM -
        # Nov 4 2012, 1:00 AM
        # (please keep the line break signified by \n)
        return _('%(earlier_time)s -\n%(later_time)s') % {
            'earlier_time': start_datetime, 'later_time': end_datetime}

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

class ProximityDisplayValues:
    """
    Temporal Proximity cell sizes.

    Calculated in different process to thta of main window.
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
        self.col2_new_file_dot_size = 4
        self.col2_new_file_dot_radius = self.col2_new_file_dot_size / 2
        self.col2_font_descent_adjust = self.proximityMetrics.descent() / 3
        self.col2_font_height_half = self.proximityMetrics.height() / 2
        self.col2_new_file_dot_left_margin = 6
        self.col2_text_left_margin = (self.col2_new_file_dot_left_margin * 2 +
                                      self.col2_new_file_dot_size)
        self.col2_right_margin = 10
        self.col2_v_padding = 6
        self.col2_v_padding_half = 3

    def assign_fonts(self) -> None:
        self.proximityFont = proximityFont()
        self.proximityMetrics = QFontMetrics(self.proximityFont)
        mf = monthFont()
        self.monthFont = mf.font
        self.month_kerning = mf.kerning
        self.monthMetrics = QFontMetrics(self.monthFont)
        self.weekdayFont = weekdayFont()
        self.dayFont = dayFont()

    def prepare_for_pickle(self) -> None:
        self.proximityFont = self.proximityMetrics = None
        self.monthFont = self.monthMetrics = None
        self.weekdayFont = None
        self.dayFont = None

    def get_month_size(self, month: str) -> QSize:
        boundingRect = self.monthMetrics.boundingRect(month)  # type: QRect
        height = boundingRect.height()
        width = int(boundingRect.width() * self.month_kerning)
        size = QSize(width, height)
        return size

    def get_month_text(self, month, year) -> str:
        if self.depth == 3:
            return _('%(month)s  %(year)s') % {'month': month.upper(), 'year': year}
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
        self.max_col1_text_height = weekday_height + day_height + \
                                    self.col1_center_space
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
        size = QSize(width  + self.col2_text_left_margin + self.col2_right_margin,
                     height + self.col2_v_padding)
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
        for idx, row in enumerate(rows):
            if next_span_start_c0 == idx:
                c0_size = self.column0Size(row.year, row.month)
                self.col0_sizes[idx] = (c0_size.width(), c0_size.height())
                c0_children = []
                sizes.append((c0_size, c0_children))
                c0_span = spans_dict.get((idx, 0), 1)
                next_span_start_c0 = idx + c0_span
                self.c2_end_of_month.add(idx + c0_span - 1)
            if next_span_start_c1 == idx:
                c1_children = []
                c0_children.append(c1_children)
                c1_span = spans_dict.get((idx, 1), 1)
                next_span_start_c1 = idx + c1_span

                if c1_span > 1:
                    self.c2_alignment[idx] = Align.bottom
                    if spans_dict.get((idx + c1_span - 1, 2)) is None:
                        self.c2_alignment[idx + c1_span - 1] = Align.top

                self.c2_end_of_day.add(idx + c1_span - 1)

            minimal_col2_size = self.get_proximity_size(row.proximity)
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

    def assign_color(self, dominant_file_type: FileExtension) -> None:
        self.tableColor = fileTypeColor(dominant_file_type)
        self.tableColorDarker = self.tableColor.darker(107)

class TemporalProximityGroups:
    # @profile
    def __init__(self, thumbnail_rows: List[SortedListItem],
                 thumbnail_types: List[FileType],
                 previously_downloaded: List[bool],
                 temporal_span: int = 3600):
        self.thumbnail_types = thumbnail_types
        self.previously_downloaded = previously_downloaded
        self.rows = []  # type: List[ProximityRow]
        self.row_height = []  # type: List[int]
        self.proximity_row_to_thumbnail_row_col2 = defaultdict(set)  # type: Dict[int, Set[int]]
        self.proximity_row_to_thumbnail_row_col1 = defaultdict(set)  # type: Dict[int, Set[int]]
        self.row_to_group_no = dict()  # type: Dict[int, int]
        self.unique_ids_in_row_col2 = defaultdict(list)  # type: Dict[int, List[int]]
        self.unique_ids_in_row_col1 = defaultdict(list)  # type: Dict[int, List[int]]
        self.unique_ids_in_row_col0 = defaultdict(list)  # type: Dict[int, List[int]]
        self.file_types_in_cell = dict()  # type: Dict[Tuple[int, int], Tuple[FileType]]
        self.times_by_proximity = defaultdict(list)
        self.unique_ids_by_proximity = defaultdict(list)
        self.new_files_by_proximity = defaultdict(set)  # type: Dict[int, Set[bool]]
        self.text_by_proximity = deque()
        self.day_groups = defaultdict(list)
        self.month_groups = defaultdict(list)
        self.year_groups = defaultdict(list)
        self._depth = None
        self._previous_year = False
        self._previous_month = False
        # Tuple of (column, row, row_span):
        self.spans = []  # type: List[Tuple[int, int, int]]
        self.row_span_for_column_starts_at_row = {}  # type: Dict[Tuple[int, int], int]

        if not thumbnail_types:
            return
        self.dominant_file_type = Counter(thumbnail_types).most_common()[0][0]

        self.display_values = ProximityDisplayValues()

        # Generate an arrow date time for every timestamp we have
        uniqueid_times = [UniqueIdTime(tr.modification_time,
                                       arrow.get(tr.modification_time).to('local'),
                                       tr.id_value)
                          for tr in thumbnail_rows]

        now = arrow.now().to('local')
        current_year = now.year
        current_month = now.month

        # Phase 1: Associate unique ids with their year, month and day
        for x in uniqueid_times:
            t = x.arrowtime  # type: arrow.Arrow
            year = t.year
            month = t.month
            day = t.day

            # Could use arrow.floor here, but it's very slow
            self.day_groups[(year, month, day)].append(x.unqiue_id)
            self.month_groups[(year, month)].append(x.unqiue_id)
            self.year_groups[year].append(x.unqiue_id)
            if year != current_year:
                self._previous_year = True
            if month != current_month or self._previous_year:
                self._previous_month = True

        # Phase 2: Identify the proximity groups
        group_no = 0
        prev = uniqueid_times[0]
        i = 0

        self.times_by_proximity[group_no].append(prev.arrowtime)
        self.unique_ids_by_proximity[group_no].append(prev.unqiue_id)
        self.new_files_by_proximity[group_no].add(not previously_downloaded[i])

        if len(uniqueid_times) > 1:
            for current in uniqueid_times[1:]:
                i += 1
                modification_time = current.modification_time
                if (modification_time - prev.modification_time > temporal_span):
                    group_no += 1
                self.times_by_proximity[group_no].append(current.arrowtime)
                self.unique_ids_by_proximity[group_no].append(current.unqiue_id)
                self.new_files_by_proximity[group_no].add(not previously_downloaded[i])
                prev = current

        # Phase 3: Generate the proximity group's text that will appear in
        # the right-most column
        for i in range(len(self.times_by_proximity)):
            start = self.times_by_proximity[i][0]  # type: Arrow
            end = self.times_by_proximity[i][-1]  # type: Arrow
            self.text_by_proximity.append(humanize_time_span(start, end,
                                                             insert_cr_on_long_line=True))

        # Phase 4: Generate the rows to be displayed to the user
        self.prev_row_month = None  # type: Tuple[int, int]
        self.prev_row_day = None  # type: Tuple[int, int, int]
        row_index = -1
        thumbnail_row_index = -1
        column2_span = 0
        for group_no in range(len(self.times_by_proximity)):
            arrowtime = self.times_by_proximity[group_no][0]
            prev_day = (arrowtime.year, arrowtime.month, arrowtime.day)
            text = self.text_by_proximity.popleft()
            new_file = any(self.new_files_by_proximity[group_no])
            row_index += 1 + column2_span
            thumbnail_row_index += 1
            self.rows.append(self.make_row(arrowtime, text, new_file, prev_day, row_index,
                                           thumbnail_row_index))
            self.proximity_row_to_thumbnail_row_col2[row_index].add(thumbnail_row_index)
            self.row_to_group_no[row_index] = group_no

            slice_end = thumbnail_row_index + len(self.times_by_proximity[group_no])
            file_types = tuple(self.thumbnail_types[thumbnail_row_index:slice_end])
            self.file_types_in_cell[(row_index, 2)] = file_types

            if len(self.times_by_proximity[group_no]) > 1:
                column2_span = 0
                for arrowtime in self.times_by_proximity[group_no][1:]:
                    thumbnail_row_index += 1
                    self.proximity_row_to_thumbnail_row_col2[row_index].add(thumbnail_row_index)

                    day = (arrowtime.year, arrowtime.month, arrowtime.day)

                    if prev_day != day:
                        prev_day = day
                        column2_span += 1
                        self.rows.append(self.make_row(arrowtime, '', new_file, prev_day,
                                                       row_index + column2_span,
                                                       thumbnail_row_index))

        # Phase 5: Determine the row spans for each column
        column = -1
        for c in (0, 2, 4):
            column += 1
            start_row = 0
            for row_index, row in enumerate(self.rows):
                if row[c]:
                    row_count = row_index - start_row
                    if row_count > 1:
                        self.spans.append((column, start_row, row_count))
                    start_row = row_index
                self.row_span_for_column_starts_at_row[(row_index, column)] = start_row

            if start_row != len(self.rows) - 1:
                self.spans.append((column, start_row, len(self.rows) - start_row))
                for row_index in range(start_row, len(self.rows)):
                    self.row_span_for_column_starts_at_row[(row_index, column)] = start_row

        assert len(self.row_span_for_column_starts_at_row) == len(self.rows) * 3

        # Phase 6: Determine the height and width of each row
        self.display_values.calculate_row_sizes(self.rows, self.spans, self.depth())

        # Phase 7: Assign appropriate color to table
        self.display_values.assign_color(self.dominant_file_type)

        self.display_values.prepare_for_pickle()

    def make_row(self, arrowtime: Arrow,
                 text: str,
                 new_file: bool,
                 day: Tuple[int, int, int],
                 row_index: int,
                 thumbnail_row_index: int) -> ProximityRow:

        arrowmonth = day[:2]
        if arrowmonth != self.prev_row_month:
            self.prev_row_month = arrowmonth
            month = arrowtime.datetime.strftime('%B')
            year = arrowtime.year
            unique_ids = self.month_groups[day[:2]]
            self.unique_ids_in_row_col0[row_index] = unique_ids
            slice_end = thumbnail_row_index + len(unique_ids)
            file_types = tuple(self.thumbnail_types[thumbnail_row_index:slice_end])
            self.file_types_in_cell[(row_index, 0)] = file_types
        else:
            month = year = ''

        if day != self.prev_row_day:
            self.prev_row_day = day
            numeric_day = arrowtime.format('D')
            weekday = arrowtime.datetime.strftime('%a')

            # Record which thumbnails are in this day's group, and the
            # type of file they represent (photo, video)
            self.unique_ids_in_row_col1[row_index] = self.day_groups[day]
            slice_end = thumbnail_row_index + len(self.day_groups[day])
            file_types = tuple(self.thumbnail_types[thumbnail_row_index:slice_end])
            self.file_types_in_cell[(row_index, 1)] = file_types
            self.proximity_row_to_thumbnail_row_col1[row_index] = set(range(thumbnail_row_index,
                                                                            slice_end))
        else:
            weekday = numeric_day = ''

        return ProximityRow(year, month, weekday, numeric_day, text, new_file)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, row_number) -> ProximityRow:
        return self.rows[row_number]

    def __iter__(self):
        return iter(self.rows)

    def selected_thumbnail_rows(self, selected_rows_col1: List[int],
                                selected_rows_col2: List[int]) -> Set[int]:
        """
        Associate thumbnails with cells selected by the user.

        :param selected_rows_col1: any selected cells in column 1 that
         are not already represented by cells selected in column 2
        :param selected_rows_col2: all selected cells in column 2
        :return: thumbnail rows associated with selected cells
        """

        s = set()
        for row in selected_rows_col1:
            s.update(self.proximity_row_to_thumbnail_row_col1[row])
        for row in selected_rows_col2:
            s.update(self.proximity_row_to_thumbnail_row_col2[row])
        return s

    def depth(self):
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
        return 'TemporalProximityGroups with {} rows and depth of {}'.format(len(self.rows),
                                                                             self.depth())


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

    def __init__(self, rapidApp, groups: TemporalProximityGroups = None, parent=None):
        super().__init__(parent)
        self.rapidApp = rapidApp
        self.groups = groups

    def columnCount(self, parent=QModelIndex()):
        return 3

    def rowCount(self, parent=QModelIndex()):
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
            if column == 0:
                return proximity_row.year, proximity_row.month
            elif column == 1:
                return proximity_row.weekday, proximity_row.day
            else:
                return proximity_row.proximity, proximity_row.new_file
        elif role == Qt.ToolTipRole:
            thumbnails = self.rapidApp.thumbnailModel.thumbnails

            if column == 1:
                unique_ids = self.groups.unique_ids_in_row_col1[row]
            elif column == 2:
                proximity_row = self.groups.row_span_for_column_starts_at_row[(row, 2)]
                group_no = self.groups.row_to_group_no[proximity_row]
                unique_ids = self.groups.unique_ids_by_proximity[group_no]
            else:
                assert column == 0
                unique_ids = self.groups.unique_ids_in_row_col0[row]

            length = len(unique_ids)
            pixmap = thumbnails[unique_ids[0]]  # type: QPixmap

            image = base64_thumbnail(pixmap, self.tooltip_image_size)
            html_image1 = '<img src="data:image/png;base64,{}">'.format(image)

            if length == 1:
                center = html_image2 = ''
            else:
                pixmap = thumbnails[unique_ids[-1]]  # type: QPixmap
                image = base64_thumbnail(pixmap, self.tooltip_image_size)
                if length == 2:
                    center = '&nbsp;'
                else:
                    center = '&nbsp;&hellip;&nbsp;'
                html_image2 = '<img src="data:image/png;base64,{}">'.format(image)

            c = FileTypeCounter(self.groups.file_types_in_cell[row, column])
            file_types = c.summarize_file_count()[0]
            tooltip = '{} {} {}<br>{}'.format(html_image1, center, html_image2, file_types)
            return tooltip


class TemporalProximityDelegate(QStyledItemDelegate):
    """
    Render table cell for Timeline.

    All cell size calculations are done prior to rendering.
    """
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.darkGray = QColor(51, 51, 51)
        self.darkerGray = self.darkGray.darker(150)
        self.midGray = QColor('#555555')
        # self.color1 = QColor(CustomColors.color1.value)
        # self.color1Darker = self.color1.darker(107)

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
            weekday_rect_bottom = int(height / 2 - self.dv.max_col1_text_height *
                                      self.dv.day_proportion) + self.dv.max_weekday_height
            weekdayRect = QRect(0, 0, width, weekday_rect_bottom)
            day_rect_top = weekday_rect_bottom + self.dv.col1_center_space
            dayRect = QRect(0, day_rect_top, width, height - day_rect_top)

            painter.setFont(self.dv.weekdayFont)
            painter.setPen(weekdayColor)
            painter.drawText(weekdayRect, Qt.AlignHCenter | Qt.AlignBottom, weekday)
            painter.setFont(self.dv.dayFont)
            painter.setPen(dayColor)
            painter.drawText(dayRect, Qt.AlignHCenter | Qt.AlignTop, day)

            if row in self.dv.c2_end_of_month:
                painter.setPen(barColor)
                painter.drawLine(0, option.rect.height() - 1,
                                 option.rect.width(), option.rect.height() - 1)

            painter.restore()

        elif column == 2:
            text, new_file = index.data()

            painter.save()

            if option.state & QStyle.State_Selected:
                color = self.highlight
                textColor = self.highlightText
            else:
                color = self.dv.tableColor
                textColor = QColor(Qt.white)

            painter.fillRect(option.rect, color)

            align = self.dv.c2_alignment.get(row)

            if new_file:
                painter.setPen(self.newFileColor)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setBrush(self.newFileColor)
                rect = QRectF(option.rect.x(), option.rect.y(),
                             self.dv.col2_new_file_dot_size, self.dv.col2_new_file_dot_size)
                if align is None:
                    height = option.rect.height() / 2 -self.dv.col2_new_file_dot_radius - \
                             self.dv.col2_font_descent_adjust
                    rect.translate(self.dv.col2_new_file_dot_left_margin, height)
                elif align == Align.bottom:
                    height = (option.rect.height() - self.dv.col2_font_height_half -
                              self.dv.col2_font_descent_adjust - self.dv.col2_new_file_dot_size)
                    rect.translate(self.dv.col2_new_file_dot_left_margin, height)
                else:
                    height = (self.dv.col2_font_height_half -
                              self.dv.col2_font_descent_adjust)
                    rect.translate(self.dv.col2_new_file_dot_left_margin, height)
                painter.drawEllipse(rect)

            painter.setFont(self.dv.proximityFont)
            painter.setPen(textColor)

            rect = QRect(option.rect)
            rect.translate(self.dv.col2_text_left_margin, 0)

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
                painter.drawLine(0, option.rect.height() - 1,
                                 self.dv.col_widths[2], option.rect.height() - 1)

            painter.restore()
        else:
            super().paint(painter, option, index)


class TemporalProximityView(QTableView):
    def __init__(self) -> None:
        super().__init__()
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
            self.selectionModel().select(model.index(r, 1),
                                         QItemSelectionModel.Select)
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
                    # Is the row the same as the clicked row?
                    if not (row==clicked_row and self.rowSpan(row, column) == 1):
                        do_selection_confirmed = True
                        break
                # Is this the only selected row in the column selected?
                if ((row < clicked_row or row >= clicked_row + row_span) and column ==
                        clicked_column):
                    do_selection_confirmed = True
                    break

            if not do_selection_confirmed:
                self.clearSelection()
                do_selection = False

        if do_selection:
            super().mousePressEvent(event)


class TemporalValuePicker(QWidget):
    """
    Simple composite widget of QSlider and QLabel
    """

    # Emites number of minutes
    valueChanged =  pyqtSignal(int)

    def __init__(self, minutes: int, parent=None) -> None:
        super().__init__(parent)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setToolTip(_("The time elapsed between consecutive photos and "
                                 "videos that is used to build the Timeline"))
        self.slider.setMaximum(len(proximity_time_steps) - 1)
        self.slider.setValue(proximity_time_steps.index(minutes))

        # self.slider.setStyleSheet("""
        # QSlider {
        #     border: none;
        #     outline: none;
        # }
        # """)

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


class QFramedLabel(QLabel):
    """
    Draw a Frame around the label in the style of the application.
    """
    def paintEvent(self, *opts):
        painter = QPainter(self)
        option = QStyleOptionFrame()
        option.initFrom(self)
        style = self.style()  # type: QStyle
        style.drawPrimitive(QStyle.PE_Frame, option, painter)
        super().paintEvent(*opts)

class TemporalProximity(QWidget):
    """
    Displays Timeline and tracks its state.

    Main widget to display and control Timeline.
    """

    def __init__(self, rapidApp,
                 thumbnailProxyModel,
                 prefs: Preferences,
                 parent=None) -> None:
        """
        :param rapidApp: main application window
        :type rapidApp: RapidWindow
        :param thumbnailProxyModel: thumbnail display's filter
        :type thumbnailProxyModel: ThumbnailSortFilterProxyModel
        :param prefs: program & user preferences
        :param parent: parent widget
        """

        super().__init__(parent)

        self.rapidApp = rapidApp
        self.thumbnailProxyModel = thumbnailProxyModel
        self.prefs = prefs

        self.state = TemporalProximityState.empty

        self.temporalProximityView = TemporalProximityView()
        self.temporalProximityModel = TemporalProximityModel(rapidApp=rapidApp)
        self.temporalProximityView.setModel(self.temporalProximityModel)
        self.temporalProximityDelegate = TemporalProximityDelegate()
        self.temporalProximityView.setItemDelegate(self.temporalProximityDelegate)
        self.temporalProximityView.selectionModel().selectionChanged.connect(
                                                self.proximitySelectionChanged)

        self.temporalProximityView.setSizePolicy(QSizePolicy.Preferred,
                                                 QSizePolicy.MinimumExpanding)

        self.temporalValuePicker = TemporalValuePicker(self.prefs.get_proximity())
        self.temporalValuePicker.setSizePolicy(QSizePolicy.Preferred,
                                                 QSizePolicy.Minimum)

        description = _('The Timeline groups photos and videos based on how much time elapsed '
'between consecutive shots. Use it to identify photos and videos taken at '
'different periods in a single day or over consecutive days.')
        adjust = _('Use the slider to adjust the time elapsed between consecutive shots '
'that is used to build the Timeline.')
        generation_pending = _("Timeline build pending...")
        generating = _("Timeline is building...")

        description = '<i>{}</i>'.format(description)
        generation_pending = '<i>{}</i>'.format(generation_pending)
        generating = '<i>{}</i>'.format(generating)
        adjust = '<i>{}</i>'.format(adjust)

        palette = QPalette()
        palette.setColor(QPalette.Window, palette.color(palette.Base))

        margin = 6


        self.description = QLabel(description)
        self.generating = QLabel(generating)
        self.generationPending = QLabel(generation_pending)
        self.adjust = QLabel(adjust)

        self.explanation = QFramedLabel()
        layout = QVBoxLayout()
        border_width = QSplitter().lineWidth()
        layout.setContentsMargins(border_width, border_width, border_width, border_width)
        layout.setSpacing(0)
        self.explanation.setLayout(layout)
        layout.addWidget(self.description)
        layout.addWidget(self.adjust)

        for label in (self.description, self.generationPending, self.generating, self.adjust):
            label.setMargin(margin)
            label.setWordWrap(True)
            label.setAutoFillBackground(True)
            label.setPalette(palette)

        for label in (self.description, self.generationPending, self.generating):
            label.setAlignment(Qt.AlignTop)
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        self.adjust.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self.explanation)
        layout.addWidget(self.temporalValuePicker)

        self.temporalValuePicker.valueChanged.connect(self.temporalValueChanged)

        self.another_generation_needed = False

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

        selected_rows_col2 = [i.row() for i in self.temporalProximityView.selectedIndexes()
                              if i.column() == 2]
        selected_rows_col1 = [i.row() for i in self.temporalProximityView.selectedIndexes()
                              if i.column() == 1 and
                              groups.row_span_for_column_starts_at_row[(
                              i.row(), 2)] not in selected_rows_col2]

        if selected_rows_col2 or selected_rows_col1:
            self.thumbnailProxyModel.selected_rows = groups.selected_thumbnail_rows(
                    selected_rows_col1, selected_rows_col2)
            self.thumbnailProxyModel.invalidateFilter()
        else:
            self.thumbnailProxyModel.selected_rows = set()
            self.thumbnailProxyModel.invalidateFilter()

    def clearThumbnailDisplayFilter(self):
        self.thumbnailProxyModel.selected_rows = set()
        self.thumbnailProxyModel.invalidateFilter()

    def setState(self, state: TemporalProximityState) -> None:
        layout = self.layout()  # type: QVBoxLayout
        if self.state == TemporalProximityState.empty:
            existingWidget = self.explanation
        elif self.state == TemporalProximityState.pending:
            existingWidget = self.generationPending
        elif self.state == TemporalProximityState.generating:
            existingWidget = self.generating
        else:
            assert self.state == TemporalProximityState.generated
            existingWidget = self.temporalProximityView

        existingWidget.hide()

        if state == TemporalProximityState.pending:
            newWidget = self.generationPending
        elif state == TemporalProximityState.generating:
            newWidget = self.generating
        elif state == TemporalProximityState.generated:
            newWidget = self.temporalProximityView
        else:
            assert state == TemporalProximityState.empty
            newWidget = self.explanation

        layout.removeWidget(existingWidget)
        layout.insertWidget(0, newWidget)
        newWidget.show()

        self.clearThumbnailDisplayFilter()

        self.state = state


    def setGroups(self, proximity_groups: TemporalProximityGroups) -> None:
        if self.another_generation_needed:
            self.another_generation_needed = False
            self.rapidApp.generateTemporalProximityTableData()
            return

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

    @pyqtSlot(int)
    def temporalValueChanged(self, minutes: int) -> None:
        self.prefs.set_proximity(minutes=minutes)
        if self.state == TemporalProximityState.generated:
            self.setState(TemporalProximityState.generating)
            self.rapidApp.generateTemporalProximityTableData()
        elif self.state == TemporalProximityState.generating:
            self.another_generation_needed = True
