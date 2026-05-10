# -*- coding: utf-8 -*-
"""Tests for market review lock stale cleanup on platforms without fcntl."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.core.market_review_lock as market_review_lock


class MarketReviewNoFcntlLockTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_running = market_review_lock._market_review_running
        market_review_lock._market_review_running = False

    def tearDown(self) -> None:
        market_review_lock._market_review_running = self._orig_running

    @staticmethod
    def _write_lock_file(path: Path, pid: int, started_at: datetime) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"pid={pid}\nstarted_at={started_at.isoformat()}\n",
            encoding="utf-8",
        )

    def test_stale_no_fcntl_lock_file_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = SimpleNamespace(database_path=str(Path(temp_dir) / "stock_analysis.db"))
            lock_path = market_review_lock.market_review_lock_path(config)
            self._write_lock_file(lock_path, pid=99999, started_at=datetime.now())

            with patch.object(market_review_lock, "fcntl", None), patch.object(
                market_review_lock,
                "_is_process_alive",
                return_value=False,
            ):
                token = market_review_lock.try_acquire_market_review_lock(config)

            self.assertIsNotNone(token)
            try:
                self.assertTrue(lock_path.exists())
            finally:
                market_review_lock.release_market_review_lock(token)

    def test_running_no_fcntl_lock_file_blocks_acquisition(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = SimpleNamespace(database_path=str(Path(temp_dir) / "stock_analysis.db"))
            lock_path = market_review_lock.market_review_lock_path(config)
            self._write_lock_file(lock_path, pid=12345, started_at=datetime.now())

            with patch.object(market_review_lock, "fcntl", None), patch.object(
                market_review_lock,
                "_is_process_alive",
                return_value=True,
            ):
                token = market_review_lock.try_acquire_market_review_lock(config)

            self.assertIsNone(token)
            self.assertTrue(lock_path.exists())

    def test_lock_with_old_started_at_is_recovered_even_if_process_alive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = SimpleNamespace(database_path=str(Path(temp_dir) / "stock_analysis.db"))
            lock_path = market_review_lock.market_review_lock_path(config)
            self._write_lock_file(
                lock_path,
                pid=12345,
                started_at=datetime.now() - timedelta(days=2),
            )

            with patch.object(market_review_lock, "fcntl", None), patch.object(
                market_review_lock,
                "_is_process_alive",
                return_value=True,
            ):
                token = market_review_lock.try_acquire_market_review_lock(config)

            self.assertIsNotNone(token)
            try:
                self.assertTrue(token.uses_flock is False)
            finally:
                market_review_lock.release_market_review_lock(token)
