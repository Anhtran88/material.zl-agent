from pathlib import Path
from .models import Source, Message, Attachment, StopAutomation

REQUIRED = {'ready', 'security', 'source', 'active_source', 'message', 'sender',
            'timestamp', 'text', 'attachment', 'download'}

class ZaloAdapter:
    """Narrow supervised DOM contract. No generic click/write operation is exposed."""
    def __init__(self, page, source: Source, selectors: dict):
        if not source.conversation_id.strip() or not source.title.strip():
            raise StopAutomation('Source ID and exact title required')
        if REQUIRED - selectors.keys() or any(not selectors[k].strip() for k in REQUIRED):
            raise StopAutomation('All selectors must be verified locally before running')
        self.page, self.source, self.s = page, source, selectors

    async def check_ready(self):
        if await self.page.locator(self.s['security']).count():
            raise StopAutomation('Security/login challenge: manual handling required')
        if await self.page.locator(self.s['ready']).count() != 1:
            raise StopAutomation('Not logged in or UI contract changed')

    async def _identity(self, loc):
        if await loc.count() != 1:
            raise StopAutomation('Conversation must have exactly one match')
        if await loc.get_attribute('data-conversation-id') != self.source.conversation_id:
            raise StopAutomation('Conversation identity mismatch')
        if await loc.get_attribute('data-title') != self.source.title:
            raise StopAutomation('Exact conversation title mismatch')

    async def open_allowed(self):
        await self.check_ready()
        loc = self.page.locator(self.s['source'])
        await self._identity(loc)
        await loc.click()  # Only the verified source navigation element.
        await self.assert_active()

    async def assert_active(self):
        await self.check_ready()
        await self._identity(self.page.locator(self.s['active_source']))

    async def read_visible(self):
        await self.assert_active()
        result, seen = [], set()
        for row in await self.page.locator(self.s['message']).all():
            mid = await row.get_attribute('data-message-id')
            if not mid or mid in seen:
                raise StopAutomation('Missing/duplicate stable message ID; coverage uncertain')
            seen.add(mid)
            fields = []
            for key in ('sender', 'timestamp', 'text'):
                loc = row.locator(self.s[key])
                if await loc.count() != 1:
                    raise StopAutomation('Message DOM contract changed')
                fields.append(await loc.inner_text())
            if not fields[0].strip() or not fields[1].strip():
                raise StopAutomation('Sender/time missing')
            attachments, aids = [], set()
            for att in await row.locator(self.s['attachment']).all():
                aid = await att.get_attribute('data-attachment-id')
                kind = await att.get_attribute('data-kind')
                if not aid or aid in aids or kind not in {'image', 'pdf', 'word', 'excel', 'file'}:
                    raise StopAutomation('Unknown/duplicate attachment metadata')
                aids.add(aid)
                attachments.append(Attachment(aid, kind, await att.inner_text()))
            result.append(Message(mid, *fields, tuple(attachments)))
        await self.assert_active()
        if not result:
            raise StopAutomation('Empty timeline requires manual verification')
        return result

    async def download_selected(self, message_id: str, attachment_id: str, target: Path):
        await self.assert_active()
        rows = [row for row in await self.page.locator(self.s['message']).all()
                if await row.get_attribute('data-message-id') == message_id]
        if len(rows) != 1:
            raise StopAutomation('Selected message is no longer uniquely visible')
        atts = [att for att in await rows[0].locator(self.s['attachment']).all()
                if await att.get_attribute('data-attachment-id') == attachment_id]
        if len(atts) != 1:
            raise StopAutomation('Selected attachment is not uniquely in this message')
        button = atts[0].locator(self.s['download'])
        if await button.count() != 1 or await button.get_attribute('data-action') != 'download':
            raise StopAutomation('Download control contract unverified')
        if target.exists():
            raise StopAutomation('Refusing to overwrite cached evidence')
        async with self.page.expect_download(timeout=30000) as pending:
            await button.click()
        download = await pending.value
        if await download.failure():
            raise StopAutomation('Download failed; retain cache and retry manually')
        await download.save_as(target)
        await self.assert_active()
        if not target.is_file() or target.stat().st_size == 0:
            raise StopAutomation('Empty download')
