import sqlite3
import threading
from enum import Enum
from core import get_settings, validate_sql_identifier, migrate_table_columns

'''
Anywhere you see # nosec B608, it is marking a Bandit false positive. The table 
name is validated and locked after initialization, and the values are 
parameterized to prevent SQL injection.
'''


class Theme(str, Enum):
    """Enumeration of available UI themes."""

    RUBEDO     = "rubedo"
    CITRINITAS = "citrinitas"
    VIRIDITAS  = "viriditas"
    NIGREDO    = "nigredo"
    ALBEDO     = "albedo"
    AURORA     = "aurora"
    CAELUM     = "caelum"


# Defaults applied on first run / if the row is missing
_DEFAULT_SETTINGS = {
    "theme":            Theme.RUBEDO.value,
    "auto_download":    False,
    "keep_originals":   True,
    "cleanup_enabled":  True,
    "cleanup_ttl_minutes": 60
}

_SETTINGS_ROW_ID = 1  # Single-row table; always read/write row with this id


class SettingsDB:
    """Database class for managing application settings.

    Manages a single-row settings table that stores user-configurable
    application preferences such as theme, auto-download behaviour,
    and whether original files are retained after conversion.

    Attributes:
        settings: Application settings instance.
        DB_PATH: Path to the SQLite database file.
        _TABLE_NAME: Name of the database table for app settings.
        conn: Active SQLite database connection.
    """

    settings = get_settings()
    DB_PATH = settings.db_path
    _TABLE_NAME = settings.app_settings_table_name

    @property
    def TABLE_NAME(self) -> str:
        """str: The validated, immutable table name."""
        return self._table_name

    def __init__(self) -> None:
        """Initialize SettingsDB, validate the table name, create tables, and seed defaults."""
        # Validate and lock table name — immutable after init
        object.__setattr__(self, '_table_name', validate_sql_identifier(self._TABLE_NAME))
        self._local = threading.local()
        self.create_tables()
        self._seed_defaults()

    @property
    def conn(self) -> sqlite3.Connection:
        """Return a thread-local SQLite connection, creating one if needed."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.DB_PATH)
        return self._local.conn

    def create_tables(self) -> None:
        """Create the app settings table if it does not already exist."""
        with self.conn:
            self.conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                    id             INTEGER PRIMARY KEY,
                    theme          TEXT    NOT NULL DEFAULT '{Theme.RUBEDO.value}',
                    auto_download  INTEGER NOT NULL DEFAULT 0,
                    keep_originals INTEGER NOT NULL DEFAULT 1,
                    cleanup_enabled INTEGER NOT NULL DEFAULT 1,
                    cleanup_ttl_minutes INTEGER NOT NULL DEFAULT 60
                )
            """)  # nosec B608

        # Ensure every expected column exists (handles older DB schemas)
        migrate_table_columns(self.conn, self.TABLE_NAME, {
            "theme":               f"TEXT NOT NULL DEFAULT '{Theme.RUBEDO.value}'",
            "auto_download":       "INTEGER NOT NULL DEFAULT 0",
            "keep_originals":      "INTEGER NOT NULL DEFAULT 1",
            "cleanup_enabled":     "INTEGER NOT NULL DEFAULT 1",
            "cleanup_ttl_minutes": "INTEGER NOT NULL DEFAULT 60",
        })  # nosec B608

    def _seed_defaults(self) -> None:
        """Insert the default settings row if it does not already exist."""
        cursor = self.conn.cursor()
        cursor.execute(
            f"SELECT id FROM {self.TABLE_NAME} WHERE id = ?",  # nosec B608
            (_SETTINGS_ROW_ID,)
        )
        if cursor.fetchone() is None:
            with self.conn:
                self.conn.execute(
                    f"INSERT INTO {self.TABLE_NAME} (id, theme, auto_download, keep_originals, cleanup_enabled, cleanup_ttl_minutes) "  # nosec B608
                    f"VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        _SETTINGS_ROW_ID,
                        _DEFAULT_SETTINGS["theme"],
                        int(_DEFAULT_SETTINGS["auto_download"]),
                        int(_DEFAULT_SETTINGS["keep_originals"]),
                        int(_DEFAULT_SETTINGS["cleanup_enabled"]),
                        int(_DEFAULT_SETTINGS["cleanup_ttl_minutes"]),
                    )
                )

    @staticmethod
    def _row_to_dict(row: dict) -> dict:
        """Normalise a raw database row dict into typed application settings.

        Args:
            row: A dictionary produced by the Row-factory cursor, keyed by
                column name.

        Returns:
            A dictionary with keys theme (str), auto_download (bool),
            keep_originals (bool), cleanup_enabled (bool), and
            cleanup_ttl_minutes (int).
        """
        return {
            "theme":               row["theme"],
            "auto_download":       bool(row["auto_download"]),
            "keep_originals":      bool(row["keep_originals"]),
            "cleanup_enabled":     bool(row["cleanup_enabled"]),
            "cleanup_ttl_minutes": int(row["cleanup_ttl_minutes"]),
        }

    def get_settings(self) -> dict:
        """Return the current app settings as a dictionary.

        Returns:
            A dictionary with keys theme (str), auto_download (bool),
            keep_originals (bool), cleanup_enabled (bool), and
            cleanup_ttl_minutes (int). Falls back to default values if
            the settings row is missing.
        """
        cursor = self.conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE id = ?",  # nosec B608
            (_SETTINGS_ROW_ID,)
        )
        row = cursor.fetchone()
        if row is None:
            return dict(_DEFAULT_SETTINGS)
        return self._row_to_dict(row)

    def update_settings(self, updates: dict) -> dict:
        """Apply a partial or full update to the app settings.

        Accepted keys are theme, auto_download, and keep_originals, cleanup_ttl_minutes.
        Unknown keys are silently ignored. The settings row is created with
        defaults if it does not yet exist.

        Args:
            updates: A dictionary containing one or more of the following keys:
                theme (str): UI theme name; must be a valid Theme value.
                auto_download (bool): Whether to automatically download
                    converted files.
                keep_originals (bool): Whether to retain original files
                    after conversion.
                cleanup_ttl_minutes (int): Time-to-live in minutes for cleanup.
        

        Returns:
            A dictionary reflecting the updated settings, with keys theme
            (str), auto_download (bool), keep_originals (bool), and cleanup_ttl_minutes (int).

        Raises:
            ValueError: If the provided theme value is not a valid
                Theme enum member.
        """
        # Prevent SQL injection by allowing only known columns
        allowed = {"theme", "auto_download", "keep_originals", "cleanup_enabled", "cleanup_ttl_minutes"}
        filtered = {k: v for k, v in updates.items() if k in allowed}

        if not filtered:
            return self.get_settings()

        # Prevent SQL injection by allowing only known theme values
        if "theme" in filtered:
            try:
                filtered["theme"] = Theme(filtered["theme"]).value
            except ValueError:
                valid = [t.value for t in Theme]
                raise ValueError(f"Invalid theme '{filtered['theme']}'. Must be one of: {valid}")

        if "auto_download" in filtered:
            filtered["auto_download"] = int(bool(filtered["auto_download"]))
        if "keep_originals" in filtered:
            filtered["keep_originals"] = int(bool(filtered["keep_originals"]))
        if "cleanup_enabled" in filtered:
            filtered["cleanup_enabled"] = int(bool(filtered["cleanup_enabled"]))
        if "cleanup_ttl_minutes" in filtered:
            filtered["cleanup_ttl_minutes"] = int(filtered["cleanup_ttl_minutes"])

        set_clause = ", ".join(f"{col} = ?" for col in filtered)
        values = list(filtered.values()) + [_SETTINGS_ROW_ID]

        with self.conn:
            self.conn.execute(
                f"UPDATE {self.TABLE_NAME} SET {set_clause} WHERE id = ?",  # nosec B608
                values
            )

        return self.get_settings()

    def close(self) -> None:
        """Close the current thread's database connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
