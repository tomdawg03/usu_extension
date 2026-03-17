"""
Load extension PDF URLs from CSV into SQLite for search.
Usage: python manage.py load_extension_articles
"""

import csv
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from chat.services.article_search import url_to_searchable


class Command(BaseCommand):
    help = "Load extension-products CSV into extension_articles.db"

    def handle(self, *args, **options):
        db_path = getattr(settings, "EXTENSION_ARTICLES_DB_PATH", None)
        csv_path = getattr(settings, "EXTENSION_PRODUCTS_CSV_PATH", None)
        if not db_path or not csv_path:
            self.stderr.write("EXTENSION_ARTICLES_DB_PATH / EXTENSION_PRODUCTS_CSV_PATH not set")
            return
        csv_path = Path(csv_path)
        db_path = Path(db_path)
        if not csv_path.exists():
            self.stderr.write(f"CSV not found: {csv_path}")
            return

        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS articles (id INTEGER PRIMARY KEY, url TEXT NOT NULL, searchable_text TEXT NOT NULL)"
        )
        conn.execute("DELETE FROM articles")
        count = 0
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            col = "PDF URL"
            for row in reader:
                url = (row.get(col) or "").strip()
                if not url or not url.startswith("http"):
                    continue
                searchable = url_to_searchable(url)
                conn.execute("INSERT INTO articles (url, searchable_text) VALUES (?, ?)", (url, searchable))
                count += 1
        conn.commit()
        conn.close()
        self.stdout.write(f"Loaded {count} articles into {db_path}")
