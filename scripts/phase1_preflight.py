"""Read-only checks for the live catalog source and Phase 1 database migration."""
import asyncio
import os
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv


async def main():
    load_dotenv(Path(__file__).resolve().parents[1] / 'app' / '.env')
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            key = os.environ['PINECONE_API_KEY']
            index = os.getenv('PINECONE_INDEX', 'concierge-knowledge-base')
            response = await client.get('https://api.pinecone.io/indexes/' + index,
                                        headers={'Api-Key': key})
            response.raise_for_status()
            info = response.json()
            host = info['host']
            stats = await client.post('https://' + host + '/describe_index_stats',
                                     headers={'Api-Key': key}, json={})
            stats.raise_for_status()
            namespaces = stats.json().get('namespaces', {})
            print('Pinecone: read-only index description succeeded; dimension=', info['dimension'])
            for namespace in namespaces:
                result = await client.post('https://' + host + '/query', headers={'Api-Key': key},
                    json={'namespace': namespace, 'vector': [0.01] * info['dimension'],
                          'topK': 1000, 'includeMetadata': True})
                result.raise_for_status()
                matches = result.json().get('matches', [])
                print('Namespace:', repr(namespace), 'sample:', len(matches),
                      'SKU metadata:', sum(bool(m.get('metadata', {}).get('sku')) for m in matches),
                      'category metadata:', sum(bool(m.get('metadata', {}).get('category')) for m in matches),
                      'metadata keys:', sorted({k for m in matches for k in m.get('metadata', {})}))
                print('Categories:', dict(Counter(m.get('metadata', {}).get('category') or '(missing)' for m in matches)))
                print('Flag vocabulary:', sorted({f for m in matches for f in m.get('metadata', {}).get('flags', [])}))
            # The host is a public service address, not a credential.
            print('PINECONE_HOST=' + host)
        except Exception as error:
            print('Pinecone preflight failed:', type(error).__name__)
        try:
            key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.environ['SUPABASE_KEY']
            result = await client.get(os.environ['SUPABASE_URL'].rstrip('/') + '/rest/v1/plans',
                headers={'apikey': key, 'Authorization': 'Bearer ' + key},
                params={'select': 'plan_id', 'limit': '0'})
            print('Phase 1 plans table HTTP status:', result.status_code)
        except Exception as error:
            print('Database preflight failed:', type(error).__name__)


if __name__ == '__main__':
    asyncio.run(main())
