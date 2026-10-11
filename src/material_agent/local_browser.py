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
  if (challenges.length) throw new Error('ZMA:CHALLENGE_VISIBLE');
  const rows = [...document.querySelectorAll('[data-id="div_TabMsg_ThrdChItem"]')];
  const allowed = rows.filter(n => normalize(n.querySelector('.conv-item-title__name .truncate')?.textContent || '') === normalize(source.title));
  if (allowed.length !== 1 || allowed[0].getAttribute('anim-data-id') !== source.dom_id)
    throw new Error('ZMA:SOURCE_MISSING');
  const selected = rows.filter(n => n.querySelector('.conv-item.selected'));
  if (selected.length !== 1 || selected[0] !== allowed[0])
    throw new Error('ZMA:SOURCE_MISMATCH');
  let texts = [...document.querySelectorAll('[id^="text-mCntr_"]')]
    .filter(n => n.id.endsWith('-' + source.dom_id) && visible(n));
  let images = [...document.querySelectorAll('[id^="image-mCntr_"]')]
    .filter(n => n.id.endsWith('-' + source.dom_id) && visible(n));
  if (!texts.length && !images.length) throw new Error('ZMA:NO_MESSAGES');
  const conversationScroller = () => {
    const nodes=[...texts,...images];
    for(let n=nodes[0].parentElement;n && n!==document.body;n=n.parentElement) {
      if(['auto','scroll'].includes(getComputedStyle(n).overflowY) && n.clientHeight>0 &&
         nodes.every(c=>n.contains(c)) && !n.querySelector('[data-id="div_TabMsg_ThrdChItem"]')) return n;
    }
    throw new Error('ZMA:SCROLLER_MISSING');
  };
  if(operation === 'read_window') {
    const bounds=conversationScroller().getBoundingClientRect();
    const intersects=n=>{const r=n.getBoundingClientRect();return r.bottom>Math.max(0,bounds.top) &&
      r.top<Math.min(innerHeight,bounds.bottom) && r.right>Math.max(0,bounds.left) &&
      r.left<Math.min(innerWidth,bounds.right);};
    texts=texts.filter(intersects);images=images.filter(intersects);
    if(!texts.length && !images.length) throw new Error('ZMA:NO_MESSAGES');
  }
  const base = {sourceTitle:source.title, candidateSourceId:source.dom_id,
    coverage:'rendered observed text/image containers only', layer:'RAW_UNVERIFIED',
    textContainers:texts.length, imageContainers:images.length,
    checkpointAdvanced:false, historicalCoverage:false, filesCoverage:false};
  if (operation === 'verify') return base;
  if (['scroll_latest','bottom_status','scroll_previous'].includes(operation)) {
    const n=conversationScroller();
    if(operation === 'bottom_status') return {atBottom:n.scrollHeight-n.clientHeight-n.scrollTop<=3};
    if(operation === 'scroll_previous') { n.scrollTop=Math.max(0,n.scrollTop-n.clientHeight*0.75); return {atTop:n.scrollTop<=3}; }
    n.scrollTop=n.scrollHeight;
    return {atBottom:n.scrollHeight-n.clientHeight-n.scrollTop<=3};
  }
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
  if (!['read_visible','read_window'].includes(operation)) throw new Error('Unsupported operation');
  const ordered = [...texts, ...images].sort((a,b) =>
    a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
  const positions = new Map(ordered.map((n,i)=>[n,i]));
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
    return {renderedOrder:positions.get(n),candidateBubbleId:bubble?.id || null,candidateFrameId:frame?.id || null,
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


IMAGE_BYTES = r'''async ({source, containerId, imageId}) => {
  const parent=document.getElementById(containerId);
  const matches=parent ? [...parent.querySelectorAll('img[data-z-element-type="image"]')].filter(n=>n.id===imageId) : [];
  const img=matches.length===1 ? matches[0] : null;
  if(!parent || !parent.id.startsWith('image-mCntr_') || !parent.id.endsWith('-'+source.dom_id) || !img) return {status:'UNAVAILABLE'};
  if(!img.complete || !img.naturalWidth) return {status:'UNAVAILABLE'};
  const url=img.currentSrc || img.src;
  // Read only an existing browser-owned blob; never fetch arbitrary remote URLs.
  if(!url.startsWith('blob:https://chat.zalo.me/')) return {status:'UNAVAILABLE'};
  const response=await fetch(url);
  if(!response.ok) return {status:'UNAVAILABLE'};
  const mime=(response.headers.get('content-type')||'').split(';')[0];
  if(!['image/png','image/jpeg','image/webp','application/octet-stream',''].includes(mime)) return {status:'UNAVAILABLE'};
  const reader=response.body.getReader();const chunks=[];let size=0;
  while(true){const {done,value}=await reader.read();if(done)break;
    size+=value.length;if(size>8*1024*1024){await reader.cancel();return {status:'LIMIT'};}chunks.push(value);}
  let binary='';for(const chunk of chunks){for(let i=0;i<chunk.length;i+=8192)binary+=String.fromCharCode(...chunk.subarray(i,i+8192));}
  return {status:'READ',base64:btoa(binary)};
}'''


class LocalBrowser:
    def __init__(self):
        self.context = self.page = self.playwright = None
        self.source=dict(SOURCE)

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
        if operation not in {'verify', 'structure', 'read_visible', 'scroll_latest', 'bottom_status', 'scroll_previous', 'read_window'}:
            raise StopAutomation('Operation is not permitted')
        if self.page is None or self.page.is_closed():
            raise StopAutomation('Open the local browser first')
        url = urlsplit(self.page.url)
        if url.scheme != 'https' or url.hostname != 'chat.zalo.me' or url.port not in (None,443):
            raise StopAutomation('Unexpected origin')
        try:
            return await self.page.evaluate(DOM_PROBE, {'source': self.source, 'operation': operation})
        except Exception as exc:
            errors={
                'CHALLENGE_VISIBLE':'Có hộp thoại hoặc bước xác minh. Hoàn tất trên Zalo rồi kết nối lại.',
                'SOURCE_MISSING':'Không xác minh được nhóm trong danh sách hội thoại. Đóng bảng tìm kiếm Zalo bằng nút Đóng, chọn lại nhóm rồi kết nối lại.',
                'SOURCE_MISMATCH':'Nhóm đang chọn khác nhóm được phép. Chọn lại nhóm rồi kết nối lại.',
                'NO_MESSAGES':'Chưa thấy tin nhắn của nhóm đã xác minh. Chờ Zalo tải nội dung rồi kết nối lại.',
                'SCROLLER_MISSING':'Không tìm thấy vùng cuộn hội thoại chứa tin nhắn đã xác minh. Cần kiểm tra cấu trúc DOM.'}
            for code,message in errors.items():
                if 'ZMA:'+code in str(exc): raise StopAutomation(message,code=code) from None
            raise StopAutomation('Source/UI/security verification failed; reconnect locally after checking browser',code='BROWSER_VERIFICATION_FAILED') from None

    async def image_bytes(self, container_id, image_id):
        import base64
        import asyncio
        if not isinstance(container_id,str) or not container_id.endswith('-'+self.source['dom_id']):
            raise StopAutomation('Nguồn ảnh không đúng nhóm.',code='SOURCE_MISMATCH')
        if not isinstance(image_id,str) or len(image_id)>500: return None
        await self.execute('verify')
        try:
            result=await asyncio.wait_for(self.page.evaluate(IMAGE_BYTES,{'source':self.source,
                'containerId':container_id,'imageId':image_id}),timeout=10)
        except Exception:
            await self.execute('verify')
            return None
        await self.execute('verify')
        if result.get('status')!='READ': return None
        try: data=base64.b64decode(result['base64'],validate=True)
        except (ValueError,KeyError): return None
        return data if len(data)<=8*1024*1024 else None

    async def select_group(self, group):
        import asyncio
        for attempt in range(60):
            if self.page is None or self.page.is_closed(): raise StopAutomation('Mở Zalo trước.',code='BROWSER_REQUIRED')
            url=urlsplit(self.page.url)
            if url.scheme!='https' or url.hostname!='chat.zalo.me' or url.port not in (None,443): raise StopAutomation('Unexpected origin')
            outcome=await self.page.evaluate(r"""group => {
              const norm=s=>s.normalize('NFC').replace(/\s+/gu,' ').trim();
              if([...document.querySelectorAll('[role="dialog"],input[type="password"],[id*="captcha" i]')].some(n=>n.getClientRects().length)) return {error:'CHALLENGE_VISIBLE'};
              const rows=[...document.querySelectorAll('[data-id="div_TabMsg_ThrdChItem"]')];
              const matches=rows.filter(n=>norm(n.querySelector('.conv-item-title__name .truncate')?.textContent||'')===norm(group.title));
              if(matches.length>1)return {error:'GROUP_AMBIGUOUS'};
              if(matches.length===1){const row=matches[0],id=row.getAttribute('anim-data-id');
                if(!/^g[0-9]+$/.test(id||'') || (group.dom_id && group.dom_id!==id)) return {error:'GROUP_ID_CHANGED'};
                return {source:{title:group.title,dom_id:id},alreadySelected:!!row.querySelector('.conv-item.selected')};}
              if(!rows.length)return {error:'GROUP_LIST_MISSING'};
              for(let n=rows[0].parentElement;n && n!==document.body;n=n.parentElement){
                if(['auto','scroll'].includes(getComputedStyle(n).overflowY) && n.clientHeight>0 && rows.every(r=>n.contains(r)) && !n.querySelector('[id^="text-mCntr_"]')){
                  const old=n.scrollTop;n.scrollTop=group.reset?0:n.scrollTop+n.clientHeight*0.7;
                  return {moved:group.reset || n.scrollTop!==old};}}
              return {error:'GROUP_NOT_FOUND'};
            }""",{**group,'reset':attempt==0})
            if outcome.get('error'):raise StopAutomation('Không mở được nhóm đã chọn: '+outcome['error'],code=outcome['error'])
            if outcome.get('source'):
                self.source=outcome['source']
                if not outcome.get('alreadySelected'):
                    try:
                        # Native Playwright click hits the actual React conversation item,
                        # rather than its outer positioning wrapper.
                        target=self.page.locator('[data-id="div_TabMsg_ThrdChItem"][anim-data-id="'+self.source['dom_id']+'"] .conv-item')
                        if await target.count()!=1:raise StopAutomation('Nhóm không duy nhất.',code='GROUP_AMBIGUOUS')
                        await target.click(timeout=5000)
                    except StopAutomation:raise
                    except Exception:raise StopAutomation('Không bấm mở được nhóm. Đóng các bảng nổi trong Zalo rồi thử lại.',code='GROUP_CLICK_FAILED') from None
                consecutive=0
                for _ in range(40):
                    await asyncio.sleep(0.25)
                    try:
                        await self.execute('verify')
                        await self.execute('read_window')
                        consecutive+=1
                        if consecutive>=2:return dict(self.source)
                    except StopAutomation as exc:
                        consecutive=0
                        if exc.code not in {'SOURCE_MISMATCH','SOURCE_MISSING','NO_MESSAGES'}:raise
                raise StopAutomation('Zalo chưa chuyển xong sang nhóm đã chọn sau 10 giây. Không đọc hay lưu dữ liệu nhóm khác.',code='GROUP_SWITCH_TIMEOUT')
            if not outcome.get('moved'):break
            await asyncio.sleep(0.2)
        raise StopAutomation('Không tìm thấy nhóm trong danh sách hội thoại. Đóng tìm kiếm Zalo và bảo đảm đã tham gia nhóm.',code='GROUP_NOT_FOUND')

    async def read_latest(self, anchor=None):
        import asyncio
        # Revalidate the source after every movement and wait for lazy rendering.
        for _ in range(8):
            await self.execute('scroll_latest')
            await asyncio.sleep(0.5)
            state=await self.execute('scroll_latest')
            if state['atBottom']:
                await asyncio.sleep(0.5)
                if not (await self.execute('bottom_status'))['atBottom']: continue
                result=await self.execute('read_window')
                break
        else:
            raise StopAutomation('Cuộc trò chuyện chưa ổn định ở cuối trang. Kết nối lại rồi thử Play.',code='SCROLL_NOT_SETTLED')
        if not anchor or any(n['domContainerId']==anchor for n in result['messages']+result['attachments']):
            return {**result,'navigation':'verified conversation scrolled to bottom','historicalCoverage':False}
        collected={n['domContainerId']:n for n in result['messages']+result['attachments']}
        order=[n['domContainerId'] for n in sorted(collected.values(),key=lambda n:n['renderedOrder'])]
        found=False
        for _ in range(80):
            movement=await self.execute('scroll_previous')
            await asyncio.sleep(0.4)
            window=await self.execute('read_window')
            entries=sorted(window['messages']+window['attachments'],key=lambda n:n['renderedOrder'])
            fresh=[n['domContainerId'] for n in entries if n['domContainerId'] not in collected]
            order=fresh+order
            collected.update({n['domContainerId']:n for n in entries})
            if sum('text' in n for n in collected.values())>200 or sum('kind' in n for n in collected.values())>200:
                raise StopAutomation('Khoảng cần đọc vượt giới hạn bản lưu. Đã dừng, chưa cập nhật mốc.',code='CATCHUP_LIMIT')
            if anchor in collected:
                found=True;break
            if movement['atTop']:
                await asyncio.sleep(0.6)
        if not found:
            raise StopAutomation('Chưa tìm thấy tin cuối đã lưu sau khi dò lịch sử. Đã dừng, chưa cập nhật mốc.',code='ANCHOR_NOT_FOUND')
        # Return the operator to the bottom and include arrivals during catch-up.
        latest=await self.read_latest()
        for n in sorted(latest['messages']+latest['attachments'],key=lambda n:n['renderedOrder']):
            if n['domContainerId'] not in collected: order.append(n['domContainerId'])
            collected[n['domContainerId']]=n
        for i,key in enumerate(order): collected[key]={**collected[key],'renderedOrder':i}
        return {**latest,'messages':[collected[k] for k in order if 'text' in collected[k]],
            'attachments':[collected[k] for k in order if 'kind' in collected[k]],
            'navigation':'bottom plus bounded catch-up to saved DOM anchor','historicalCoverage':False}

    async def close(self):
        context, playwright = self.context, self.playwright
        self.page = self.context = self.playwright = None
        try:
            if context is not None:
                await context.close()
        finally:
            if playwright is not None:
                await playwright.stop()
