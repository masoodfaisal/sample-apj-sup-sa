"""Model catalog and pricing repositories."""

from __future__ import annotations

from fnmatch import fnmatch
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from gateway.repositories.base import BaseRepository, paginate_window
from shared.models import ModelAliasMapping, ModelCatalog, ModelPricing
from shared.utils.constants import ModelStatus


class ModelCatalogRepository(BaseRepository):
    async def get_by_id(self, model_id: UUID) -> ModelCatalog | None:
        return await self.session.get(ModelCatalog, model_id)

    async def get_by_canonical_name(self, canonical_name: str) -> ModelCatalog | None:
        stmt = select(ModelCatalog).where(ModelCatalog.canonical_name == canonical_name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_canonical_names(self, names: list[str]) -> list[ModelCatalog]:
        if not names:
            return []
        stmt = select(ModelCatalog).where(ModelCatalog.canonical_name.in_(names))
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_active_list(self) -> list[ModelCatalog]:
        stmt = (
            select(ModelCatalog)
            .where(ModelCatalog.status == ModelStatus.ACTIVE)
            .order_by(ModelCatalog.canonical_name.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list(
        self, *, page: int = 1, page_size: int = 100
    ) -> tuple[list[ModelCatalog], int | None]:
        stmt = (
            select(ModelCatalog)
            .order_by(ModelCatalog.created_at.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        models = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(models, page, page_size)

    async def create(self, model: ModelCatalog) -> ModelCatalog:
        self.session.add(model)
        await self.session.flush()
        return model

    async def update(self, model: ModelCatalog, **changes: object) -> ModelCatalog:
        for key, value in changes.items():
            setattr(model, key, value)
        await self.session.flush()
        return model

    async def delete(self, model: ModelCatalog) -> None:
        await self.session.delete(model)
        await self.session.flush()


class ModelAliasMappingRepository(BaseRepository):
    async def get_by_id(self, mapping_id: UUID) -> ModelAliasMapping | None:
        return await self.session.get(ModelAliasMapping, mapping_id)

    async def list(
        self, *, page: int = 1, page_size: int = 100
    ) -> tuple[list[ModelAliasMapping], int | None]:
        stmt = (
            select(ModelAliasMapping)
            .order_by(ModelAliasMapping.priority.desc(), ModelAliasMapping.id.desc())
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
        mappings = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(mappings, page, page_size)

    async def delete(self, mapping: ModelAliasMapping) -> None:
        await self.session.delete(mapping)
        await self.session.flush()

    async def resolve_mapping(self, selected_model: str) -> ModelAliasMapping | None:
        stmt = (
            select(ModelAliasMapping)
            .options(joinedload(ModelAliasMapping.target_model))
            .where(ModelAliasMapping.active.is_(True))
            .order_by(ModelAliasMapping.priority.desc())
        )
        mappings = (await self.session.execute(stmt)).scalars().all()
        fallback: ModelAliasMapping | None = None
        for mapping in mappings:
            if mapping.is_fallback and fallback is None:
                fallback = mapping
            if fnmatch(selected_model, mapping.selected_model_pattern):
                return mapping
        return fallback

    async def resolve_model(self, selected_model: str) -> ModelCatalog | None:
        mapping = await self.resolve_mapping(selected_model)
        if mapping is None:
            return None
        return mapping.target_model

    async def create(self, mapping: ModelAliasMapping) -> ModelAliasMapping:
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def update(self, mapping: ModelAliasMapping, **changes: object) -> ModelAliasMapping:
        for key, value in changes.items():
            setattr(mapping, key, value)
        await self.session.flush()
        return mapping


class ModelPricingRepository(BaseRepository):
    async def get_by_id(self, pricing_id: UUID) -> ModelPricing | None:
        return await self.session.get(ModelPricing, pricing_id)

    async def list(
        self, *, model_id: UUID | None = None, page: int = 1, page_size: int = 100
    ) -> tuple[list[ModelPricing], int | None]:
        stmt = select(ModelPricing).order_by(
            ModelPricing.effective_from.desc(), ModelPricing.id.desc()
        )
        if model_id is not None:
            stmt = stmt.where(ModelPricing.model_id == model_id)
        stmt = stmt.limit(page_size + 1).offset((page - 1) * page_size)
        pricings = (await self.session.execute(stmt)).scalars().all()
        return paginate_window(pricings, page, page_size)

    async def delete(self, pricing: ModelPricing) -> None:
        await self.session.delete(pricing)
        await self.session.flush()

    async def get_active_pricing(self, model_id: UUID) -> ModelPricing | None:
        stmt = (
            select(ModelPricing)
            .where(ModelPricing.model_id == model_id, ModelPricing.active.is_(True))
            .order_by(ModelPricing.effective_from.desc())
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def create(self, pricing: ModelPricing) -> ModelPricing:
        self.session.add(pricing)
        await self.session.flush()
        return pricing

    async def update(self, pricing: ModelPricing, **changes: object) -> ModelPricing:
        for key, value in changes.items():
            setattr(pricing, key, value)
        await self.session.flush()
        return pricing
