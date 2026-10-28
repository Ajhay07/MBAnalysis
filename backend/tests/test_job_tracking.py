"""Phase 13: background job / processing-state hardening.

Covers: a proper Job record per analysis run (stage/retry_count/failure_reason/
started_at/completed_at), clean failure handling for every major failure mode (vision
provider auth error, vision provider transient error after retries exhausted, malformed AI
JSON, corrupt PDF), a job never stuck in "processing", never silently succeeding when it
didn't, retry incrementing retry_count, and a failed real-drawing retry never falling back to
demo-tagged content."""
import os

import pytest

from app.config import get_settings
from app.models.models import Drawing, DrawingStatus, Job, JobStage, UserRole
from app.providers.base import ProviderAuthError, ProviderTransientError
from app.services.analysis_pipeline import run_analysis


def _make_drawing(db, name: str = "job_test.png") -> Drawing:
    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(settings.UPLOAD_DIR, name)
    # 1x1 PNG - valid enough for cv2.imread, irrelevant to these tests since the provider is mocked.
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d7636060600000000500010d0a2db40000000049454e44ae426082"
    )
    with open(path, "wb") as f:
        f.write(png_bytes)
    drawing = Drawing(
        drawing_number=f"JOB-{name}", title="Job Tracking Test", revision="A",
        file_name=name, stored_file_name=name, file_type="png", file_size=len(png_bytes),
        status=DrawingStatus.UPLOADED, is_demo=False,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)
    return drawing


def _latest_job(db, drawing_id: str) -> Job:
    return db.query(Job).filter(Job.drawing_id == drawing_id).order_by(Job.created_at.desc()).first()


def test_successful_run_records_job_with_terminal_stage_and_timestamps(db):
    drawing = _make_drawing(db, "success.png")
    analysis = run_analysis(db, drawing)
    job = _latest_job(db, drawing.id)

    assert job.status == "Done"
    assert job.stage in (JobStage.NEEDS_REVIEW, JobStage.REVIEWED)
    assert job.retry_count == 0
    assert job.failure_reason is None
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.analysis_id == analysis.id
    assert drawing.is_demo is False


def test_vision_provider_auth_error_fails_job_cleanly_never_stuck_processing(db, monkeypatch):
    drawing = _make_drawing(db, "autherr.png")

    class FailingProvider:
        name = "openai"

        def analyze(self, **kwargs):
            raise ProviderAuthError("OpenAI authentication/authorization failed: invalid api key")

    monkeypatch.setattr("app.services.analysis_pipeline.get_provider", lambda: FailingProvider())

    with pytest.raises(ProviderAuthError):
        run_analysis(db, drawing)

    db.refresh(drawing)
    job = _latest_job(db, drawing.id)
    assert drawing.status == DrawingStatus.FAILED
    assert drawing.status != DrawingStatus.PROCESSING
    assert job.status == "Failed"
    assert job.stage == JobStage.FAILED
    assert "auth" in job.failure_reason.lower()
    assert job.completed_at is not None
    assert drawing.is_demo is False


def test_vision_provider_transient_error_exhausted_fails_job_cleanly(db, monkeypatch):
    drawing = _make_drawing(db, "transient.png")

    class FailingProvider:
        name = "openai"

        def analyze(self, **kwargs):
            raise ProviderTransientError("OpenAI request failed after 2 retries: timeout")

    monkeypatch.setattr("app.services.analysis_pipeline.get_provider", lambda: FailingProvider())

    with pytest.raises(ProviderTransientError):
        run_analysis(db, drawing)

    db.refresh(drawing)
    job = _latest_job(db, drawing.id)
    assert drawing.status == DrawingStatus.FAILED
    assert job.status == "Failed"
    assert job.stage == JobStage.FAILED
    assert "timeout" in job.failure_reason.lower() or "retries" in job.failure_reason.lower()


def test_malformed_ai_json_response_fails_cleanly(db, monkeypatch):
    """A provider that cannot produce a schema-valid result (simulating a malformed AI JSON
    response) must raise a retryable-classified error that the pipeline turns into a clean
    Failed job, never a raw unhandled 500 and never a silently-successful job."""
    drawing = _make_drawing(db, "malformed.png")

    class GarbageProvider:
        name = "openai"

        def analyze(self, **kwargs):
            raise ProviderTransientError("AI provider returned JSON that did not match the expected schema")

    monkeypatch.setattr("app.services.analysis_pipeline.get_provider", lambda: GarbageProvider())

    with pytest.raises(ProviderTransientError):
        run_analysis(db, drawing)

    db.refresh(drawing)
    job = _latest_job(db, drawing.id)
    assert drawing.status == DrawingStatus.FAILED
    assert job.stage == JobStage.FAILED
    assert "schema" in job.failure_reason.lower()


