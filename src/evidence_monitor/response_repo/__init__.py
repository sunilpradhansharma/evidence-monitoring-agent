"""Response Repository: the immutable response record plus capture/query/export (US1).

The :class:`~evidence_monitor.response_repo.repository.ResponseService` is imported from
``response_repo.repository`` directly — not re-exported here — to avoid a circular import, since
``data_access.interface`` imports this package's ``schema`` module.
"""

from __future__ import annotations

from evidence_monitor.response_repo.schema import Response

__all__ = ["Response"]
