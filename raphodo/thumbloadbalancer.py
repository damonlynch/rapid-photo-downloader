# SPDX-FileCopyrightText: Copyright 2015-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later


"""Starts load balancer used for thumbnail extraction and caching"""

from raphodo.interprocess import LoadBalancer, LoadBalancerWorkerManager


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
