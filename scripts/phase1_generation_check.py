"""Ten synthetic live-model runs. No database writes or email sends.

Catalog is deliberately empty until a development database is available. These
timings cover detection, read-only search and composition, not full delivery.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / 'app' / '.env')

from app.services.plans.generator import PlanGenerator
from app.services.plans.models import PlanRequest
from app.services.plans.store import now


class NoCatalog:
    async def catalog(self, skus):
        return {}


async def main():
    import httpx
    if not os.getenv('PINECONE_HOST'):
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get('https://api.pinecone.io/indexes/' + os.getenv('PINECONE_INDEX', 'concierge-knowledge-base'),
                                        headers={'Api-Key': os.environ['PINECONE_API_KEY']})
            response.raise_for_status()
            os.environ['PINECONE_HOST'] = response.json()['host']
    cases = ['', 'My hair snaps when I detangle.', 'My curls drop by noon.',
             'My hair feels waxy and coated.', 'My scalp reacts to products.'] * 2
    generator = PlanGenerator(NoCatalog())
    results = []
    for index, text in enumerate(cases):
        request = PlanRequest(submission_id=uuid4(), texture='3B', density='medium',
            email='synthetic@example.com', porosity='medium', concern_text=text)
        row = {'plan_id': str(uuid4()), 'created_at': now().isoformat()}
        start = time.monotonic()
        try:
            async with asyncio.timeout(25):
                plan = await generator.build(request, row, [])
            result = {'case': index + 1, 'status': 'ready', 'seconds': round(time.monotonic()-start, 3),
                      'steps': [s['step'] for s in plan['steps']]}
        except Exception as error:
            result = {'case': index + 1, 'status': 'failed', 'seconds': round(time.monotonic()-start, 3),
                      'error_type': type(error).__name__}
        results.append(result)
        print(json.dumps(result), flush=True)
    output = Path(__file__).resolve().parents[1] / 'tests' / 'phase1_generation_results.json'
    output.write_text(json.dumps({'scope': 'Live models and search; empty catalog; no persistence or email',
                                  'results': results}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
