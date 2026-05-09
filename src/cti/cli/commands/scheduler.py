"""`cti scheduler` — boots the APScheduler service in the foreground."""

from __future__ import annotations

import asyncio


def scheduler() -> None:
    """Run the APScheduler service (one replica)."""
    from cti.manager.scheduler import main

    asyncio.run(main())
