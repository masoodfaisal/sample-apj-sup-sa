"""Tests for shared.exceptions hierarchy."""

from __future__ import annotations

import pytest

from shared.exceptions import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    BedrockError,
    BedrockThrottlingError,
    BudgetExceededError,
    InternalError,
    InvalidKeyError,
    KeyExpiredError,
    KeyRevokedError,
    ModelNotAllowedError,
    TeamInactiveError,
    UpstreamError,
    UserInactiveError,
    UserNotFoundError,
    ValidationError,
)


class TestExceptionHierarchy:
    def test_app_error_is_base_exception(self):
        assert issubclass(AppError, Exception)

    def test_authentication_error_hierarchy(self):
        assert issubclass(AuthenticationError, AppError)

    def test_invalid_key_error_hierarchy(self):
        assert issubclass(InvalidKeyError, AuthenticationError)
        assert issubclass(InvalidKeyError, AppError)

    def test_key_revoked_error_hierarchy(self):
        assert issubclass(KeyRevokedError, AuthenticationError)
        assert issubclass(KeyRevokedError, AppError)

    def test_key_expired_error_hierarchy(self):
        assert issubclass(KeyExpiredError, AuthenticationError)
        assert issubclass(KeyExpiredError, AppError)

    def test_authorization_error_hierarchy(self):
        assert issubclass(AuthorizationError, AppError)

    def test_user_not_found_error_hierarchy(self):
        assert issubclass(UserNotFoundError, AuthorizationError)
        assert issubclass(UserNotFoundError, AppError)

    def test_user_inactive_error_hierarchy(self):
        assert issubclass(UserInactiveError, AuthorizationError)
        assert issubclass(UserInactiveError, AppError)

    def test_team_inactive_error_hierarchy(self):
        assert issubclass(TeamInactiveError, AuthorizationError)

    def test_model_not_allowed_error_hierarchy(self):
        assert issubclass(ModelNotAllowedError, AuthorizationError)

    def test_budget_exceeded_error_hierarchy(self):
        assert issubclass(BudgetExceededError, AppError)

    def test_upstream_error_hierarchy(self):
        assert issubclass(UpstreamError, AppError)

    def test_bedrock_error_hierarchy(self):
        assert issubclass(BedrockError, UpstreamError)

    def test_bedrock_throttling_error_hierarchy(self):
        assert issubclass(BedrockThrottlingError, UpstreamError)

    def test_validation_error_hierarchy(self):
        assert issubclass(ValidationError, AppError)

    def test_internal_error_hierarchy(self):
        assert issubclass(InternalError, AppError)

    def test_all_errors_carry_message(self):
        for cls in (
            AppError,
            AuthenticationError,
            InvalidKeyError,
            KeyExpiredError,
            KeyRevokedError,
            AuthorizationError,
            UserNotFoundError,
            UserInactiveError,
            InternalError,
        ):
            err = cls("test message")
            assert str(err) == "test message"

    def test_except_app_error_catches_all_subclasses(self):
        for cls in (
            UserNotFoundError,
            InvalidKeyError,
            InternalError,
            BudgetExceededError,
            BedrockError,
        ):
            with pytest.raises(AppError):
                raise cls("caught")
