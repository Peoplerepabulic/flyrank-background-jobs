"""Inngest functions: the report generator and the hourly cleanup cron."""

from datetime import datetime, timedelta, timezone

import inngest

from app import store
from worker.client import client


@client.create_function(
    fn_id="generate-report",
    trigger=inngest.TriggerEvent(event="app/report.requested"),
    retries=3,
)
async def generate_report(ctx: inngest.Context) -> dict:
    """Slow report generation (~8s) in visible steps, updating job status/progress."""
    data = ctx.event.data
    job_id = data["job_id"]
    title = data["title"]
    sections = data.get("sections", [])

    store.set_status(job_id, "running", 5)

    # NOTE: inngest's step.sleep takes *milliseconds*; use timedelta for seconds.
    await ctx.step.sleep("fetching-data", timedelta(seconds=3))
    store.set_status(job_id, "running", 40)

    await ctx.step.sleep("rendering-sections", timedelta(seconds=3))
    store.set_status(job_id, "running", 80)

    await ctx.step.sleep("finalizing", timedelta(seconds=2))

    result = {
        "title": title,
        "sections_rendered": len(sections),
        "summary": f"Report '{title}' generated in the background "
        f"with {len(sections)} section(s) rendered.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    store.complete_job(job_id, result)
    return result


@client.create_function(
    fn_id="cleanup-old-jobs",
    trigger=inngest.TriggerCron(cron="0 * * * *"),
)
async def cleanup_old_jobs(ctx: inngest.Context) -> dict:
    """Hourly cron: delete completed/failed jobs older than 1 hour."""
    deleted = store.cleanup_finished(older_than_hours=1)
    return {"deleted": deleted}
