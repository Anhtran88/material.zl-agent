"""Local browser port: fixed read-only operations, no arbitrary scripts/selectors."""
from urllib.parse import urlsplit
from .login import profile_path
from .models import StopAutomation

SOURCE = {'title': 'ĐỐI CHIẾU KL- KẾ TOÁN IJC', 'dom_id': 'g3144426084883145716'}

# Code is fixed on disk; callers cannot supply JavaScript or CSS selectors.
DOM_PROBE = r'''({source, operation}) => {
  const normalize = s => s.normalize('NFC').replace(/\s+/gu, ' ').trim();
  const visible = n => Boolean(n.getClientRects().length);
  const challenges = [...document.querySelectorAll(
    '[role="dialog"], [id*="captcha" i], [class*="captcha" i], iframe[src*="captcha" i], input[type="password"]'
  )].filter(visible);
  if (challenges.length) throw new Error('PAUSE_USER: dialog or possible challenge');
  const rows = [...document.querySelectorAll('[data-id="div_TabMsg_ThrdChItem"]')];
  const allowed = rows.filter(n => normalize(n.querySelector('.conv-item-title__name .truncate')?.textContent || '') === normalize(source.title));
  if (allowed.length !== 1 || allowed[0].getAttribute('anim-data-id') !== source.dom_id)
    throw new Error('PAUSE_USER: allowed source missing, ambiguous or changed');
  const selected = rows.filter(n => n.querySelector('.conv-item.selected'));
  if (selected.length !== 1 || selected[0] !== allowed[0])
    throw new Error('PAUSE_USER: active source mismatch');
  const texts = [...document.querySelectorAll('[id^="text-mCntr_"]')]
    .filter(n => n.id.endsWith('-' + source.dom_id) && visible(n));
  const images = [...document.querySelectorAll('[id^="image-mCntr_"]')]
    .filter(n => n.id.endsWith('-' + source.dom_id) && visible(n));
  if (!texts.length && !images.length) throw new Error('PAUSE_USER: no verified rendered nodes');
  const base = {sourceTitle:source.title, candidateSourceId:source.dom_id,
    coverage:'rendered observed text/image containers only', layer:'RAW_UNVERIFIED',
    textContainers:texts.length, imageContainers:images.length,
    checkpointAdvanced:false, historicalCoverage:false, filesCoverage:false};
  if (operation === 'verify') return base;
  const attrs = ['id','class','data-id','data-component','anim-data-id','role'];
  const describe = n => ({tag:n.tagName.toLowerCase(),
    attributes:Object.fromEntries(attrs.filter(a=>n.hasAttribute(a)).map(a=>[a,n.getAttribute(a)])),
    children:[...n.children].slice(0,30).map(c=>({tag:c.tagName.toLowerCase(),
      class:c.getAttribute('class'),dataId:c.getAttribute('data-id'),component:c.getAttribute('data-component')}))});
  const ancestors = n => {
    const out=[];
    for(let i=0;i<16 && n && n!==document.body;i++,n=n.parentElement) { out.push(describe(n)); if (n.matches('[data-component="bubble-message"]')) break; }
    return out;
  };
  if (operation === 'structure') return {...base,
    textStructures:texts.slice(0,5).map(ancestors),imageStructures:images.slice(0,5).map(ancestors)};
  if (operation !== 'read_visible') throw new Error('Unsupported operation');
  // These are current DOM labels and opaque identities, not stable server IDs.
  const context = n => {
    const bubble = n.closest('[data-component="bubble-message"]');
    const frame = n.closest('[data-component="message-content-view"]');
    const label = selector => {
      if (!frame || !bubble) return null;
      const nodes = [...frame.querySelectorAll(selector)].filter(c =>
        visible(c) && c.closest('[data-component="message-content-view"]') === frame &&
        !c.closest('.message-quote-fragment__container'));
      if (nodes.length !== 1) return null;
      const value = normalize(nodes[0].textContent || '');
      return value && value.length <= 500 ? value : null;
    };
    return {candidateBubbleId:bubble?.id || null,candidateFrameId:frame?.id || null,
      senderDisplayLabel:label('.message-sender-name-wrapper'),
      messageTimeDisplayLabel:label('.card-send-time')};
  };
  const messages = texts.slice(0,200).map(n => {
    const text = [...n.querySelectorAll('[data-component="message-text-content"] .text')]
      .filter(c=>!c.closest('.message-quote-fragment__container'))
      .map(c=>c.textContent || '').join('\n');
    return {...context(n),domContainerId:n.id,text:text.slice(0,20000),textTruncated:text.length>20000,
      stableMessageId:null,sender:null,messageTimestamp:null};
  });
  const attachments = images.slice(0,200).map(n=>({...context(n),domContainerId:n.id,kind:'image',
    images:[...n.querySelectorAll('img[data-z-element-type="image"]')].map(img=>({
      domImageId:img.id,width:img.naturalWidth,height:img.naturalHeight,
      loaded:img.complete && img.naturalWidth>0,originalBytesDownloaded:false}))}));
  return {...base,messages,attachments,truncated:texts.length>200 || images.length>200,
    warning:'Display labels and DOM identities only; no inferred sender, parsed timestamp or original image. Not business evidence acceptance.'};
}'''


class LocalBrowser:
    def __init__(self):
        self.context = self.page = self.playwright = None

    async def start(self):
        if self.page is not None and not self.page.is_closed():
            return
        await self.close()
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                str(profile_path()), headless=False, accept_downloads=False)
            self.page = await self.context.new_page()
            await self.page.goto('https://chat.zalo.me', wait_until='domcontentloaded', timeout=60000)
        except Exception:
            await self.close()
            raise StopAutomation('Browser unavailable; manual intervention required') from None

    async def execute(self, operation):
        if operation not in {'verify', 'structure', 'read_visible'}:
            raise StopAutomation('Operation is not permitted')
        if self.page is None or self.page.is_closed():
            raise StopAutomation('Open the local browser first')
        url = urlsplit(self.page.url)
        if url.scheme != 'https' or url.hostname != 'chat.zalo.me' or url.port not in (None,443):
            raise StopAutomation('Unexpected origin')
        try:
            return await self.page.evaluate(DOM_PROBE, {'source': SOURCE, 'operation': operation})
        except Exception:
            raise StopAutomation('Source/UI/security verification failed; reconnect locally after checking browser') from None

    async def close(self):
        context, playwright = self.context, self.playwright
        self.page = self.context = self.playwright = None
        try:
            if context is not None:
                await context.close()
        finally:
            if playwright is not None:
                await playwright.stop()
