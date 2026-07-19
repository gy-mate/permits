"""Provide the required settings env vars so importing permits modules works.

Several modules (e.g. ``permits.enrich.http``) build the :class:`Settings` object at
import time; the unit tests never talk to these endpoints, so dummy values suffice.
"""

import os

os.environ.setdefault("PERMITS_REPO_URL", "https://example.invalid/repo")
os.environ.setdefault("DB_CONNECTION_STRING", "postgresql+asyncpg://user:pass@invalid:5432/permits")
os.environ.setdefault("PERMITS_CORS_ORIGINS", "http://invalid")
os.environ.setdefault("PERMITS_ENRICH_TIMEOUT", "60")
os.environ.setdefault("PERMITS_WIKIDATA_SPARQL_API_URL", "https://example.invalid/wikidata")
os.environ.setdefault("PERMITS_OSM_SPARQL_API_URL", "https://example.invalid/osm")
