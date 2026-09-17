"""Print deployed HTTPS responses; save the complete transcript locally."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

BASE = 'https://concierge-jzf8.onrender.com'
transcript = []


def emit(value):
    value = str(value)
    print(value, flush=True)
    transcript.append(value)


def request(client, method, path, **kwargs):
    emit('\n' + method + ' ' + BASE + path)
    if 'json' in kwargs:
        emit('Request: ' + json.dumps(kwargs['json']))
    try:
        response = client.request(method, BASE + path, **kwargs)
        emit('HTTP ' + str(response.status_code))
        emit('Content-Type: ' + response.headers.get('content-type', '(none)'))
        if 'location' in response.headers:
            emit('Location: ' + response.headers['location'])
        try:
            emit(json.dumps(response.json(), indent=2))
        except ValueError:
            emit(response.text or '(empty response body)')
        return response
    except httpx.HTTPError as error:
        emit(type(error).__name__ + ': ' + str(error))
        return None


def main():
    quiz_id = str(uuid4())
    plan_id = str(uuid4())
    plan = {}
    with httpx.Client(timeout=45, follow_redirects=False) as client:
        request(client, 'GET', '/health')
        health = request(client, 'GET', '/api/phase1/health')
        mock = health is not None and health.status_code == 200 and health.json().get('mode') == 'mock'
        payload = {'submission_id': str(uuid4()), 'quiz_id': quiz_id,
                   'texture': '3B', 'density': 'medium', 'porosity': 'low',
                   'email': 'https-smoke@example.invalid', 'marketing_consent': False,
                   'source': 'https_smoke_test'}
        if not mock:
            emit('Live/unknown mode: testing submission validation with an empty payload.')
        submitted = request(client, 'POST', '/api/plan', json=payload if mock else {})
        if submitted is not None and submitted.status_code == 202:
            plan_id = submitted.json()['plan_id']
        for attempt in range(20):
            fetched = request(client, 'GET', '/api/plan/' + plan_id)
            if fetched is None or fetched.status_code != 200:
                break
            plan = fetched.json()
            if plan.get('status') != 'pending':
                break
            time.sleep(2)
        request(client, 'POST', '/api/plan/' + plan_id + '/feedback',
                json={'rating': 'somewhat', 'note': 'Synthetic HTTPS smoke test'})
        event = {'quiz_id': quiz_id, 'events': [{'id': str(uuid4()),
                 'name': 'quiz_started', 'occurred_at': datetime.now(timezone.utc).isoformat(),
                 'props': {'entry_path': '/https-smoke-test'}}]}
        request(client, 'POST', '/api/events', json=event if mock else {})
        request(client, 'POST', '/api/events', content=json.dumps(event if mock else {}),
                headers={'Content-Type': 'text/plain'})
        emit('Catalog test: unauthenticated request; no catalog import.')
        request(client, 'POST', '/api/catalog', json={})
        products = [p for step in plan.get('steps', []) for p in step.get('products', [])]
        shopify_id = products[0]['shopify_id'] if products else '0'
        request(client, 'GET', '/api/plan/' + plan_id + '/go', params={'shopify_id': shopify_id})
        emit('Webhook test: unsigned request; checks rejection, not paid-order processing.')
        request(client, 'POST', '/api/webhooks/shopify/orders-paid', json={})
        request(client, 'GET', '/docs')
        request(client, 'GET', '/openapi.json')


if __name__ == '__main__':
    try:
        main()
    finally:
        output = Path(__file__).resolve().parents[1] / 'tests' / 'phase1_https_responses.txt'
        output.write_text('\n'.join(transcript), encoding='utf-8')
        print('\nFull response transcript: ' + str(output), flush=True)
