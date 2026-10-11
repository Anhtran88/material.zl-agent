"""Manual-only local login browser. Does not scan or interact with conversations."""
import asyncio
import os
from pathlib import Path


def profile_path():
    local = os.environ.get('LOCALAPPDATA')
    if os.name == 'nt' and not local:
        raise RuntimeError('LOCALAPPDATA is required on Windows')
    return Path(local or Path.home() / '.local/share') / 'ZaloMaterialAgent' / 'browser-profile'


async def open_browser():
    from playwright.async_api import async_playwright
    profile = profile_path()
    profile.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        profile.chmod(0o700)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(profile), headless=False, accept_downloads=False,
        )
        try:
            page = await context.new_page()
            await page.goto('https://chat.zalo.me', wait_until='domcontentloaded', timeout=60000)
            print('Dang nhap Zalo thu cong trong Chromium. Agent khong doc nhom o buoc nay.')
            print('Tu xu ly QR/xac minh; khong gui OTP, cookie hoac profile vao chat.')
            await asyncio.to_thread(input, 'Nhan Enter tai day khi muon dong trinh duyet: ')
        finally:
            await context.close()


def main():
    try:
        asyncio.run(open_browser())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        # Browser errors can contain credential-bearing URLs: log only the type.
        print(f'Khong mo duoc trinh duyet ({type(exc).__name__}). Kiem tra mang va profile dang su dung.')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
