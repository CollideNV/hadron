"""Release routes — backward-compatible re-export of query + ops routers.

Import ``router`` from this module to get all release routes (used by
tests and the embedded single-process dev mode).
"""

from __future__ import annotations

from fastapi import APIRouter

from hadron.controller.routes.release_ops import router as _ops_router
from hadron.controller.routes.release_queries import router as _queries_router

router = APIRouter()
router.include_router(_queries_router)
router.include_router(_ops_router)
