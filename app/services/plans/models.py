"""Validated public inputs and composer output."""
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Short = Annotated[str, Field(min_length=1, max_length=200)]
Level = Literal['low', 'medium', 'high']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PlanRequest(StrictModel):
    submission_id: UUID
    quiz_id: UUID | None = None
    texture: Literal['2A', '2B', '2C', '3A', '3B', '3C', '4A', '4B', '4C']
    density: Level
    email: Annotated[str, Field(max_length=254)]
    porosity: Level | None = None
    moisture_behaviour: Short | None = None
    strand_thickness: Literal['fine', 'medium', 'coarse'] | None = None
    elasticity: Literal['low', 'normal', 'high'] | None = None
    scalp_state: Literal['dry', 'normal', 'oily', 'sensitive'] | None = None
    humidity_response: Literal['low', 'moderate', 'medium', 'high'] | None = None
    hair_length: Short | None = None
    hair_goals: list[Short] = Field(default_factory=list, max_length=10)
    concern_text: str = Field(default='', max_length=1000)
    location: Short | None = None
    first_name: Short | None = None
    marketing_consent: bool = False
    source: Short | None = None

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        value = value.strip()
        if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
            raise ValueError('Invalid email address')
        return value


class Feedback(StrictModel):
    rating: Literal['very_closely', 'somewhat', 'not_quite', 'not_sure']
    rejected_shopify_ids: list[Short] = Field(default_factory=list, max_length=30)
    unclear_step: Short | None = None
    note: str | None = Field(default=None, max_length=1000)


EVENT_PROPS = {
    'quiz_started': {'referrer', 'utm', 'entry_path'},
    'quiz_step_viewed': {'step_index', 'question_id'},
    'quiz_step_answered': {'step_index', 'question_id'},
    'quiz_submitted': {'step_count', 'free_text_used'},
    'plan_viewed': {'revisit'},
    'plan_step_expanded': {'step'},
    'product_clicked': {'shopify_id', 'step'},
    'whatsapp_requested': {'step', 'origin'},
    'feedback_submitted': {'rating'},
    'plan_exited': {'dwell_ms', 'deepest_step'},
    'product_added_to_cart': {'shopify_id', 'variant_id', 'quantity'},
    'checkout_completed': {'order_id'},
}


class JourneyEvent(StrictModel):
    id: UUID
    name: Short
    occurred_at: datetime
    props: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_event(self):
        if self.name not in EVENT_PROPS or set(self.props) - EVENT_PROPS[self.name]:
            raise ValueError('Unknown event or property')
        if self.occurred_at.tzinfo is None:
            raise ValueError('Timestamp needs a timezone')
        if len(json.dumps(self.props, ensure_ascii=False).encode('utf-8')) > 2048:
            raise ValueError('Properties exceed 2 KB')
        for key in ('step_index', 'step_count', 'dwell_ms', 'deepest_step', 'quantity'):
            if key in self.props and (type(self.props[key]) is not int or not 0 <= self.props[key] <= 86400000):
                raise ValueError(key + ' must be a nonnegative integer')
        for key in ('revisit', 'free_text_used'):
            if key in self.props and type(self.props[key]) is not bool:
                raise ValueError(key + ' must be a boolean')
        required = {'quiz_step_viewed': {'step_index', 'question_id'},
                    'quiz_step_answered': {'step_index', 'question_id'},
                    'product_clicked': {'shopify_id', 'step'}}
        if required.get(self.name, set()) - set(self.props):
            raise ValueError('Missing event properties')
        return self


class EventBatch(StrictModel):
    quiz_id: UUID | None = None
    plan_id: UUID | None = None
    events: list[JourneyEvent] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def has_identity(self):
        if self.quiz_id is None and self.plan_id is None:
            raise ValueError('quiz_id or plan_id required')
        return self


class CatalogProduct(StrictModel):
    sku: Annotated[str, Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_. -]+$')]
    shopify_id: Annotated[str, Field(pattern=r'^[0-9]+$', max_length=30)]
    variant_id: Annotated[str, Field(pattern=r'^[0-9]+$', max_length=30)]
    handle: Annotated[str, Field(pattern=r'^[a-z0-9][a-z0-9-]*$', max_length=255)]
    title: Short
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    available: bool


class CatalogBatch(StrictModel):
    sync_id: UUID
    generated_at: datetime
    mode: Literal['full', 'partial'] = 'full'
    products: list[CatalogProduct] = Field(min_length=1, max_length=2000)
    unmatched_matrix_skus: list[Short] = Field(default_factory=list, max_length=2000)

    @model_validator(mode='after')
    def unique_skus(self):
        if self.generated_at.tzinfo is None:
            raise ValueError('generated_at needs a timezone')
        if len({p.sku for p in self.products}) != len(self.products):
            raise ValueError('Duplicate SKU')
        return self


class ProductExplanation(StrictModel):
    sku: Short
    why: Annotated[str, Field(min_length=1, max_length=600)]


class StepExplanation(StrictModel):
    step: Short
    why: Annotated[str, Field(min_length=1, max_length=800)]
    products: list[ProductExplanation] = Field(max_length=3)


class PlanProse(StrictModel):
    summary: Annotated[str, Field(min_length=1, max_length=2000)]
    climate_note: str | None = Field(max_length=600)
    steps: list[StepExplanation] = Field(min_length=1, max_length=20)


ConcernCode = Literal['absorption_blocked', 'hold_loss', 'breakage_active',
                      'buildup_present', 'coated_feel', 'scalp_sensitivity']


class Concern(StrictModel):
    code: ConcernCode
    label: Short


class PlanProduct(StrictModel):
    sku: Short
    shopify_id: Short
    variant_id: Short
    handle: Annotated[str, Field(pattern=r'^[a-z0-9][a-z0-9-]*$', max_length=255)]
    name: Short
    price: Annotated[str, Field(pattern=r'^\d+(\.\d{1,2})?$')]
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    why: Annotated[str, Field(min_length=1, max_length=600)]


class PlanStep(StrictModel):
    order: int = Field(ge=1)
    step: Short
    title: Short
    why: Annotated[str, Field(min_length=1, max_length=800)]
    products: list[PlanProduct]


class PlanSnapshot(StrictModel):
    plan_id: UUID
    status: Literal['ready']
    created_at: datetime
    you_told_us: str | None
    summary: Annotated[str, Field(min_length=1, max_length=2000)]
    concerns: list[Concern]
    climate_note: str | None
    steps: list[PlanStep] = Field(min_length=1, max_length=20)
