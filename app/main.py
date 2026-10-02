"""FastAPI app: /reports endpoints + Inngest serve mount."""

import uuid

import inngest
import inngest.fast_api
from fastapi import FastAPI, Header, HTTPException, Response

from app import models, store
from worker.client import client
from worker.functions import cleanup_old_jobs, generate_report

store.init_db()

app = FastAPI(title="flyrank-reports", version="0.1.0")


@app.post("/reports", response_model=models.ReportAccepted, status_code=202)
async def create_report(
    body: models.ReportRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> models.ReportAccepted:
    """Accept a report request and hand the slow work to Inngest.

    Reusing an Idempotency-Key returns the EXISTING job with HTTP 200
    (no duplicate job, no duplicate event).
    """
    if idempotency_key:
        existing = store.find_by_idempotency_key(idempotency_key)
        if existing:
            response.status_code = 200
            return models.ReportAccepted(
                job_id=existing["job_id"], status=existing["status"]
            )

    job_id = str(uuid.uuid4())
    store.create_job(job_id, idempotency_key)

    await client.send(
        inngest.Event(
            name="app/report.requested",
            data={
                "job_id": job_id,
                "title": body.title,
                "sections": body.sections,
            },
        )
    )
    return models.ReportAccepted(job_id=job_id, status=models.JobStatus.PENDING)


@app.get("/reports/{job_id}", response_model=models.JobResponse)
async def get_report(job_id: str) -> models.JobResponse:
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return models.JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=job["progress"],
        result=job["result"],
    )


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


inngest.fast_api.serve(app, client, [generate_report, cleanup_old_jobs])
