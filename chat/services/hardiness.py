"""
Look up plant hardiness zone by ZIP code from the Hardiness Zone CSV.
"""

import csv
from pathlib import Path


def get_hardiness_for_zip(zip_code: str, csv_path) -> str | None:
    """
    Return the hardiness zone string for the given ZIP code, or None if not found.
    Uses columns 'Zip Code' and 'Average and Minimum Hardiness Zones'.
    """
    zip_clean = (zip_code or "").strip()
    if not zip_clean:
        return None
    if not csv_path or not Path(csv_path).exists():
        return None
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_zip = (row.get("Zip Code") or "").strip()
                if row_zip == zip_clean:
                    zone = (row.get("Average and Minimum Hardiness Zones") or "").strip()
                    return zone if zone else None
    except Exception:
        pass
    return None
