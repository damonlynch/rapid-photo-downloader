#!/usr/bin/env python3

# Copyright (C) 2015-2021 Damon Lynch <damonlynch@gmail.com>

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

"""Starts load balancer used for thumbnail extraction and caching"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2015-2021, Damon Lynch"

from raphodo.interprocess import LoadBalancerWorkerManager, LoadBalancer


class ThumbnailLoadBalancerWorkerManager(LoadBalancerWorkerManager):
    """
    Manages thumbnail extractors
    """

    def __init__(
        self, no_workers: int, backend_port: int, sink_port: int, logging_port: int
    ) -> None:
        super().__init__(no_workers, backend_port, sink_port, logging_port)
        self._process_name = "Thumbnail Load Balancer Manager"
        self._process_to_run = "thumbnailextractor.py"


class ThumbnailLoadBalancer(LoadBalancer):
    """
    Manages the thumbnail load balancer
    """

    def __init__(self) -> None:
        super().__init__("Thumbnail", ThumbnailLoadBalancerWorkerManager)


if __name__ == "__main__":
    loadbalancer = ThumbnailLoadBalancer()
