"""Compatibility wrappers for the PoC one-listing realtime scraper."""

from __future__ import annotations

from typing import Any


def run_incremental_cycle(**kwargs: Any) -> None:
    from api.scrape_service import run_scrape_cycle

    run_scrape_cycle(**kwargs)


def start_incremental_background_loops(**kwargs: Any) -> None:
    from api.scrape_service import start_background_scraper

    start_background_scraper(**kwargs)
