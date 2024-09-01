#!/usr/bin/python3

# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import pickle
import proximity

with open('proximity_test_data', 'rb') as data:
    test_rows = pickle.load(data)

p = proximity.TemporalProximityGroups(test_rows)
print(p.depth())
