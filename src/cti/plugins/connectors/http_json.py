"""HTTP connector emitting bytes intended for the JSON parser."""

from __future__ import annotations

from cti.plugins.connectors.http_base import HttpConnectorBase


class HttpJsonConnector(HttpConnectorBase):
    name = "http_json"
    default_content_type = "application/json"
