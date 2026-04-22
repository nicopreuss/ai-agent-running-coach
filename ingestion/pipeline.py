"""Ingestion pipeline: orchestrates fetch → normalize → upsert for each data source."""

import logging

from ingestion.sources.base import DataSource

logger = logging.getLogger(__name__)


def run_pipeline(sources: list[DataSource]) -> None:
    """Execute the full ingestion pipeline for every provided source.

    Args:
        sources: List of DataSource instances to run in sequence.
    """
    for source in sources:
        name = type(source).__name__
        logger.info("Starting ingestion for source: %s", name)

        raw = source.fetch()
        logger.info("Fetched %d raw records from %s", len(raw), name)

        normalised = source.normalize(raw)
        logger.info("Normalised %d records from %s", len(normalised), name)

        written = source.upsert(normalised)
        logger.info("Upserted %d records from %s", written, name)

    logger.info("Pipeline complete for %d source(s).", len(sources))
