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

from collections import (namedtuple, defaultdict)
import locale
import datetime

import arrow.arrow
from sortedcontainers import SortedListWithKey

from gettext import gettext as _

from PyQt5.QtCore import (QAbstractTableModel, QModelIndex, Qt)
from PyQt5.QtWidgets import QTableView, QTreeView

GroupRow = namedtuple('GroupRow', 'year, month, day, time')

YEAR, MONTH, DAY, TIME = range(4)

def locale_time(t: datetime.datetime, show_seconds: bool=False) -> str:
    """
    Attempt to localize the time without displaying seconds
    Adapted from http://stackoverflow.com/questions/2507726/how-to-display
    -locale-sensitive-time-format-without-seconds-in-python
    :param t: time in datetime format
    :param show_seconds: whether to show seconds or not
    :return: time in format like "12:08 AM", or locale equivalent
    """
    if show_seconds:
        return t.strftime('%X')
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

class TemporalProximityGroups:
    def __init__(self, sorted_list_items: SortedListWithKey,
                 temporal_span: int):
        self.years = set()
        self.months = set()
        self.days = set()
        self.row_counter = 0
        self.row = {}
        self.groups = defaultdict(list)
        self.timestamps = defaultdict(list)
        self.formatted_row = {}

        if sorted_list_items:
            # Phase 1: group the time stamps
            prev = sorted_list_items[0]

            timestamp = prev.modification_time
            self.group_start_time = None
            self.groups[timestamp].append(prev.id_value)
            self.timestamps[timestamp].append(timestamp)
            self._add_timestamp(timestamp)
            for sorted_list_item in sorted_list_items[1:]:
                modification_time = sorted_list_item.modification_time
                if (modification_time - prev.modification_time
                        > temporal_span):
                    timestamp = sorted_list_item.modification_time
                    self._add_timestamp(timestamp)
                prev = sorted_list_item
                self.timestamps[timestamp].append(modification_time)
                self.groups[timestamp].append(sorted_list_item.id_value)

            # Phase 2: extract the group time spans, and create headings
            prev_year = ''
            prev_month = ''
            prev_day = ''

            for row_counter in range(len(self.row)):
                start_timestamp = self.row[row_counter]
                start = arrow.get(start_timestamp).to('local') # type: arrow.Arrow
                end_timestamp = self.timestamps[start_timestamp][-1]
                end =  arrow.get(end_timestamp).to('local') # type: arrow.Arrow
                
                if start.year != end.year:
                    year = _('%(past_year)s - %(future_year)s') % {
                        'past_year': start.year,
                        'future_year': end.year}
                else:
                    year = start.year
                if year != prev_year:
                    row_year = year
                    prev_year = year
                else:
                    row_year = ''

                start_month = start.strftime('%B')
                end_month = end.strftime('%B')
                if start.month != end.month:
                    month = _('%(past_month)s - %(future_month)s') % {
                        'past_month': start_month,
                        'future_month': end_month}
                else:
                    month = start_month
                if month != prev_month:
                    row_month = month
                    prev_month = month
                else:
                    row_month = ''
                    
                if start.day != end.day:
                    day = _('%(past_day)s - %(future_day)s') % {
                        'past_day': start.day,
                        'future_day': end.day}
                else:
                    day = start.day
                if day != prev_day:
                    row_day = day
                    prev_day = day
                else:
                    row_day = ''

                start_time = locale_time(start.datetime)
                end_time = locale_time(end.datetime)
                if start_time != end_time:
                    row_time = _('%(past_time)s - %(future_time)s') % {
                        'past_time': start_time,
                        'future_time': end_time}
                else:
                    row_time = start_time

                group_row =  GroupRow(row_year, row_month, row_day, row_time)
                self.formatted_row[start_timestamp] = group_row

    def _add_timestamp(self, timestamp):
        a = arrow.get(timestamp).to('local') # type: arrow.Arrow
        self.years.add(a.year)
        self.months.add((a.year, a.month))
        self.days.add((a.year, a.month, a.day))

        self.row[self.row_counter] = timestamp
        self.row_counter += 1

    def __contains__(self, timestamp):
        return timestamp in self.groups

    def __len__(self):
        return len(self.groups)

    def __getitem__(self, row_number) -> float:
        """
        :return:timestamp for the row
        """
        return self.row[row_number]

    def __iter__(self):
        return iter(self.groups)

    def generate_re(self, timestamp):
        return '|'.join(self.groups[timestamp])

    def get_headers(self, timestamp):
        return self.formatted_row[timestamp]

    def depth(self):
        if len(self.years) > 1:
            return 3
        elif len(self.months) > 1:
            return 2
        elif len(self.days) > 1:
            return 1
        else:
            return 0


class TemporalProximityModel(QAbstractTableModel):
    header_labels = (_('Year'), _('Month'), _('Day'), _('Time'),)
    def __init__(self, parent, groups: TemporalProximityGroups=None):
        super().__init__(parent)
        self.rapidApp = parent # type: rapid.RapidWindow
        self.groups = groups


    def setGroup(self, groups: TemporalProximityGroups):
        self.groups = groups
        self.endResetModel()

    def columnCount(self, parent=QModelIndex()):
        return 4

    def rowCount(self, parent=QModelIndex()):
        if self.groups:
            return len(self.groups)
        else:
            return 0

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.header_labels[section]
        return QAbstractTableModel.headerData(self, section, orientation, role)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        if row >= len(self.groups) or row < 0:
            return None

        column = index.column()
        if column < 0 or column > 3:
            return None
        timestamp = self.groups.row[row] # type: float
        group = self.groups.get_headers(timestamp) # type: GroupRow

        if role==Qt.DisplayRole:
            if column == 0:
                return group.year
            elif column == 1:
                return group.month
            elif column == 2:
                return group.day
            else:
                return group.time


class TemporalProximityView(QTableView):
    pass