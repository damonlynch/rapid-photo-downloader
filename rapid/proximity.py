__author__ = 'Damon Lynch'

# Copyright (C) 2015 Damon Lynch <damonlynch@gmail.com>

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

from collections import (namedtuple, defaultdict, deque)
import locale
from datetime import datetime
import logging
import pickle
import math

import arrow.arrow

from gettext import gettext as _

from PyQt5.QtCore import (QAbstractTableModel, QModelIndex, Qt, QSize,
                          QRect, QPoint)
from PyQt5.QtWidgets import (QTableView, QStyledItemDelegate,
                             QStyleOptionViewItem)
from PyQt5.QtGui import (QPainter, QFontMetrics, QFont, QColor)

ProximityRow = namedtuple('ProximityRow', 'year, month, weekday, day, '
                                          'proximity')

UniqueIdTime = namedtuple('UniqueIdTime', 'modification_time, arrowtime, '
                                          'unqiue_id')

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

AM = datetime(2015,11,3).strftime('%p')
PM = datetime(2015,11,3,13).strftime('%p')

def humanize_time_span(start: arrow.Arrow, end: arrow.Arrow,
                       strip_leading_zero_from_time: bool=True,
                       insert_cr_on_long_line: bool=False) -> str:
    r"""

    :param start: start time
    :param end: end time
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

        if (start.hour < 12 and end.hour < 12) or (start.hour >= 12 and
                                                   end.hour >= 12):
            # both dates are in the same meridiem
            start_time =  strip_ampm(start_time)

        # Translators: for example 9:00 AM - 3:55 PM
        return _('%(starttime)s - %(endtime)s') % {
                'starttime': start_time,
                'endtime': end_time}

    # Translators: for example Nov 3 or Dec 31
    start_date = _('%(month)s %(numeric_day)s') % {
        'month': start.datetime.strftime('%b'),
        'numeric_day': start.format('D')}
    end_date = _('%(month)s %(numeric_day)s') % {
        'month': end.datetime.strftime('%b'),
        'numeric_day': end.format('D')}

    if start.floor('year') != end.floor('year'):
        # Translators: for example Nov 3 2015
        start_date = _('%(date)s %(year)s') % {
            'date': start_date, 'year': start.year}
        end_date = _('%(date)s %(year)s') % {
            'date': end_date, 'year': end.year}

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
        

class TemporalProximityGroups:
    # @profile
    def __init__(self, thumbnail_rows: list,
                 temporal_span: int=3600):
        self.rows = []
        self.uniqueid_by_proximity = defaultdict(list)
        self.times_by_proximity = defaultdict(list)
        self.text_by_proximity = deque()
        self.day_groups = defaultdict(list)
        self.month_groups = defaultdict(list)
        self.year_groups = defaultdict(list)
        self._depth = None
        self._previous_year = False
        self._previous_month = False

        # print(thumbnail_rows[0].modification_time, type(thumbnail_rows[0].modification_time))

        # Generate an arrow date time for every timestamp we have.
        uniqueid_times = [UniqueIdTime(tr.modification_time,
                                  arrow.get(tr.modification_time).to('local'),
                                  tr.id_value)
                          for tr in thumbnail_rows]

        if not uniqueid_times:
            return

        now = arrow.now().to('local')
        current_year = now.year
        current_month = now.month

        # Phase 1: Associate unique ids with their year, month and day
        for x in uniqueid_times:
            self.day_groups[x.arrowtime.floor('day')].append(x.unqiue_id)
            self.month_groups[x.arrowtime.floor('month')].append(x.unqiue_id)
            self.year_groups[x.arrowtime.floor('year')].append(x.unqiue_id)
            if x.arrowtime.year != current_year:
                self._previous_year = True
            if x.arrowtime.month != current_month:
                self._previous_month = True

        # Phase 2: Identify the proximity groups
        group_no = 0
        prev = uniqueid_times[0]

        self.uniqueid_by_proximity[group_no].append(prev.unqiue_id)
        self.times_by_proximity[group_no].append(prev.arrowtime)

        if len(uniqueid_times) > 1:
            for current in uniqueid_times[1:]:
                modification_time = current.modification_time
                if (modification_time - prev.modification_time
                        > temporal_span):
                    group_no += 1
                self.times_by_proximity[group_no].append(current.arrowtime)
                self.uniqueid_by_proximity[group_no].append(current.unqiue_id)
                prev = current

        # Phase 3: Generate the proximity group's text that will appear in
        # the right-most column
        for i in range(len(self.times_by_proximity)):
            start = self.times_by_proximity[i][0] # type: arrow.Arrow
            end = self.times_by_proximity[i][-1] # type: arrow.Arrow
            self.text_by_proximity.append(humanize_time_span(start, end,
                                             insert_cr_on_long_line=True))

        # Phase 4: Generate the rows to be displayed to the user
        self.prev_row_month = None # type: arrow.Arrow
        self.prev_row_day = None  # type: arrow.Arrow
        self.row_index = -1
        for group_no in range(len(self.times_by_proximity)):
            arrowtime = self.times_by_proximity[group_no][0]
            prev_day = arrowtime.floor('day')
            text = self.text_by_proximity.popleft()
            self.row_index += 1
            self.rows.append(self.make_row(arrowtime, text))
            if len(self.times_by_proximity[group_no]) > 1:
                for arrowtime in self.times_by_proximity[group_no][1:]:
                    day = arrowtime.floor('day')

                    if prev_day != day:
                        prev_day = day
                        self.rows.append(self.make_row(arrowtime, ''))

        # Phase 5: Determine the row spans for each column
        self.spans = []
        self.row_span_for_col0_starts_at = {}
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
                if column == 0:
                    self.row_span_for_col0_starts_at[row_index] = start_row

            if start_row != len(self.rows) - 1:
                self.spans.append((column, start_row, len(self.rows) - start_row))
                for row_index in range(start_row, len(self.rows)):
                    self.row_span_for_col0_starts_at[row_index] = start_row

        assert len(self.row_span_for_col0_starts_at) == len(self.rows)

    def make_row(self, arrowtime: arrow.Arrow, text: str) -> ProximityRow:
        arrowmonth = arrowtime.floor('month')
        if arrowmonth != self.prev_row_month:
            self.prev_row_month = arrowmonth
            month = arrowtime.datetime.strftime('%B')
            year = arrowtime.year
        else:
            month = year = ''

        arrowday = arrowtime.floor('day')
        if arrowday != self.prev_row_day:
            self.prev_row_day = arrowday
            day = arrowtime.format('D')
            weekday = arrowtime.datetime.strftime('%a')
        else:
            weekday = day = ''

        return ProximityRow(year, month, weekday, day, text)

    # def __contains__(self, timestamp):
    #     return timestamp in self.uniqueid_by_proximity

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, row_number) -> ProximityRow:
        return self.rows[row_number]

    def __iter__(self):
        return iter(self.rows)

    # def generate_re(self, row):
    #     return '|'.join(self.uniqueid_by_proximity[timestamp])



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


class TemporalProximityModel(QAbstractTableModel):
    def __init__(self, parent, groups: TemporalProximityGroups=None):
        super().__init__(parent)
        self.rapidApp = parent # type: rapid.RapidWindow
        self.groups = groups

    def setGroup(self, groups: TemporalProximityGroups):
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
        proximity_row = self.groups[row] # type: ProximityRow

        if role==Qt.DisplayRole:
            if column == 0:
                # return '{} {}'.format(proximity_row.month,
                #                       proximity_row.year, )
                return proximity_row.year, proximity_row.month
            elif column == 1:
                return proximity_row.weekday, proximity_row.day
            else:
                return proximity_row.proximity


class TemporalProximityDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        parent_font = parent.font()

        self.darkGray = QColor(51, 51, 51)
        self.midGray = QColor('#555555')
        # Setup column 0
        self.month_sizes = {}
        self.month_kerning = 1.2
        self.month_font = QFont(parent_font) # type: QFont
        self.month_font.setPointSize(parent_font.pointSize() - 1)
        self.month_font.setLetterSpacing(QFont.PercentageSpacing,
                                         self.month_kerning * 100)
        self.month_font.setStretch(QFont.SemiExpanded)
        self.month_metrics = QFontMetrics(self.month_font)
        self.col0_padding = 20
        self.col0_center_space = 2
        self.col0_center_space_half = 1

        # Setup column 1
        self.weekday_font = QFont(parent_font) # type: QFont
        self.weekday_font.setPointSize(self.weekday_font.pointSize() - 3)
        self.weekday_metrics = QFontMetrics(self.weekday_font)
        self.weekday_height = self.weekday_metrics.height()

        self.day_font = QFont(parent_font) # type: QFont
        self.day_font.setPointSize(self.day_font.pointSize() + 1)
        self.day_metrics = QFontMetrics(self.day_font)

        self.col1_center_space = 2
        self.col1_center_space_half = 1
        self.col1_padding = 10

        self.calculate_max_col1_size()

        self.day_proporation = self.max_day_height / self.max_col1_text_height
        self.weekday_proporation = self.max_weekday_height / \
                                   self.max_col1_text_height

        # Setup column 2
        self.proximity_font = QFont(parent_font) # type: QFont
        self.proximity_font.setPointSize(parent_font.pointSize() -1)
        self.proximity_metrics = QFontMetrics(self.proximity_font)
        self.proximity_sizes = {}
        self.col2_padding = 20

    def calculate_max_col1_size(self) -> None:
        day_width = 0
        day_height = 0
        for day in range(10,32):
            rect = self.day_metrics.boundingRect(str(day))
            day_width = max(day_width, rect.width())
            day_height = max(day_height, rect.height())

        self.max_day_height = day_height
        self.max_day_width = day_width

        weekday_width = 0
        weekday_height = 0
        for i in range(1,7):
            dt = datetime(2015, 11, i)
            weekday = dt.strftime('%a').upper()
            rect = self.weekday_metrics.boundingRect(str(weekday))
            weekday_width = max(weekday_width, rect.width())
            weekday_height = max(weekday_height, rect.height())

        self.max_weekday_height = weekday_height
        self.max_weekday_width = weekday_width
        self.max_col1_text_height = weekday_height + day_height + \
                                self.col1_center_space
        self.max_col1_text_width = max(weekday_width, day_width)
        self.col1_width = self.max_col1_text_width + self.col1_padding
        self.col1_height = self.max_col1_text_height + self.col1_padding

    def getMonthSize(self, row: int, month: str) -> QSize:
        if row in self.month_sizes:
            # return a copy of the size, not the cached value
            # the consumer of the cached value might transpose it
            return QSize(self.month_sizes[row])

        boundingRect = self.month_metrics.boundingRect(month) # type: QRect
        height = boundingRect.height()
        width =  int(boundingRect.width() * self.month_kerning)
        size = QSize(width, height)
        self.month_sizes[row] = QSize(size)
        return size

    def getMonthText(self, month, year) -> str:
        if self.depth == 3:
            return _('%(month)s %(year)s') % {'month': month.upper(), 'year':
                year}
        else:
            return month.upper()

    def getProximitySize(self, row: int, text: str) -> QSize:
        if row in self.proximity_sizes:
            # return a copy of the size, not the cached value
            # the consumer of the cached value might transpose it
            return QSize(self.proximity_sizes[row])

        text = text.split('\n')
        width = height = 0
        for t in text:
            boundingRect = self.proximity_metrics.boundingRect(t) # type: QRect
            width = max(width, boundingRect.width())
            height += boundingRect.height()
        size = QSize(width, height)
        self.proximity_sizes[row] = QSize(size)
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index:  QModelIndex)  -> None:
        column = index.column()
        model = index.model()

        if column == 0:
            painter.save()
            row = index.row()

            painter.fillRect(option.rect, self.darkGray)
            painter.setPen(QColor(Qt.white))

            year, month =  model.data(index)

            month = self.getMonthText(month, year)

            x = option.rect.x()
            y = option.rect.y()

            painter.setFont(self.month_font)
            painter.setPen(QColor(Qt.white))

            month_size = self.getMonthSize(row, month)
            cell_height = option.rect.height()
            cell_width = option.rect.width()
            cell_x_center = cell_width / 2
            cell_y_center = cell_height / 2

            painter.rotate(270.0)

            # expected_minimum = self.sizeHint(option, index).height()
            # if cell_height < expected_minimum:
            #     logging.error(
            #         "Column height for row 0 is too small: with row %s "
            #         "expected %s but got %s", month, expected_minimum,
            #         cell_height)

            # Text is drawn using a point from the bottom left of the first
            # character, not the top left. So need to account for the text
            # height.
            # The rotation means we must be very careful to draw elements
            # correctly on the rotated plane!

            month_text_x = y * -1
            x_offset = cell_y_center + month_size.width() / 2
            month_text_x = month_text_x - x_offset

            text_y = x
            y_offset = cell_x_center + month_size.height() / 2
            text_y = text_y + y_offset

            painter.drawText(month_text_x, text_y, month)

            painter.restore()

        elif column == 1:
            painter.save()

            painter.fillRect(option.rect, self.darkGray)
            weekday, day = model.data(index)
            weekday = weekday.upper()
            width = option.rect.width()
            height =  option.rect.height()

            painter.translate(option.rect.x(), option.rect.y())
            weekday_rect_bottom = int(height / 2 - self.max_col1_text_height *
                                   self.day_proporation) + \
                                  self.max_weekday_height
            weekday_rect = QRect(0, 0,
                                 width, weekday_rect_bottom)
            day_rect_top = weekday_rect_bottom + self.col1_center_space
            day_rect = QRect(0, day_rect_top, width,
                             height-day_rect_top)

            painter.setFont(self.weekday_font)
            painter.setPen(QColor(221,221,221))
            painter.drawText(weekday_rect, Qt.AlignHCenter | Qt.AlignBottom,
                             weekday)
            painter.setFont(self.day_font)
            painter.setPen(QColor(Qt.white))
            painter.drawText(day_rect, Qt.AlignHCenter | Qt.AlignTop, day)
            painter.restore()

        elif column == 2:
            text = model.data(index)
            text = text.replace('\n', '\n\n')

            painter.save()

            painter.fillRect(option.rect, self.midGray)
            painter.setFont(self.proximity_font)
            painter.setPen(QColor(Qt.white))

            rect = QRect(option.rect)
            m = self.col2_padding // 2
            rect.translate(m, 0)
            painter.drawText(rect, Qt.AlignLeft |
                             Qt.AlignVCenter, text)

            painter.restore()
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:

        column = index.column()
        if column == 0:
            cell_size = self.column0Size(index)
            if cell_size.isNull():
                return cell_size
            else:
                model = index.model() # type: TemporalProximityModel
                row = index.row()
                span = self.parent().temporalProximityView.rowSpan(row,0)
                if span == 1:
                    return cell_size
                else:
                    #  The height of a particular row is calculated to
                    # include the row heights of the spanned column as
                    # if it were not spanned. The result is that other
                    # cells in the same row can be too high.

                    # Want max of col1_height and column 2 height
                    col2_height = self.column2Size(model.index(row, 2)).height()
                    return QSize(cell_size.width(), max(self.col1_height, col2_height))
        elif column == 1:
            row = index.row()
            span = self.parent().temporalProximityView.rowSpan(row,0)
            if span == 1:
                return QSize(self.col1_width, self.col1_height)
            else:
                # As above, the height of a particular row is calculated to
                # include the row heights of the spanned column as
                # if it were not spanned. The result is that other
                # cells in the same row can be too high.

                # Since we have manipulated the minimum height of
                # column 0, we need to take into account situations
                # where column 0 is taller than the contents of the
                # rows it spans

                # Need minimum height of column 0, divided by span
                col0_row = self.row_span_for_col0_starts_at[row]
                column0_height = self.column0Size(index.model().index(col0_row, 0)).height()
                assert column0_height > 0
                return QSize(self.col1_width, max(self.col1_height,
                                                  math.ceil(column0_height / span)))
        elif column == 2:
            return self.column2Size(index)
        else:
            return super().sizeHint(option, index)

    def column0Size(self, index) -> QSize:
        model = index.model() # type: TemporalProximityModel
        year, month =  model.data(index)
        # Don't return a cell size for empty cells that have been
        # merged into the cell with content.
        if not month:
            return QSize(0,0)
        else:
            row = index.row()
            month = self.getMonthText(month, year)
            size = self.getMonthSize(row, month)
            # Height and width are reversed because of the rotation
            size.transpose()

            return QSize(size.width() + self.col0_padding, size.height() + self.col0_padding)

    def column2Size(self, index) -> QSize:
        model = index.model()
        text = model.data(index)
        if not text:
            return QSize(0,0)
        else:
            row = index.row()
            text = text.replace('\n', '\n\n')
            size = self.getProximitySize(row, text)
            return QSize(size.width() + self.col2_padding, size.height() + self.col2_padding)


class TemporalProximityView(QTableView):
    def __init__(self) -> None:
        # style = """
        # QListView {
        # border: 0px;
        # }
        # """
        super().__init__()
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(False)
        # self.setShowGrid(False)

    def minimumSizeHint(self) -> QSize:
        model = self.model() # type: TemporalProximityModel
        w = 0
        for i in range(model.columnCount()):
            w += self.columnWidth(i)
        h = 100
        return QSize(w, h)