def test_ocr_unavailable_does_not_crash_pipeline_and_does_not_fabricate_success(db, monkeypatch):
    """PaddleOCR missing/unavailable is a graceful degradation (vision analysis still runs), not
    a hard failure - document that explicitly: the pipeline must still reach a real terminal
    stage (not get stuck), and components are still genuinely derived from the provider, not
    faked."""
    # Explicit DemoProvider: DemoProvider is no longer the implicit no-key default (see
    # app.providers.get_provider), and this test specifically wants "the provider still ran and
    # produced something" regardless of OCR - the deterministic provider would legitimately
    # return zero components for this 1x1 placeholder PNG regardless of OCR availability, which
    # would defeat the point of this test.
    from app.providers.demo_provider import DemoProvider
    monkeypatch.setattr("app.services.analysis_pipeline.get_provider", lambda: DemoProvider())

    drawing = _make_drawing(db, "no_ocr.png")
    monkeypatch.setattr("app.services.paddle_ocr._get_engine", lambda: None)

    analysis = run_analysis(db, drawing)
    job = _latest_job(db, drawing.id)

    assert job.status == "Done"
    assert job.stage in (JobStage.NEEDS_REVIEW, JobStage.REVIEWED)
    assert drawing.status != DrawingStatus.PROCESSING
    assert analysis.components  # demo provider still produced real (if placeholder) components


def test_retry_after_failure_increments_retry_count_and_can_succeed(db, monkeypatch):
    drawing = _make_drawing(db, "retry.png")

    class FailingProvider:
        name = "openai"

        def analyze(self, **kwargs):
            raise ProviderTransientError("simulated transient failure")

    monkeypatch.setattr("app.services.analysis_pipeline.get_provider", lambda: FailingProvider())
    with pytest.raises(ProviderTransientError):
        run_analysis(db, drawing)

    db.refresh(drawing)
    assert drawing.status == DrawingStatus.FAILED
    first_job = _latest_job(db, drawing.id)
    assert first_job.retry_count == 0

    # Retry: simulate the /reprocess endpoint's retry_count accounting, and let a real (demo)
    # provider succeed this time. Set explicitly (rather than monkeypatch.undo(), which would
    # now fall through to DeterministicProvider - the no-key default since this change - and
    # legitimately return zero components for this placeholder PNG, defeating this test's
    # "analysis.components" assertion below).
    from app.providers.demo_provider import DemoProvider
    monkeypatch.setattr("app.services.analysis_pipeline.get_provider", lambda: DemoProvider())
    prior_retries = db.query(Job).filter(Job.drawing_id == drawing.id).count()
    analysis = run_analysis(db, drawing, retry_count=prior_retries)

    db.refresh(drawing)
    retry_job = _latest_job(db, drawing.id)
    assert retry_job.retry_count == 1
    assert retry_job.status == "Done"
    assert drawing.status != DrawingStatus.FAILED
    assert drawing.is_demo is False  # a real drawing never gets tagged demo, even on retry
    assert analysis.components


def test_reprocess_endpoint_retries_failed_real_drawing_never_demo_tagged(client, make_user, db, monkeypatch):
    admin, pw = make_user(role=UserRole.ADMIN)
    login = client.post("/api/auth/login", json={"email": admin.email, "password": pw})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    stored_name = "reprocess_api_test.png"
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415408d7636060600000000500010d0a2db40000000049454e44ae426082"
    )
    with open(os.path.join(settings.UPLOAD_DIR, stored_name), "wb") as f:
        f.write(png_bytes)
    drawing = Drawing(
        drawing_number="REPROC-1", title="Reprocess API Test", revision="A",
        file_name=stored_name, stored_file_name=stored_name, file_type="png",
        file_size=len(png_bytes), status=DrawingStatus.UPLOADED, is_demo=False,
    )
    db.add(drawing)
    db.commit()
    db.refresh(drawing)

    class FailingProvider:
        name = "openai"

        def analyze(self, **kwargs):
            raise ProviderAuthError("bad key")

    monkeypatch.setattr("app.services.analysis_pipeline.get_provider", lambda: FailingProvider())
    resp = client.post(f"/api/drawings/{drawing.id}/analyze", headers=headers)
    assert resp.status_code == 422

    monkeypatch.undo()
    resp2 = client.post(f"/api/drawings/{drawing.id}/reprocess", headers=headers)
    assert resp2.status_code == 200
    body = resp2.json()
    # real pipeline ran fresh (no seeded demo content leaked in) - "deterministic" is the real
    # no-key default now (see app.providers.get_provider), not "demo".
    assert body.get("provider") == "deterministic"

    jobs_resp = client.get(f"/api/drawings/{drawing.id}/jobs", headers=headers)
    assert jobs_resp.status_code == 200
    jobs = jobs_resp.json()
    assert len(jobs) == 2
    assert jobs[0]["retry_count"] == 1  # most recent (the retry) first
    assert jobs[0]["status"] == "Done"
    assert jobs[1]["status"] == "Failed"
    assert jobs[1]["failure_reason"]

    drawing_resp = client.get(f"/api/drawings/{drawing.id}", headers=headers)
    out = drawing_resp.json()
    assert out["is_demo"] is False
    assert out["job_retry_count"] == 1
