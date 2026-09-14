"""Explicit supplier mock. Volatile records, no provider calls or email."""
import copy
from uuid import uuid4

from app.services.plans.store import now


class MockStore:
    def __init__(self):
        self.rows = {}
        self.submissions = {}
        self.feedback_rows = []
        self.event_rows = {}

    async def close(self):
        pass

    async def create(self, payload, mock=True):
        key = str(payload.submission_id)
        if key in self.submissions:
            return self.rows[self.submissions[key]], False
        if len(self.rows) >= 1000:
            raise RuntimeError('Mock capacity reached; restart the mock')
        row = {'plan_id': str(uuid4()), 'submission_id': key, 'email': payload.email,
               'status': 'pending', 'created_at': now().isoformat(), 'is_mock': True}
        self.rows[row['plan_id']] = row
        self.submissions[key] = row['plan_id']
        return row, True

    async def get(self, plan_id):
        return self.rows.get(str(plan_id))

    async def ready(self, plan_id, plan, diagnostics):
        row = self.rows[plan_id]
        if row['status'] != 'pending':
            return False
        row.update(status='ready', plan_json=copy.deepcopy(plan), diagnostics=diagnostics)
        return True

    async def fail(self, plan_id, reason):
        if self.rows[plan_id]['status'] == 'pending':
            self.rows[plan_id].update(status='failed', failure_code=reason)

    async def feedback(self, plan_id, payload):
        if len(self.feedback_rows) >= 10000:
            self.feedback_rows.pop(0)
        self.feedback_rows.append({'plan_id': str(plan_id), **payload.model_dump()})

    async def events(self, batch):
        if len(self.event_rows) >= 10000:
            self.event_rows.clear()
        for event in batch.events:
            self.event_rows.setdefault(str(event.id), event.model_dump())


class MockGenerator:
    async def build(self, request, row, diagnostics):
        return {'plan_id': row['plan_id'], 'status': 'ready', 'created_at': row['created_at'],
            'summary': 'This sample routine shows how your personal plan will appear.',
            'you_told_us': None, 'concerns': [], 'climate_note': None,
            'steps': [{'order': 1, 'step': 'cleanse', 'title': 'Cleanse',
                       'why': 'Start with a clean base for your routine.', 'products': [
                           {'sku': 'MOCK-CLEANSER', 'shopify_id': '100001', 'variant_id': '200001',
                            'handle': 'sample-cleanser', 'name': 'Sample Cleanser', 'price': '89.00',
                            'currency': 'AED', 'why': 'A sample product card for frontend development.'}]},
                      {'order': 2, 'step': 'condition', 'title': 'Condition',
                       'why': 'Follow with conditioning.', 'products': []}]}
