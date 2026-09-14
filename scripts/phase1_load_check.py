"""Loopback HTTP concurrency check with delayed generation and in-memory storage."""
import asyncio
import json
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
import uvicorn
from tests.test_phase1 import app_for, payload
from app.services.plans.mock import MockGenerator


async def main():
    gate = asyncio.Event()
    class DelayedGenerator(MockGenerator):
        async def build(self, *args):
            await gate.wait()
            return await super().build(*args)
    app = app_for(generator=DelayedGenerator())
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    results = []
    try:
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(.01)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', timeout=5) as client:
            for count in (8, 25):
                gate.clear()
                async def submit():
                    started = time.monotonic()
                    response = await client.post('/api/plan', json=payload())
                    assert response.status_code == 202, response.text
                    return response.json()['plan_id'], time.monotonic()-started
                submissions = await asyncio.gather(*(submit() for _ in range(count)))
                async def poll(plan_id):
                    started = time.monotonic()
                    response = await client.get('/api/plan/' + plan_id)
                    assert response.json()['status'] == 'pending'
                    return time.monotonic()-started
                delays = []
                for _ in range(3):
                    delays.extend(await asyncio.gather(*(poll(plan_id) for plan_id, _ in submissions)))
                gate.set()
                async with asyncio.timeout(3):
                    while app.state.plan_service.active:
                        await asyncio.sleep(.01)
                result = {'concurrent_submissions': count,
                          'max_submit_ms': round(max(t for _, t in submissions)*1000, 2),
                          'max_poll_ms': round(max(delays)*1000, 2)}
                assert result['max_submit_ms'] < 1000, result
                assert result['max_poll_ms'] < 500, result
                results.append(result)
                print(json.dumps(result), flush=True)
    finally:
        gate.set()
        server.should_exit = True
        await task
        sock.close()
    output = Path(__file__).resolve().parents[1] / 'tests' / 'phase1_load_results.json'
    output.write_text(json.dumps({'scope': 'Loopback HTTP, delayed generation, in-memory storage; not production load',
                                 'results': results}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
