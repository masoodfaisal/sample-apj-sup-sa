"""Snapshot test for DataStack."""

from aws_cdk.assertions import Template

from tests.conftest import assert_matches_snapshot


def test_data_stack_snapshot(stack_bundle) -> None:
    template = Template.from_stack(stack_bundle.data)
    assert_matches_snapshot("data_stack", template)
