"""HTTP connector emitting bytes intended for the text-lines extractor."""

from __future__ import annotations

from cti.plugins.connectors.http_base import HttpConnectorBase


class HttpTxtLinesConnector(HttpConnectorBase):
    name = "http_txt_lines"
    default_content_type = "text/plain"
