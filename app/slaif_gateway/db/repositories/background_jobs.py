"""Repository helpers for background_jobs table operations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from slaif_gateway.db.models import BackgroundJob


class BackgroundJobsRepository:
    """Encapsulates CRUD-style access for BackgroundJob rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_background_job(
        self,
        *,
        job_type: str,
        status: str = "queued",
        celery_task_id: str | None = None,
        created_by_admin_user_id: uuid.UUID | None = None,
        payload_summary: dict[str, object] | None = None,
    ) -> BackgroundJob:
        row = BackgroundJob(
            job_type=job_type,
            status=status,
            celery_task_id=celery_task_id,
            created_by_admin_user_id=created_by_admin_user_id,
            payload_summary=payload_summary or {},
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update_background_job_status(
        self,
        background_job_id: uuid.UUID,
        *,
        status: str,
        result_summary: dict[str, object] | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> bool:
        background_job = await self.get_background_job_by_id(background_job_id)
        if background_job is None:
            return False

        background_job.status = status
        if result_summary is not None:
            background_job.result_summary = result_summary
        background_job.error_message = error_message
        background_job.started_at = started_at
        background_job.finished_at = finished_at
        await self._session.flush()
        return True

    async def get_background_job_by_id(self, background_job_id: uuid.UUID) -> BackgroundJob | None:
        return await self._session.get(BackgroundJob, background_job_id)

    async def find_background_job_by_celery_task_id(self, celery_task_id: str) -> BackgroundJob | None:
        result = await self._session.execute(
            select(BackgroundJob).where(BackgroundJob.celery_task_id == celery_task_id)
        )
        return result.scalar_one_or_none()
