"""TLP propagation helper.

Re-exports `tlp_max` from enums; this module exists so callers don't reach into
the enums module for behaviour.
"""

from __future__ import annotations

from cti.core.enums import TLP, tlp_max

__all__ = ["TLP", "tlp_max"]
