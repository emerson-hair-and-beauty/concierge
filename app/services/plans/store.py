"""Async PostgREST access. Mutations requiring atomicity use SQL functions."""
import os
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import httpx


def now():
    return datetime.now(timezone.utc)


class PlanStore:
    def __init__(self, client=None):
        self.client = client or httpx.AsyncClient(timeout=3.0)

    async def close(self):
        await self.client.aclose()

    async def request(self, method, path, *, params=None, body=None, prefer=None):
        url = os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/' + path
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY']
        headers = {'apikey': key, 'Authorization': f'Bearer {key}'}
        if prefer:
            headers['Prefer'] = prefer
        async with asyncio.timeout(3):
            response = await self.client.request(method, url, params=params, json=body, headers=headers)
        response.raise_for_status()
        return response.json() if response.content else None

    async def rpc(self, name, **params):
        return await self.request('POST', 'rpc/' + name, body=params)

    async def create(self, payload, mock=False):
        row = {'plan_id': str(uuid4()), 'anonymous_user_id': str(uuid4()),
               'submission_id': str(payload.submission_id),
               'quiz_id': str(payload.quiz_id) if payload.quiz_id else None,
               'email': payload.email, 'marketing_consent': payload.marketing_consent,
               'source': payload.source, 'is_mock': mock}
        inserted = await self.request('POST', 'plans', params={'on_conflict': 'submission_id'},
                                      body=row, prefer='resolution=ignore-duplicates,return=representation')
        if inserted:
            return inserted[0], True
        existing = await self.request('GET', 'plans', params={
            'submission_id': 'eq.' + str(payload.submission_id), 'limit': '1'})
        return existing[0], False

    async def get(self, plan_id):
        rows = await self.request('GET', 'plans', params={'plan_id': 'eq.' + str(plan_id), 'limit': '1'})
        return rows[0] if rows else None

    async def ready(self, plan_id, plan, diagnostics):
        return await self.rpc('phase1_finish_plan', p_plan_id=str(plan_id),
                              p_plan=plan, p_diagnostics=diagnostics)

    async def fail(self, plan_id, reason):
        return await self.request('PATCH', 'plans', params={
            'plan_id': 'eq.' + str(plan_id), 'status': 'eq.pending'}, body={
            'status': 'failed', 'failure_code': reason, 'completed_at': now().isoformat()},
            prefer='return=representation')

    async def sweep(self):
        return await self.rpc('phase1_sweep_plans')

    async def feedback(self, plan_id, payload):
        await self.request('POST', 'plan_feedback', body={
            'plan_id': str(plan_id), **payload.model_dump(mode='json')})

    async def events(self, batch):
        envelope = batch.model_dump(mode='json')
        rows = [{**e, 'quiz_id': envelope['quiz_id'], 'plan_id': envelope['plan_id']}
                for e in envelope['events']]
        await self.request('POST', 'journey_events', params={'on_conflict': 'id'}, body=rows,
                           prefer='resolution=ignore-duplicates')

    async def catalog(self, skus):
        if not skus:
            return {}
        rows = await self.request('GET', 'catalog', params={
            'sku': 'in.(' + ','.join('"' + sku + '"' for sku in skus) + ')',
            'available': 'eq.true'})
        return {r['sku']: r for r in rows}

    async def ingest(self, payload):
        return await self.rpc('phase1_ingest_catalog', p_batch=payload.model_dump(mode='json'))
