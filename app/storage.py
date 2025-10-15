"""
Persistent storage for photo file IDs.

The PhotoStore class wraps a SQLite database, allowing the bot to cache
file_id values returned by Telegram when photos are uploaded. This
avoids re-uploading images every time they are sent.
"""

import aiosqlite
from typing import Optional


class PhotoStore:
    """A simple async storage layer for mapping slugs to Telegram file IDs."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self) -> None:
        """Initialise the database, creating the table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS photos (
                    slug TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def set_file_id(self, slug: str, file_id: str) -> None:
        """Insert or update the file_id for a given slug."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO photos(slug, file_id) VALUES(?, ?) 
                ON CONFLICT(slug) DO UPDATE SET file_id=excluded.file_id
                """,
                (slug, file_id),
            )
            await db.commit()

    async def get_file_id(self, slug: str) -> Optional[str]:
        """Retrieve the cached file_id for a given slug, if present."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT file_id FROM photos WHERE slug=?", (slug,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else None