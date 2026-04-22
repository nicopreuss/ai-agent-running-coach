"""Abstract base class for all data sources in the ingestion pipeline."""

from abc import ABC, abstractmethod


class DataSource(ABC):
    """Base interface that every concrete data source must implement.

    Subclass this in ingestion/sources/ to add a new data source.
    Each source is responsible for fetching raw records, normalising them
    into the project's canonical schema, and upserting them to the database.
    """

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Pull raw records from the external source.

        Returns:
            A list of raw record dicts as returned by the source API or file.
        """
        ...

    @abstractmethod
    def normalize(self, raw: list[dict]) -> list[dict]:
        """Transform raw records into the project's canonical schema.

        Args:
            raw: The list of dicts returned by fetch().

        Returns:
            A list of dicts conforming to the target schema.
        """
        ...

    @abstractmethod
    def upsert(self, records: list[dict]) -> int:
        """Write normalised records to the database, upserting on primary key.

        Args:
            records: The list of dicts returned by normalize().

        Returns:
            The number of records written (inserted or updated).
        """
        ...
