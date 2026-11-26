import time

import httpx
import pytest
from PIL import Image

from recipebook.intake.jobs import Job, JobStore
from recipebook.intake.pipeline import Pipeline, Worker
from recipebook.intake.structure import StructurerError, StructurerUnavailable
from recipebook.library import Library
from recipebook.model import Ingredient, IngredientGroup, Recipe, Step

from test_readers import FakeOcr, RECIPE_DATA, page


class FakeStructurer:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.seen = result, error, []

    def structure(self, material, categories, glossary):
        self.seen.append(material)
        if self.error:
            raise self.error
        if self.result is not None:
            return self.result
        return [Recipe(
            title="Shortbread", category="Desserts & Baking", structured_by="local",
            ingredient_groups=[IngredientGroup(items=[Ingredient(text="1 c butter"), Ingredient(text="3/4 cup sugar")])],
            steps=[Step(text="Bake at 325°F for 35-40 minutes.")],
            source=material.source, original_text=material.text,
        )]


@pytest.fixture
def setup(tmp_path):
    library = Library(tmp_path / "library.db")
    jobs = JobStore(tmp_path / "library.db")
    structurers = {"local": FakeStructurer(), "claude": FakeStructurer()}
    html = page("x", RECIPE_DATA)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html)))
    pipeline = Pipeline(jobs, library, tmp_path / "originals", FakeOcr("1 cup butter ½ cup sugar 325 35 40"),
                        lambda name: structurers[name], url_client=client)
    return pipeline, jobs, structurers, tmp_path


def url_job(jobs, **kw):
    return jobs.add(Job(kind="url", label="example.com/shortbread", url="https://example.com/shortbread", **kw))


def test_url_job_becomes_a_styled_flagged_draft(setup):
    pipeline, jobs, _, _ = setup
    job = pipeline.process(url_job(jobs))
    assert job.state == "done" and job.message == "1 recipe ready for review."
    [draft] = jobs.drafts_for(job.id)
    recipe = draft.recipe
    assert draft.state == "needs_review" and jobs.needing_review() == 1
    assert [i.text for i in recipe.ingredients()] == ["1 cup butter", "¾ cup sugar"]  # code rules applied
    assert recipe.steps[0].text == "Bake at 325 degrees for 35 to 40 minutes."
    assert recipe.source.credit() == "Source: example.com/shortbread"
    changed = [f for f in recipe.flags if f.kind == "amount_changed"]
    assert len(changed) == 1 and "¾" in changed[0].message  # the source said 1/2 cup sugar


def test_reader_failure_is_reported_with_advice(setup):
    pipeline, jobs, _, _ = setup
    job = pipeline.process(jobs.add(Job(kind="url", label="x", url="notaurl")))
    assert job.state == "failed" and "not a web address" in job.message and job.advice
    assert jobs.drafts_for(job.id) == []


def test_no_recipe_found(setup):
    pipeline, jobs, structurers, _ = setup
    structurers["local"].result = []
    job = pipeline.process(url_job(jobs))
    assert job.state == "failed" and job.message == "No recipe was found in this item."
    assert "Retry with Claude" in job.advice


def test_waiting_jobs_resume_and_do_not_block_claude_jobs(setup):
    pipeline, jobs, structurers, _ = setup
    structurers["local"].error = StructurerUnavailable("Ollama is not running.", "ollama serve")
    first, second, third = url_job(jobs), url_job(jobs), url_job(jobs, structurer="claude")
    assert pipeline.run_pending() is True
    assert jobs.get(first.id).state == "waiting" and jobs.get(first.id).advice == "ollama serve"
    assert jobs.get(second.id).state == "queued"  # not attempted once the first proved Ollama is down
    assert jobs.get(third.id).state == "done"
    assert len(structurers["local"].seen) == 1
    structurers["local"].error = None
    assert pipeline.run_pending() is False
    assert jobs.get(first.id).state == jobs.get(second.id).state == "done"
    assert jobs.get(first.id).material is not None  # the page was not fetched again


def test_structurer_failure_then_retry_with_claude_reuses_the_material(setup):
    pipeline, jobs, structurers, _ = setup
    structurers["local"].error = StructurerError("The local model's reply was cut off.", "Use Retry with Claude on this item.")
    job = pipeline.process(url_job(jobs))
    assert job.state == "failed" and "cut off" in job.message
    retried = jobs.retry(job.id, "claude")
    assert retried.state == "queued" and retried.structurer == "claude"
    pipeline.run_pending()
    assert jobs.get(job.id).state == "done" and len(structurers["claude"].seen) == 1
    assert structurers["claude"].seen[0].text == structurers["local"].seen[0].text


def test_retry_replaces_unreviewed_drafts_only(setup):
    pipeline, jobs, _, _ = setup
    job = pipeline.process(url_job(jobs))
    [draft] = jobs.drafts_for(job.id)
    jobs.mark_draft(draft.id, "saved", recipe_id=7)
    jobs.add_draft(job.id, draft.recipe)
    jobs.retry(job.id, "claude")
    assert [d.state for d in jobs.drafts_for(job.id)] == ["saved"]


def test_photo_job_uses_cookbook_credit_and_flags_low_text(setup):
    pipeline, jobs, _, tmp_path = setup
    photo = tmp_path / "IMG_1.png"
    Image.new("RGB", (200, 100), "white").save(photo)
    job = pipeline.process(jobs.add(Job(kind="photo", label="IMG_1.png", files=[str(photo)],
                                        cookbook_title="Sample Cookbook", cookbook_author="A. N. Author")))
    [draft] = jobs.drafts_for(job.id)
    assert draft.recipe.source.credit() == "Source: Sample Cookbook, by A. N. Author"
    assert "low_text" in [f.kind for f in draft.recipe.flags]


def test_unexpected_errors_fail_the_job_not_the_worker(setup):
    pipeline, jobs, structurers, _ = setup
    structurers["local"].error = RuntimeError("boom")
    job = pipeline.process(url_job(jobs))
    assert job.state == "failed" and "RuntimeError: boom" in job.message


def test_interrupted_jobs_are_requeued_on_start(setup):
    pipeline, jobs, _, _ = setup
    job = url_job(jobs)
    jobs.update(job.model_copy(update={"state": "structuring"}))
    assert jobs.requeue_interrupted() == 1 and jobs.get(job.id).state == "queued"


def test_worker_thread_processes_the_queue(setup):
    pipeline, jobs, _, _ = setup
    worker = Worker(pipeline, idle_seconds=0.05)
    worker.start()
    try:
        job = url_job(jobs)
        worker.wake()
        deadline = time.time() + 5
        while jobs.get(job.id).state != "done" and time.time() < deadline:
            time.sleep(0.05)
        assert jobs.get(job.id).state == "done"
    finally:
        worker.stop()
