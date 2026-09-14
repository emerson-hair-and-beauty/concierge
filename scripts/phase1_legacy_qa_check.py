"""Record the existing live routing QA outcomes without its verbose prompt output."""
import asyncio
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.qa_scenarios import SCENARIOS, run_routing_check


async def main():
    slots = asyncio.Semaphore(4)
    async def run(case):
        async with slots:
            async with asyncio.timeout(60):
                return await run_routing_check(*case)
    with redirect_stdout(io.StringIO()):
        results = await asyncio.gather(*(run(case) for case in SCENARIOS))
    output = Path(__file__).resolve().parents[1] / 'tests' / 'phase1_legacy_qa_results.json'
    output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print('Existing live routing QA:', sum(r['pass'] for r in results), '/', len(results))
    for result in results:
        if not result['pass']:
            print(json.dumps(result))


if __name__ == '__main__':
    asyncio.run(main())
