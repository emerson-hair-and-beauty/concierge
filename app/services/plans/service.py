"""Bounded background generation and durable email delivery."""
import asyncio
import logging
import os
from datetime import datetime
from urllib.parse import urlsplit

import httpx

from app.services.plans.generator import PlanGenerator
from app.services.plans.store import now

log = logging.getLogger(__name__)


async def send_plan_email(job):
    template = os.environ['PLAN_PUBLIC_URL_TEMPLATE']
    link = template.format(plan_id=job['plan_id'])
    if urlsplit(link).scheme != 'https' or not urlsplit(link).netloc:
        raise ValueError('Plan link must be an absolute HTTPS URL')
    headers = {'Authorization': 'Klaviyo-API-Key ' + os.environ['KLAVIYO_API_KEY'],
               'revision': os.getenv('KLAVIYO_REVISION', '2026-07-15'),
               'Content-Type': 'application/json'}
    profile = {'type': 'profile', 'attributes': {'email': job['email']}}
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post('https://a.klaviyo.com/api/profile-import', headers=headers,
            json={'data': profile})
        response.raise_for_status()
        response = await client.post('https://a.klaviyo.com/api/events', headers=headers, json={
            'data': {'type': 'event', 'attributes': {
                'unique_id': 'curl-plan-ready:' + job['plan_id'],
                'properties': {'plan_id': job['plan_id'], 'plan_url': link,
                               'marketing_consent': job['marketing_consent']},
                'metric': {'data': {'type': 'metric', 'attributes': {'name': 'curl_plan_ready'}}},
                'profile': {'data': profile}}}})
        response.raise_for_status()


class PlanService:
    def __init__(self, store, generator=None, email_sender=send_plan_email):
        self.store = store
        self.generator = generator or PlanGenerator(store)
        self.email_sender = email_sender
        self.generation_budget = 25.0
        self.total_budget = 30.0
        self.active = 0

    async def run_reserved(self, payload, row):
        try:
            await self.generate(payload, row)
        finally:
            self.active -= 1

    async def generate(self, payload, row):
        diagnostics = []
        age = (now() - datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))).total_seconds()
        try:
            if age >= self.generation_budget:
                raise TimeoutError('Generation started after deadline')
            async with asyncio.timeout(self.generation_budget - max(age, 0)):
                plan = await self.generator.build(payload, row, diagnostics)
            remaining = self.total_budget - (now() - datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))).total_seconds()
            if remaining <= 0:
                raise TimeoutError('Generation exceeded total deadline')
            async with asyncio.timeout(remaining):
                saved = await self.store.ready(row['plan_id'], plan, diagnostics)
            if not saved:
                raise TimeoutError('Plan completion rejected after deadline or terminal state')
            log.info('Plan ready plan_id=%s elapsed=%.3f degradations=%s', row['plan_id'],
                     self.total_budget - remaining, diagnostics)
        except asyncio.CancelledError:
            # A process kill is recovered by the durable sweeper on startup.
            raise
        except Exception as error:
            code = 'generation_timeout' if isinstance(error, TimeoutError) else 'generation_failed'
            log.error('Plan failed plan_id=%s code=%s error_type=%s diagnostics=%s',
                      row['plan_id'], code, type(error).__name__, diagnostics)
            try:
                await self.store.fail(row['plan_id'], code)
            except Exception as persistence_error:
                log.error('Failure status NOT saved plan_id=%s error_type=%s',
                          row['plan_id'], type(persistence_error).__name__)

    async def sweep_loop(self):
        while True:
            started = asyncio.get_running_loop().time()
            try:
                affected = await self.store.sweep()
                if affected:
                    log.error('Abandoned plans marked failed count=%s', affected)
            except Exception as error:
                log.error('Plan sweeper failed error_type=%s', type(error).__name__)
            await asyncio.sleep(max(0, 5 - (asyncio.get_running_loop().time() - started)))

    async def deliver_one(self):
        job = await self.store.rpc('phase1_claim_email')
        if not job:
            return False
        failure = None
        try:
            async with asyncio.timeout(15):
                await self.email_sender(job)
        except Exception as error:
            failure = type(error).__name__
            log.error('Plan email failed plan_id=%s attempt=%s error_type=%s',
                      job['plan_id'], job['attempts'], failure)
        await self.store.rpc('phase1_email_result', p_plan_id=job['plan_id'],
                             p_claim_id=job['claim_id'], p_error=failure)
        return True

    async def email_loop(self):
        while True:
            try:
                if os.getenv('KLAVIYO_API_KEY') and os.getenv('PLAN_PUBLIC_URL_TEMPLATE'):
                    if await self.deliver_one():
                        continue
            except Exception as error:
                log.error('Email worker failed error_type=%s', type(error).__name__)
            await asyncio.sleep(5)
