"""Shared Inngest client for the reports app."""

import inngest

# Dev mode: talk to the local Inngest dev server (localhost:8288), no signing key.
client = inngest.Inngest(app_id="flyrank-reports", is_production=False)
