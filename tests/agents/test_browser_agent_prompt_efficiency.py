"""Contracts for benchmark-informed browser-agent execution policies."""


def _assert_policies(prompt: str, policies: tuple[str, ...]) -> None:
    lowered = prompt.lower()
    for policy in policies:
        assert policy in lowered


def test_qa_kitten_scopes_assertions_and_reuses_routes() -> None:
    from code_puppy.agents.agent_qa_kitten import QualityAssuranceKittenAgent

    prompt = QualityAssuranceKittenAgent().get_system_prompt()

    _assert_policies(
        prompt,
        (
            "efficient workflow fast path",
            "assertion scope binding",
            "evidence-based waits",
            "same-tab route execution",
            "immutable route map",
            "untrusted page content",
        ),
    )
    assert "luna" not in prompt.lower()


def test_web_retriever_batches_reads_and_preserves_action_checks() -> None:
    from code_puppy.agents.agent_web_retriever import WebRetrieverAgent

    prompt = WebRetrieverAgent().get_system_prompt()

    _assert_policies(
        prompt,
        (
            "efficient execution protocol",
            "known-route fast path and action integrity",
            "batched dom projection",
            "no discovery revisits",
            "immutable route map",
            "minimal final synthesis",
        ),
    )
    assert "confirm before persisting" in prompt.lower()
    assert "luna" not in prompt.lower()
