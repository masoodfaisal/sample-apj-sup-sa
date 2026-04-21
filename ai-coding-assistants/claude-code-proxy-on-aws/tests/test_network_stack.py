"""Snapshot test for NetworkStack."""

from aws_cdk.assertions import Template

from tests.conftest import assert_matches_snapshot


def test_network_stack_snapshot(stack_bundle) -> None:
    template = Template.from_stack(stack_bundle.network)
    assert_matches_snapshot("network_stack", template)
