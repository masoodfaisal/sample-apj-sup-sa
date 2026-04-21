"""Aggregate admin router."""

from __future__ import annotations

from fastapi import APIRouter

from gateway.domains.admin import budgets, models, teams, usage, users, virtual_keys

router = APIRouter(prefix="/v1/admin")
router.include_router(users.router)
router.include_router(virtual_keys.router)
router.include_router(teams.router)
router.include_router(models.router)
router.include_router(budgets.router)
router.include_router(usage.router)
