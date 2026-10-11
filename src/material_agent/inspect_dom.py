"""Read-only DOM discovery for the manually selected, observed allowed group."""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .login import profile_path

PROBE = r"""() => {
  const norm = s => s.normalize('NFC').replace(/\s+/gu,' ').trim();
  const expectedTitle = 'ĐỐI CHIẾU KL- KẾ TOÁN IJC';
  const expectedId = 'g3144426084883145716';
  const rows = [...document.querySelectorAll('[data-id="div_TabMsg_ThrdChItem"]')]
    .filter(n => n.querySelector('.conv-item.selected'));
  if (rows.length !== 1) throw new Error('Selected source ambiguous');
  const row = rows[0];
  const title = row.querySelector('.conv-item-title__name .truncate')?.textContent || '';
  if (norm(title) !== norm(expectedTitle) || row.getAttribute('anim-data-id') !== expectedId)
    throw new Error('Allowed source identity mismatch');
  const attrs = ['id','class','data-id','data-component','anim-data-id','role'];
  const describe = n => ({tag:n.tagName.toLowerCase(),
    attributes:Object.fromEntries(attrs.filter(a=>n.hasAttribute(a)).map(a=>[a,n.getAttribute(a)])),
    children:[...n.children].slice(0,30).map(c=>({tag:c.tagName.toLowerCase(),
      class:c.getAttribute('class'),dataId:c.getAttribute('data-id'),
      component:c.getAttribute('data-component')}))});
  const ancestry = n => {
    const out=[];
    for(let i=0;i<8 && n && n!==document.body;i++,n=n.parentElement) out.push(describe(n));
    return out;
  };
  // Select only nodes whose observed ID includes the allowed group identity.
  // Do not read text, URLs, arbitrary HTML, application state or credential storage.
  const texts=[...document.querySelectorAll('[id^="text-mCntr_"]')]
    .filter(n=>n.id.endsWith('-'+expectedId));
  const images=[...document.querySelectorAll('[id^="image-mCntr_"]')]
    .filter(n=>n.id.endsWith('-'+expectedId));
  if(!texts.length && !images.length) throw new Error('No observed allowed timeline nodes');
  return {sourceTitle:expectedTitle,candidateSourceId:expectedId,
    coverage:'currently rendered observed text/image nodes only',
    textNodes:texts.length,imageContainers:images.length,
    textStructures:texts.slice(0,5).map(ancestry),
    imageStructures:images.slice(0,5).map(ancestry),
    sourceStructure:describe(row),
    limitations:['Not a stable message ID guarantee','No sender/time extraction yet',
      'No file/download or historical coverage verification']};
}"""

async def inspect():
    from playwright.async_api import async_playwright
    root = profile_path().parent
    if not profile_path().exists():
        raise RuntimeError('Run manual login launcher first')
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(profile_path()), headless=False, accept_downloads=False)
        try:
            page = await context.new_page()
            await page.goto('https://chat.zalo.me', wait_until='domcontentloaded', timeout=60000)
            print('Mo thu cong nhom DOI CHIEU KL- KE TOAN IJC. Khong gui noi dung.')
            print('Neu gap QR/CAPTCHA/xac minh: tu xu ly thu cong truoc khi tiep tuc.')
            await asyncio.to_thread(input,'Khi dung nhom da hien tin nhan va anh, nhan Enter: ')
            if not page.url.startswith('https://chat.zalo.me/') and page.url != 'https://chat.zalo.me':
                raise RuntimeError('Unexpected browser origin')
            report = await page.evaluate(PROBE)
            report['capturedAtUTC'] = datetime.now(timezone.utc).isoformat()
            report['kind'] = 'DOM_STRUCTURE_ONLY_NOT_M1_ACCEPTANCE'
            folder = root/'cache'/str(uuid4())
            folder.mkdir(parents=True,exist_ok=False)
            target = folder/'dom-report.json'
            target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'Bao cao DOM: {target}')
            if os.name == 'nt':
                os.startfile(str(folder))
            await asyncio.to_thread(input,'Da xuat bao cao. Nhan Enter de dong trinh duyet: ')
        finally:
            await context.close()

def main():
    raise SystemExit("Local business file export is disabled. Use Local Agent memory preview; Firebase setup pending.")

def legacy_local_main():
    try:
        asyncio.run(inspect())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'DUNG ({type(exc).__name__}): kiem tra dung nhom, mang, hoac profile dang mo. Khong tu bo qua kiem tra.')
        raise SystemExit(1) from None

if __name__ == '__main__':
    main()
