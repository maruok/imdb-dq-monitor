"""
Ensures IMDB data files are present, downloading them if not.
Works both locally and on Streamlit Cloud.
"""

import os
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

FILES = {
    "title.ratings.tsv.gz": "https://datasets.imdbws.com/title.ratings.tsv.gz",
    "title.basics.tsv.gz": "https://datasets.imdbws.com/title.basics.tsv.gz",
}


def ensure_data(status_callback=None):
    """Download missing data files. status_callback(msg) is called with progress updates."""
    DATA_DIR.mkdir(exist_ok=True)
    for filename, url in FILES.items():
        dest = DATA_DIR / filename
        if dest.exists():
            continue
        msg = f"Downloading {filename}..."
        if status_callback:
            status_callback(msg)
        urllib.request.urlretrieve(url, dest)

    return str(DATA_DIR)
