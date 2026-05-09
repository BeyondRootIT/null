"""HTTP connector emitting bytes intended for the CSV parser."""

from __future__ import annotations

from cti.plugins.connectors.http_base import HttpConnectorBase


class HttpCsvConnector(HttpConnectorBase):
    name = "http_csv"
    default_content_type = "text/csv"
