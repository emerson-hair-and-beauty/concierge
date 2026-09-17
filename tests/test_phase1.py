"""Offline contract and failure tests. No live database, model or email calls."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.plan import router
from app.services.decision_state.models import EnvironmentalContext, ProductFilters, SessionSignal
from app.services.plans.generator import PlanGenerator, detect, eligible, profile_for, retry_call, validate_prose
from app.services.plans.mock import MockGenerator, MockStore
from app.services.plans.models import CatalogBatch, EventBatch, PlanRequest
from app.services.plans.service import PlanService
from app.services.plans.store import PlanStore, now


def payload(**overrides):
    return {'submission_id': str(uuid4()), 'texture': '3B', 'density': 'medium',
            'email': 'test@example.com', **overrides}


def app_for(store=None, generator=None):
    app = FastAPI()
    app.include_router(router)
    app.state.plan_mock = True
    app.state.plan_service = PlanService(store or MockStore(), generator or MockGenerator())
    return app


def prose(context, steps):
    return {'summary': 'A routine based on your answers.', 'climate_note': None,
            'steps': [{'step': s['step'], 'why': 'This supports your routine.',
                       'products': [{'sku': p['sku'], 'why': 'Matches this step.'} for p in s['products']]}
                      for s in steps]}


class ContractTests(unittest.TestCase):
    def test_failed_plan_exposes_only_allowlisted_error(self):
        body = payload()
        plan_id = self.client.post('/api/plan', json=body).json()['plan_id']
        row = self.app.state.plan_service.store.rows[plan_id]
        for code in ('generation_failed', 'generation_timeout', 'worker_lost_or_deadline', 'secret detail'):
            row.update(status='failed', failure_code=code, diagnostics={'secret': 'private'})
            response = self.client.get('/api/plan/' + plan_id)
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertEqual(set(result), {'plan_id', 'status', 'error'})
            self.assertEqual(result['error']['code'], code if code != 'secret detail' else 'generation_failed')
            self.assertNotIn('private', response.text)
            self.assertNotIn('secret detail', response.text)

    def setUp(self):
        self.app = app_for()
        self.client = TestClient(self.app)

    def test_retry_returns_one_frozen_plan_and_no_private_fields(self):
        body = payload()
        first = self.client.post('/api/plan', json=body)
        self.assertEqual(first.status_code, 202)
        plan_id = first.json()['plan_id']
        again = self.client.post('/api/plan', json=body)
        self.assertEqual(again.json()['plan_id'], plan_id)
        self.assertEqual(len(self.app.state.plan_service.store.rows), 1)
        plan = self.client.get('/api/plan/' + plan_id)
        self.assertEqual(plan.json()['status'], 'ready')
        self.assertNotIn('email', plan.json())
        self.assertEqual(plan.content, self.client.get('/api/plan/' + plan_id).content)
        self.assertEqual(plan.headers['cache-control'], 'no-store')

    def test_unknown_and_invalid_inputs(self):
        self.assertEqual(self.client.get('/api/plan/' + str(uuid4())).status_code, 404)
        bad = self.client.post('/api/plan', json=payload(email='private-invalid'))
        self.assertEqual(bad.status_code, 422)
        self.assertNotIn('private-invalid', bad.text)
        self.assertEqual(self.client.post('/api/plan', json=payload(concern_text='x'*1001)).status_code, 422)
        body = payload()
        del body['submission_id']
        self.assertEqual(self.client.post('/api/plan', json=body).status_code, 422)

    @patch.dict(os.environ, {'PLAN_MODE': 'mock'})
    def test_standalone_startup_and_openapi(self):
        from app.phase1_main import app
        with TestClient(app) as client:
            schema = client.get('/openapi.json').json()
            self.assertIn('PlanRequest', schema['components']['schemas'])
            self.assertIn('requestBody', schema['paths']['/api/catalog']['post'])
            self.assertEqual(client.get('/api/phase1/health').json()['mode'], 'mock')
            self.assertEqual(client.post('/api/plan', json=payload()).status_code, 202)

    def test_text_beacon_is_deduplicated(self):
        event_id = str(uuid4())
        body = {'quiz_id': str(uuid4()), 'events': [{'id': event_id, 'name': 'quiz_started',
                'occurred_at': now().isoformat(), 'props': {'entry_path': '/quiz'}}]}
        for _ in range(2):
            self.assertEqual(self.client.post('/api/events', content=json.dumps(body),
                headers={'Content-Type': 'text/plain'}).status_code, 202)
        self.assertEqual(len(self.app.state.plan_service.store.event_rows), 1)
        body['events'][0]['name'] = 'plan_generated'
        self.assertEqual(self.client.post('/api/events', json=body).status_code, 422)

    def test_event_limits_and_unknown_properties(self):
        event = {'id': str(uuid4()), 'name': 'quiz_started', 'occurred_at': now().isoformat(), 'props': {}}
        body = {'quiz_id': str(uuid4()), 'events': [event]*51}
        self.assertEqual(self.client.post('/api/events', json=body).status_code, 422)
        body['events'] = [event | {'props': {'email': 'test@example.com'}}]
        self.assertEqual(self.client.post('/api/events', json=body).status_code, 422)

    def test_feedback_preserves_history_and_checks_membership(self):
        plan_id = self.client.post('/api/plan', json=payload()).json()['plan_id']
        path = '/api/plan/' + plan_id + '/feedback'
        for rating in ['somewhat', 'very_closely']:
            self.assertEqual(self.client.post(path, json={'rating': rating}).status_code, 202)
        self.assertEqual(len(self.app.state.plan_service.store.feedback_rows), 2)
        self.assertEqual(self.client.post(path, json={'rating': 'somewhat',
            'rejected_shopify_ids': ['999']}).status_code, 422)

    @patch.dict(os.environ, {'SHOPIFY_STORE_URL': 'https://store.example.com'})
    def test_redirect_does_not_double_count_frontend_click(self):
        plan_id = self.client.post('/api/plan', json=payload()).json()['plan_id']
        result = self.client.get(f'/api/plan/{plan_id}/go?shopify_id=100001', follow_redirects=False)
        self.assertEqual(result.status_code, 302)
        self.assertIn('https://store.example.com/products/sample-cleanser?plan_id=', result.headers['location'])
        self.assertFalse(self.app.state.plan_service.store.event_rows)
        self.assertEqual(self.client.get(f'/api/plan/{plan_id}/go?shopify_id=999',
                                       follow_redirects=False).status_code, 404)

    @patch.dict(os.environ, {'CATALOG_INGEST_TOKEN': 'test-token'})
    def test_catalog_authentication_happens_before_parsing(self):
        self.assertEqual(self.client.post('/api/catalog', content='bad').status_code, 401)
        self.assertEqual(self.client.post('/api/catalog', headers={'Authorization': 'Bearer test-token'},
                                         content='bad').status_code, 409)

    @patch.dict(os.environ, {'SHOPIFY_WEBHOOK_SECRET': 'test-secret'})
    def test_webhook_authentication_and_minimal_storage(self):
        self.app.state.plan_mock = False
        self.app.state.plan_service.store.request = AsyncMock(return_value=None)
        raw = json.dumps({'id': 10, 'email': 'private@example.com', 'note_attributes': [], 'line_items': []}).encode()
        path = '/api/webhooks/shopify/orders-paid'
        self.assertEqual(self.client.post(path, content=raw).status_code, 401)
        sig = base64.b64encode(hmac.new(b'test-secret', raw, hashlib.sha256).digest()).decode()
        response = self.client.post(path, content=raw,
            headers={'x-shopify-hmac-sha256': sig, 'x-shopify-topic': 'orders/paid'})
        self.assertEqual(response.status_code, 200)
        stored = self.app.state.plan_service.store.request.call_args.kwargs['body']
        self.assertNotIn('private@example.com', json.dumps(stored))


class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def run_job(self, build):
        store = MockStore()
        request = PlanRequest(**payload())
        row, _ = await store.create(request)
        generator = MockGenerator()
        generator.build = build
        worker = PlanService(store, generator)
        worker.generation_budget = 0.03
        worker.total_budget = 0.05
        await worker.generate(request, dict(row))
        return row, store

    async def test_fatal_error_is_persisted_without_waiting_for_sweeper(self):
        started = time.monotonic()
        row, _ = await self.run_job(AsyncMock(side_effect=ValueError('bad schema')))
        self.assertEqual(row['status'], 'failed')
        self.assertLess(time.monotonic() - started, 0.5)

    async def test_hung_generation_is_cancelled_and_failed(self):
        cancelled = asyncio.Event()
        async def hang(*args):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        row, _ = await self.run_job(hang)
        self.assertEqual(row['failure_code'], 'generation_timeout')
        self.assertTrue(cancelled.is_set())

    async def test_late_completion_cannot_replace_failure(self):
        row, store = await self.run_job(AsyncMock(side_effect=TimeoutError()))
        self.assertFalse(await store.ready(row['plan_id'], {'summary': 'late'}, []))
        self.assertEqual(row['status'], 'failed')

    async def test_email_failure_does_not_regenerate_or_fail_saved_plan(self):
        store = MockStore()
        store.rpc = AsyncMock(side_effect=[{'plan_id': str(uuid4()), 'claim_id': str(uuid4()), 'attempts': 1}, None])
        generator = MockGenerator()
        generator.build = AsyncMock()
        service = PlanService(store, generator, email_sender=AsyncMock(side_effect=TimeoutError()))
        await service.deliver_one()
        self.assertEqual(store.rpc.call_args.kwargs['p_error'], 'TimeoutError')
        generator.build.assert_not_called()

    async def test_only_transient_errors_retry(self):
        call = AsyncMock(side_effect=[TimeoutError(), 'ok'])
        self.assertEqual(await retry_call(call, seconds=1), 'ok')
        self.assertEqual(call.await_count, 2)
        call = AsyncMock(side_effect=ValueError())
        with self.assertRaises(ValueError):
            await retry_call(call)
        self.assertEqual(call.await_count, 1)

    async def test_empty_concern_skips_provider(self):
        signal = await detect('  ')
        self.assertFalse(signal.breakage_active)
        self.assertEqual(signal.confidence_score, 1)

    async def test_product_and_weather_outages_keep_valid_routine(self):
        request = PlanRequest(**payload(concern_text='hair is snapping'))
        store = MockStore()
        row, _ = await store.create(request)
        generator = PlanGenerator(store,
            detect_fn=AsyncMock(return_value=SessionSignal(breakage_active=True, evidence_quote='hair is snapping')),
            search_fn=AsyncMock(side_effect=ValueError('no index')),
            environment_fn=AsyncMock(side_effect=TimeoutError()),
            compose_fn=AsyncMock(side_effect=prose))
        diagnostics = []
        result = await generator.build(request, row, diagnostics)
        self.assertEqual(result['steps'][0]['step'], 'gentle_cleanse')
        self.assertTrue(all(not step['products'] for step in result['steps']))
        self.assertIsNone(result['climate_note'])
        self.assertEqual(result['concerns'][0]['code'], 'breakage_active')

    async def test_catalog_join_uses_verified_commercial_fields_and_drops_stale_stock(self):
        request = PlanRequest(**payload(porosity='medium'))
        store = MockStore()
        row, _ = await store.create(request)
        fresh = {'sku': 'A', 'shopify_id': '1', 'variant_id': '2', 'handle': 'cleanser',
                 'title': 'Store title', 'price': '12.00', 'currency': 'AED',
                 'available': True, 'source_at': now().isoformat()}
        store.catalog = AsyncMock(return_value={
            'A': fresh,
            'B': {**fresh, 'sku': 'B', 'source_at': (now()-timedelta(hours=25)).isoformat()},
            'C': {**fresh, 'sku': 'C', 'available': False}})
        generator = PlanGenerator(store, detect_fn=AsyncMock(return_value=SessionSignal()),
            search_fn=AsyncMock(return_value=[{'metadata': {'sku': sku}} for sku in ['A','B','C']]),
            environment_fn=AsyncMock(return_value=EnvironmentalContext()), compose_fn=AsyncMock(side_effect=prose))
        result = await generator.build(request, row, [])
        for step in result['steps']:
            self.assertEqual([p['sku'] for p in step['products']], ['A'])
            self.assertEqual(step['products'][0]['name'], 'Store title')
            self.assertEqual(step['products'][0]['variant_id'], '2')

    async def test_detector_failure_cannot_become_a_profile_only_plan(self):
        request = PlanRequest(**payload(concern_text='My hair is snapping.'))
        store = MockStore()
        row, _ = await store.create(request)
        generator = PlanGenerator(store, detect_fn=AsyncMock(side_effect=ValueError('invalid detector output')),
            environment_fn=AsyncMock(return_value=EnvironmentalContext()), compose_fn=AsyncMock())
        await PlanService(store, generator).generate(request, dict(row))
        self.assertEqual(row['status'], 'failed')
        generator.compose.assert_not_called()

    async def test_concurrent_work_does_not_block_polls(self):
        for count in (8, 25):
            store = MockStore()
            gate = asyncio.Event()
            async def build(request, row, diagnostics):
                await gate.wait()
                return await MockGenerator().build(request, row, diagnostics)
            worker = PlanService(store, type('Generator', (), {'build': staticmethod(build)})())
            jobs = []
            for _ in range(count):
                request = PlanRequest(**payload())
                row, _ = await store.create(request)
                jobs.append(asyncio.create_task(worker.generate(request, dict(row))))
            await asyncio.sleep(0)
            worst = 0
            for plan_id in store.rows:
                start = time.monotonic()
                self.assertEqual((await store.get(plan_id))['status'], 'pending')
                worst = max(worst, time.monotonic() - start)
            gate.set()
            await asyncio.gather(*jobs)
            self.assertLess(worst, .5)

    async def test_invalid_composer_uses_rule_based_fallback_without_invented_products(self):
        store = MockStore()
        request = PlanRequest(**payload())
        row, _ = await store.create(request)
        generator = PlanGenerator(store, detect_fn=AsyncMock(return_value=SessionSignal()),
            search_fn=AsyncMock(return_value=[]), environment_fn=AsyncMock(return_value=EnvironmentalContext()),
            compose_fn=AsyncMock(return_value={'summary': 'bad schema'}))
        diagnostics = []
        result = await generator.build(request, row, diagnostics)
        self.assertTrue(result['summary'])
        self.assertTrue(all(not s['products'] for s in result['steps']))
        self.assertTrue(any(d.get('code') == 'rule_based_fallback' for d in diagnostics))


class SelectionTests(unittest.TestCase):
    def test_explicit_porosity_wins_and_unknown_is_not_invented(self):
        diagnostics = []
        profile = profile_for(PlanRequest(**payload(porosity='high', moisture_behaviour='Low Porosity')), diagnostics)
        self.assertEqual(profile.porosity, 'high')
        self.assertTrue(diagnostics[0]['conflict'])
        self.assertEqual(profile_for(PlanRequest(**payload()), []).porosity, 'unknown')

    def test_composer_cannot_invent_product_or_reorder_steps(self):
        steps = [{'step': 'cleanse', 'products': []}]
        invalid = {'summary': 'Test', 'climate_note': None,
                   'steps': [{'step': 'cleanse', 'why': 'Test', 'products': [{'sku': 'invented', 'why': 'Test'}]}]}
        with self.assertRaises(ValueError):
            validate_prose(invalid, steps)
        invalid['steps'][0].update(step='style', products=[])
        with self.assertRaises(ValueError):
            validate_prose(invalid, steps)

    def test_unknown_required_flags_do_not_become_soft_preferences(self):
        metadata = {'category': 'Treatment', 'flags': ['protein'], 'porosity': ['high']}
        self.assertFalse(eligible(metadata, ['Treatment'], ProductFilters(required_flags=['bond_builder'])))
        self.assertFalse(eligible(metadata, ['Cleanser'], ProductFilters()))
        self.assertFalse(eligible(metadata, ['Treatment'], ProductFilters(forbidden_flags=['protein'])))

    def test_styler_hold_and_density_are_hard_constraints(self):
        metadata = {'category': 'Styler', 'hold': 'soft', 'density': ['fine']}
        self.assertFalse(eligible(metadata, ['Styler'], ProductFilters(ideal_hold_level='strong')))
        self.assertFalse(eligible(metadata, ['Styler'], ProductFilters(), density='high'))

    def test_duplicate_catalog_skus_are_rejected(self):
        item = {'sku': 'A', 'shopify_id': '1', 'variant_id': '2', 'handle': 'a', 'title': 'A',
                'price': '12.00', 'currency': 'AED', 'available': True}
        with self.assertRaises(ValidationError):
            CatalogBatch(sync_id=uuid4(), generated_at=now(), products=[item, item])


class StoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_fatal_error_persists_sanitized_diagnostics_and_logs(self):
        store = MockStore()
        request = PlanRequest(**payload())
        row, _ = await store.create(request)
        async def build(request, row, diagnostics):
            diagnostics.append({'stage': 'detector', 'signals': {'quote': 'private-answer'}})
            raise httpx.HTTPStatusError('secret-token private-answer',
                request=httpx.Request('POST', 'https://provider.example/secret-token'),
                response=httpx.Response(401, text='secret-token'))
        generator = type('Generator', (), {'build': staticmethod(build)})()
        with self.assertLogs('app.services.plans.service', level='ERROR') as logs:
            await PlanService(store, generator).generate(request, dict(row))
        details = row['diagnostics'][-1]
        self.assertEqual(details['http_status'], 401)
        self.assertEqual(details['stage'], 'generation')
        self.assertEqual(details['error_type'], 'HTTPStatusError')
        self.assertTrue(details['frames'])
        output = json.dumps(row['diagnostics']) + str(logs.output)
        self.assertNotIn('secret-token', output)
        self.assertNotIn('private-answer', output)

    @patch.dict(os.environ, {'SUPABASE_URL': 'https://db.example.com', 'SUPABASE_KEY': 'test'})
    async def test_failure_patch_persists_diagnostics_only_for_pending_plan(self):
        calls = []
        async def handler(request):
            calls.append(request)
            return httpx.Response(200, json=[])
        store = PlanStore(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        diagnostics = [{'stage': 'persistence', 'error_type': 'HTTPStatusError', 'http_status': 403}]
        await store.fail(uuid4(), 'generation_failed', diagnostics)
        self.assertEqual(json.loads(calls[0].content)['diagnostics'], diagnostics)
        self.assertEqual(calls[0].url.params['status'], 'eq.pending')
        await store.close()

    @patch.dict(os.environ, {'SUPABASE_URL': 'https://db.example.com', 'SUPABASE_KEY': 'test'})
    async def test_submission_uniqueness_is_a_database_upsert(self):
        calls = []
        async def handler(request):
            calls.append(request)
            if request.method == 'POST':
                return httpx.Response(201, json=[])
            return httpx.Response(200, json=[{'plan_id': 'existing', 'status': 'ready'}])
        store = PlanStore(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        row, created = await store.create(PlanRequest(**payload()))
        self.assertFalse(created)
        self.assertEqual(row['plan_id'], 'existing')
        self.assertIn('resolution=ignore-duplicates', calls[0].headers['Prefer'])
        self.assertEqual(calls[0].url.params['on_conflict'], 'submission_id')
        await store.close()


if __name__ == '__main__':
    unittest.main()
