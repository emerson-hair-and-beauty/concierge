"""Mount the same API in the existing app or the standalone supplier service."""
import asyncio
import os
from contextlib import asynccontextmanager

from app.api.plan import router
from app.services.plans.mock import MockGenerator, MockStore
from app.services.plans.service import PlanService
from app.services.plans.store import PlanStore
from app.services.plans.models import PlanRequest, Feedback, EventBatch, CatalogBatch, PlanSnapshot


def install(app, enabled=True):
    app.include_router(router)

    from fastapi.openapi.utils import get_openapi
    from pydantic.json_schema import models_json_schema

    def openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        _, definitions = models_json_schema(
            [(model, 'validation') for model in (PlanRequest, Feedback, EventBatch, CatalogBatch, PlanSnapshot)],
            ref_template='#/components/schemas/{model}')
        schema.setdefault('components', {}).setdefault('schemas', {}).update(definitions['$defs'])
        inputs = {'/api/plan': PlanRequest, '/api/plan/{plan_id}/feedback': Feedback,
                  '/api/events': EventBatch, '/api/catalog': CatalogBatch}
        for path, model in inputs.items():
            content = {'application/json': {'schema': {'$ref': '#/components/schemas/' + model.__name__}}}
            if model is EventBatch:
                content['text/plain'] = content['application/json']
            schema['paths'][path]['post']['requestBody'] = {'required': True, 'content': content}
        schema['components'].setdefault('securitySchemes', {}).update({'CatalogToken': {'type': 'http', 'scheme': 'bearer'}})
        schema['paths']['/api/catalog']['post']['security'] = [{'CatalogToken': []}]
        schema['paths']['/api/plan/{plan_id}']['get']['responses']['200']['content'] = {
            'application/json': {'schema': {'anyOf': [
                {'$ref': '#/components/schemas/PlanSnapshot'},
                {'type': 'object', 'required': ['plan_id', 'status'], 'properties': {
                    'plan_id': {'type': 'string', 'format': 'uuid'},
                    'status': {'type': 'string', 'enum': ['pending', 'failed']}}}]}}}
        app.openapi_schema = schema
        return schema

    app.openapi = openapi

    async def start_plans():
        if os.getenv('PLAN_MODE', 'live') not in ('mock', 'live'):
            raise ValueError('PLAN_MODE must be mock or live')
        app.state.plan_mock = os.getenv('PLAN_MODE', 'live') == 'mock'
        app.state.plan_workers = []
        if not enabled:
            return
        mock = app.state.plan_mock
        store = MockStore() if mock else PlanStore()
        app.state.plan_service = PlanService(store, MockGenerator() if mock else None)
        if not mock:
            app.state.plan_workers = [
                asyncio.create_task(app.state.plan_service.sweep_loop()),
                asyncio.create_task(app.state.plan_service.email_loop()),
            ]

    async def stop_plans():
        for task in getattr(app.state, 'plan_workers', []):
            task.cancel()
        await asyncio.gather(*getattr(app.state, 'plan_workers', []), return_exceptions=True)
        if getattr(app.state, 'plan_service', None):
            await app.state.plan_service.store.close()

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application) as state:
            await start_plans()
            try:
                yield state
            finally:
                await stop_plans()

    app.router.lifespan_context = lifespan

    @app.get('/api/phase1/health', tags=['Phase 1'])
    async def phase1_health():
        mock = getattr(app.state, 'plan_mock', False)
        required = ['SUPABASE_URL', 'CATALOG_INGEST_TOKEN', 'PINECONE_HOST',
                    'PINECONE_API_KEY', 'KLAVIYO_API_KEY', 'PLAN_PUBLIC_URL_TEMPLATE']
        missing = [name for name in required if not os.getenv(name)]
        if not (os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_KEY')):
            missing.append('SUPABASE_SERVICE_ROLE_KEY')
        if os.getenv('LLM_PROVIDER', 'openai') == 'openai':
            if not (os.getenv('OPENAI_API_KEY') or os.getenv('OPEN_AI_KEY')):
                missing.append('OPENAI_API_KEY')
        elif not os.getenv('GEMINI_API_KEY'):
            missing.append('GEMINI_API_KEY')
        return {'enabled': enabled, 'mode': 'mock' if mock else 'live',
                'configured': enabled and (mock or not missing),
                'missing_settings': [] if mock else missing}
