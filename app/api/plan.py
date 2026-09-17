"""Public quiz endpoints and authenticated supplier catalog ingestion."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.services.plans.models import CatalogBatch, EventBatch, Feedback, PlanRequest
from app.services.plans.errors import public_error

router = APIRouter(tags=['Phase 1'])
log = logging.getLogger(__name__)


def service(request):
    instance = getattr(request.app.state, 'plan_service', None)
    if instance is None:
        raise HTTPException(503, 'Plan service is not enabled')
    return instance


async def body_bytes(request, limit):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(413, 'Request is too large')
    return bytes(data)


async def parse(request, model, limit=16000):
    try:
        return model.model_validate_json(await body_bytes(request, limit))
    except ValidationError as error:
        # Do not echo the customer's email or free text in validation responses.
        raise HTTPException(422, [{'loc': e['loc'], 'msg': e['msg']} for e in error.errors()]) from None


async def database(call):
    try:
        return await call
    except httpx.HTTPStatusError:
        log.error('Phase 1 database rejected request')
        raise HTTPException(503, 'Storage is temporarily unavailable') from None
    except (httpx.TransportError, TimeoutError, KeyError, RuntimeError):
        raise HTTPException(503, 'Storage is temporarily unavailable') from None


async def require_plan(request, plan_id, ready=False):
    row = await database(service(request).store.get(plan_id))
    if not row:
        raise HTTPException(404, 'Plan not found')
    if ready and row['status'] != 'ready':
        raise HTTPException(409, 'Plan is not ready')
    return row


@router.post('/api/plan', status_code=202)
async def submit(request: Request, tasks: BackgroundTasks):
    payload = await parse(request, PlanRequest)
    worker = service(request)
    if worker.active >= 25:
        raise HTTPException(429, 'Please retry shortly', headers={'Retry-After': '5'})
    worker.active += 1
    try:
        row, created = await database(worker.store.create(payload, mock=request.app.state.plan_mock))
    except BaseException:
        worker.active -= 1
        raise
    if created:
        tasks.add_task(worker.run_reserved, payload, dict(row))
    else:
        worker.active -= 1
    return {'plan_id': row['plan_id'], 'status': row['status']}


@router.get('/api/plan/{plan_id}')
async def read_plan(plan_id: UUID, request: Request, response: Response):
    row = await require_plan(request, plan_id)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    if row['status'] == 'ready':
        return row['plan_json']
    result = {'plan_id': row['plan_id'], 'status': row['status']}
    if row['status'] == 'failed':
        result['error'] = public_error(row.get('failure_code'))
    return result


@router.post('/api/plan/{plan_id}/feedback', status_code=202)
async def feedback(plan_id: UUID, request: Request):
    payload = await parse(request, Feedback)
    row = await require_plan(request, plan_id, ready=True)
    steps = row['plan_json']['steps']
    products = {p['shopify_id'] for step in steps for p in step['products']}
    if set(payload.rejected_shopify_ids) - products or (
        payload.unclear_step and payload.unclear_step not in {s['step'] for s in steps}):
        raise HTTPException(422, 'Feedback references an unknown product or step')
    await database(service(request).store.feedback(plan_id, payload))
    return Response(status_code=202)


async def save_events(store, batch):
    try:
        await store.events(batch)
    except Exception as error:
        log.error('Journey batch NOT saved events=%s error_type=%s', len(batch.events), type(error).__name__)


@router.post('/api/events', status_code=202)
async def events(request: Request, tasks: BackgroundTasks):
    batch = await parse(request, EventBatch, 120000)
    worker = service(request)
    if batch.plan_id:
        row = await require_plan(request, batch.plan_id)
        products = {p['shopify_id'] for s in (row.get('plan_json') or {}).get('steps', []) for p in s['products']}
        if any(e.name == 'product_clicked' and e.props.get('shopify_id') not in products for e in batch.events):
            raise HTTPException(422, 'Click references a product outside this plan')
    elif any(e.name == 'product_clicked' for e in batch.events):
        raise HTTPException(422, 'Product clicks require plan_id')
    tasks.add_task(save_events, worker.store, batch)
    return Response(status_code=202)


@router.post('/api/catalog')
async def catalog(request: Request):
    expected = os.getenv('CATALOG_INGEST_TOKEN')
    if not expected:
        raise HTTPException(503, 'Catalog ingestion is not configured')
    supplied = request.headers.get('authorization', '')
    if not hmac.compare_digest(supplied.encode(), ('Bearer ' + expected).encode()):
        raise HTTPException(401, 'Invalid catalog credentials')
    if request.app.state.plan_mock:
        raise HTTPException(409, 'Catalog ingestion requires persistent mode')
    batch = await parse(request, CatalogBatch, 2000000)
    try:
        return await service(request).store.ingest(batch)
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 400:
            raise HTTPException(409, 'Catalog refresh refused; check timestamp, sync ID and SKU coverage') from None
        raise HTTPException(503, 'Catalog storage is unavailable') from None
    except (httpx.TransportError, TimeoutError, KeyError):
        raise HTTPException(503, 'Catalog storage is unavailable') from None


@router.get('/api/plan/{plan_id}/go')
async def go(plan_id: UUID, shopify_id: str, request: Request):
    row = await require_plan(request, plan_id, ready=True)
    product = next((p for s in row['plan_json']['steps'] for p in s['products']
                    if p['shopify_id'] == shopify_id), None)
    if not product:
        raise HTTPException(404, 'Product is not in this plan')
    origin = os.getenv('SHOPIFY_STORE_URL', '').rstrip('/')
    parts = urlsplit(origin)
    if parts.scheme != 'https' or not parts.netloc or parts.path or parts.query or parts.fragment:
        raise HTTPException(503, 'Store URL is not configured')
    # The frontend owns the click event. This endpoint only redirects.
    return RedirectResponse(origin + '/products/' + product['handle'] + '?' +
                            urlencode({'plan_id': str(plan_id)}), status_code=302)


@router.get('/apps/concierge/go', include_in_schema=False)
async def legacy_go(plan_id: UUID, shopify_id: str, request: Request):
    return await go(plan_id, shopify_id, request)


def uuid_or_none(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError):
        return None


@router.post('/api/webhooks/shopify/orders-paid')
async def orders_paid(request: Request):
    secret = os.getenv('SHOPIFY_WEBHOOK_SECRET')
    if not secret:
        raise HTTPException(503, 'Webhook is not configured')
    raw = await body_bytes(request, 2000000)
    expected = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(expected.encode(), request.headers.get('x-shopify-hmac-sha256', '').encode()):
        raise HTTPException(401, 'Invalid webhook signature')
    if request.headers.get('x-shopify-topic') != 'orders/paid':
        raise HTTPException(400, 'Unexpected webhook topic')
    try:
        order = json.loads(raw)
        order_id = str(order['id'])
        note = next((a.get('value') for a in order.get('note_attributes', []) if a.get('name') == 'plan_id'), None)
        references = [{'plan_id': uuid_or_none(note), 'line_id': None}]
        for line in order.get('line_items', []):
            value = next((p.get('value') for p in line.get('properties', []) if p.get('name') == '_plan_id'), None)
            references.append({'plan_id': uuid_or_none(value), 'line_id': str(line['id']),
                'shopify_id': str(line.get('product_id')), 'variant_id': str(line.get('variant_id')),
                'quantity': line.get('quantity')})
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(400, 'Invalid order payload') from None
    if request.app.state.plan_mock:
        raise HTTPException(409, 'Webhooks require persistent mode')
    # Persist before acknowledging so a process restart cannot lose a paid order.
    # Only minimal attribution fields are stored; no customer or payment details.
    await database(service(request).store.request('POST', 'plan_orders',
        params={'on_conflict': 'order_id'}, prefer='resolution=ignore-duplicates', body={
            'order_id': order_id, 'webhook_id': request.headers.get('x-shopify-webhook-id', order_id),
            'attribution': [r for r in references if r['plan_id']]}))
    return Response(status_code=200)
