"""Step-registry integrity — the 72-step structure is a hard invariant."""

import pytest

from app.db.models import PipelineKind
from app.pipeline.registry import REGISTRY, get_steps, phase_title


@pytest.mark.parametrize("pipeline", [PipelineKind.STRATEGY, PipelineKind.GTM])
class TestRegistryIntegrity:
    def test_exactly_72_steps(self, pipeline):
        assert len(get_steps(pipeline)) == 72

    def test_eight_phases_of_nine(self, pipeline):
        steps = get_steps(pipeline)
        for phase in range(1, 9):
            assert sum(1 for s in steps if s.phase == phase) == 9
        assert {s.phase for s in steps} == set(range(1, 9))

    def test_step_no_is_sequential_1_to_72(self, pipeline):
        assert [s.step_no for s in get_steps(pipeline)] == list(range(1, 73))

    def test_phase_matches_step_no(self, pipeline):
        for s in get_steps(pipeline):
            assert s.phase == (s.step_no - 1) // 9 + 1

    def test_names_and_guidance_nonempty(self, pipeline):
        for s in get_steps(pipeline):
            assert s.name.strip()
            assert s.guidance.strip()

    def test_prompt_renders_with_all_blocks(self, pipeline):
        s = get_steps(pipeline)[41]  # arbitrary mid-pipeline step
        prompt = s.build_prompt("PRODUCT", "PATTERNS", "CONTEXT")
        for token in (s.name, s.phase_title, "PRODUCT", "PATTERNS", "CONTEXT"):
            assert token in prompt

    def test_phase_titles_resolve(self, pipeline):
        for phase in range(1, 9):
            assert phase_title(pipeline, phase).strip()


def test_ids_globally_unique_across_both_pipelines():
    ids = [s.id for steps in REGISTRY.values() for s in steps]
    assert len(ids) == 144
    assert len(set(ids)) == 144
