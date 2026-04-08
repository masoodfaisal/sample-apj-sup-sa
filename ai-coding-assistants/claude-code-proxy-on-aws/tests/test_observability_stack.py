"""Snapshot test for ObservabilityStack."""

from aws_cdk.assertions import Template

from tests.conftest import assert_matches_snapshot


def test_observability_stack_snapshot(stack_bundle) -> None:
    template = Template.from_stack(stack_bundle.observability)
    assert_matches_snapshot("observability_stack", template)
