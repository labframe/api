"""Database change detection service for polling-based notifications."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


class ChangeDetector:
    """Detects changes in the database by tracking last known state."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._last_max_rowid: Optional[int] = None

    def detect_changes(self) -> tuple[bool, list[str]]:
        """
        Detect changes in parameter values and return affected parameter names.

        Returns:
            Tuple of (has_changes, affected_parameter_names)
        """
        connection = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row

        try:
            # Get current max rowid from _sample_param_value table
            cursor = connection.execute(
                """
                SELECT MAX(rowid) AS max_rowid
                FROM _sample_param_value
                """
            )
            row = cursor.fetchone()
            current_max_rowid = row["max_rowid"] if row and row["max_rowid"] is not None else 0

            # If rowid increased, changes occurred
            if self._last_max_rowid is None:
                # First check - initialize and don't report changes
                self._last_max_rowid = current_max_rowid
                return (False, [])

            if current_max_rowid > self._last_max_rowid:
                # Changes detected - get affected parameter names
                cursor = connection.execute(
                    """
                    SELECT DISTINCT d.name AS param_name
                    FROM _sample_param_value AS spv
                    JOIN _param_def AS d ON d.param_id = spv.param_id
                    WHERE spv.rowid > ?
                    ORDER BY d.name
                    """,
                    (self._last_max_rowid,),
                )
                affected_parameters = [row["param_name"] for row in cursor.fetchall()]

                # Update last known state
                self._last_max_rowid = current_max_rowid

                return (True, affected_parameters)

            # No changes
            return (False, [])

        finally:
            connection.close()

    def reset(self) -> None:
        """Reset the detector state (useful for testing or reinitialization)."""
        self._last_max_rowid = None

