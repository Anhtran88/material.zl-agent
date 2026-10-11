import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
from .adapter import ZaloAdapter
from .models import Source, StopAutomation

async def run(args):
    from playwright.async_api import async_playwright
    cfg = json.loads(Path(args.config).read_text(encoding='utf-8'))
    source = Source(cfg['conversation_id'], cfg['title'])
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'ZaloMaterialAgent'
    job = str(uuid4())
    cache = root / 'cache' / job
    cache.mkdir(parents=True, exist_ok=False)
    log = cache / 'run.jsonl'
    def emit(event, **fields):
        with log.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'run_id': job, 'job_id': job, 'event': event, **fields}, ensure_ascii=False) + '\n')
    # Validate before starting the browser. No user credentials are requested.
    ZaloAdapter(None, source, cfg['selectors'])
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(root / 'browser-profile'), headless=False, accept_downloads=True)
        try:
            page = await context.new_page()
            await page.goto('https://chat.zalo.me', wait_until='domcontentloaded')
            emit('WAITING_LOGIN')
            await asyncio.to_thread(input, 'Đăng nhập thủ công; hoàn tất xác minh rồi nhấn Enter: ')
            adapter = ZaloAdapter(page, source, cfg['selectors'])
            await adapter.open_allowed()
            messages = await adapter.read_visible()
            # Raw evidence is sensitive; stays local and never goes to console/provider.
            (cache / 'timeline.json').write_text(json.dumps([asdict(m) for m in messages], ensure_ascii=False, indent=2), encoding='utf-8')
            emit('READ_VISIBLE', messages=len(messages), attachments=sum(len(m.attachments) for m in messages), coverage='visible_only')
            if bool(args.message) != bool(args.attachment):
                raise StopAutomation('Both message and attachment IDs are required')
            if args.attachment:
                target = cache / 'attachment.bin'
                await adapter.download_selected(args.message, args.attachment, target)
                with target.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                emit('DOWNLOAD_COMPLETE', sha256=digest, bytes=target.stat().st_size)
            emit('POC_CAPTURED', accepted=False, checkpoint_advanced=False)
            print(f'PoC evidence: {cache}')
        except Exception as exc:
            # Never log exception text: browser errors may contain signed URLs or secrets.
            emit('STOP_AUTOMATION', error_type=type(exc).__name__)
            raise StopAutomation('PoC stopped. Inspect local evidence and UI manually.') from None
        finally:
            await context.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--message')
    parser.add_argument('--attachment')
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except StopAutomation as exc:
        parser.exit(2, f'{exc}\n')

if __name__ == '__main__':
    main()
