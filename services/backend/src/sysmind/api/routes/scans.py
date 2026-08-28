from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from sysmind.api.dto.scans import ScanListResponse, ScanResponse
from sysmind.application.services import QuickScanCoordinator
from sysmind.core.constants import CORRELATION_HEADER

router = APIRouter(prefix="/api/v1/scans", tags=["scans"])


def _coordinator(request: Request) -> QuickScanCoordinator:
    return cast(QuickScanCoordinator, request.app.state.quick_scan_coordinator)


@router.post("/quick", response_model=ScanResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_quick_scan(
    request: Request,
    correlation_id: Annotated[str | None, Header(alias=CORRELATION_HEADER)] = None,
) -> ScanResponse:
    # Coordinator.start schedules asyncio tasks and must run on the event loop.
    return ScanResponse.from_record(_coordinator(request).start(correlation_id))


@router.get("", response_model=ScanListResponse)
async def recent_scans(request: Request) -> ScanListResponse:
    items = await run_in_threadpool(_coordinator(request).recent)
    return ScanListResponse(items=[ScanResponse.from_record(item) for item in items])


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str, request: Request) -> ScanResponse:
    record = await run_in_threadpool(_coordinator(request).get, scan_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found.")
    return ScanResponse.from_record(record)


@router.post("/{scan_id}/cancel", response_model=ScanResponse)
async def cancel_scan(scan_id: str, request: Request) -> ScanResponse:
    record = await run_in_threadpool(_coordinator(request).cancel, scan_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found.")
    return ScanResponse.from_record(record)
