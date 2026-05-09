"""Dead-letter sink: records permanent failures for later inspection / replay."""

from __future__ import annotations

import hashlib
import traceback
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from cti.persistence.models import DeadLetterRow


async def record_dead_letter(
    session: AsyncSession,
    *,
    feed_run_id: UUID,
    source_id: str,
    payload: bytes | None,
    error: BaseException,
    reason: str = "permanent",
) -> DeadLetterRow:
    sha = hashlib.sha256(payload or b"").hexdigest()
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    row = DeadLetterRow(
        feed_run_id=feed_run_id,
        source_id=source_id,
        payload_sha=sha,
        error_class=type(error).__name__,
        error_msg=str(error)[:1000],
        traceback=tb[:8000],
        reason=reason,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    try:
        from cti.obs.metrics import DLQ_TOTAL

        DLQ_TOTAL.labels(source=source_id, reason=reason).inc()
    except ImportError:
        pass
    return row
