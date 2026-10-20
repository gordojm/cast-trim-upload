"""Upload an episode through the Spotify for Creators web UI with Playwright.

Spotify has no public upload API for Spotify-hosted shows, so this drives the site
like a person would. The browser profile in data/browser-profile keeps the login
session; when it is missing or expired a visible window opens for a manual login.

Playwright runs in a worker thread on its own event loop (Proactor on Windows), so it
works no matter which loop the web server uses.
"""

import asyncio
import json
import logging
import re
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .. import messages as M
from ..config import Settings
from ..models import Job, JobStatus, PublishMode
from . import selectors as sel

log = logging.getLogger(__name__)

Reporter = Callable[..., None]

STEP_TIMEOUT_MS = 30_000
LOGIN_CHECK_TIMEOUT_S = 30
LOGIN_STABLE_CHECKS = 3


class UploadError(M.AppError):
    pass


class UploadCancelled(UploadError):
    def __init__(self) -> None:
        super().__init__(M.E_CANCELLED)


class LoginRequiredError(UploadError):
    pass


class _NeedHeadedLogin(Exception):
    pass


def _run_isolated(factory: Callable[[], Awaitable]):
    loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(factory())
    finally:
        loop.close()
        asyncio.set_event_loop(None)


class SpotifyUploader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self.logged_in: bool | None = None
        self.checked_at: datetime | None = None
        self.busy = False
        self._state_file = settings.data_dir / "spotify.json"
        self.show_id: str | None = settings.spotify_show_id or self._load_state().get("show_id")

    # ------------------------------------------------------------ public (async)

    async def upload(self, job: Job, report: Reporter, cancel: threading.Event) -> str | None:
        return await asyncio.to_thread(self._exclusive, lambda: self._upload(job, report, cancel))

    async def check_session(self) -> bool:
        return await asyncio.to_thread(self._exclusive, self._check_session)

    async def login(self) -> bool:
        return await asyncio.to_thread(self._exclusive, lambda: self._interactive_login(None))

    async def open_dashboard(self) -> None:
        """Open a visible browser on the dashboard (handy for inspecting the site)."""
        await asyncio.to_thread(self._exclusive, self._open_dashboard)

    # ------------------------------------------------------------ plumbing

    def _exclusive(self, factory: Callable[[], Awaitable]):
        # One browser at a time: the persistent profile can't be opened twice.
        with self._lock:
            self.busy = True
            try:
                return _run_isolated(factory)
            finally:
                self.busy = False

    @asynccontextmanager
    async def _browser(self, headless: bool):
        self.settings.browser_profile_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                str(self.settings.browser_profile_dir),
                headless=headless,
                locale="en-US",
                viewport={"width": 1440, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx.set_default_timeout(STEP_TIMEOUT_MS)
            try:
                yield ctx
            finally:
                try:
                    await ctx.close()
                except PlaywrightError:
                    pass

    @staticmethod
    async def _page(ctx: BrowserContext) -> Page:
        return ctx.pages[0] if ctx.pages else await ctx.new_page()

    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _remember(self, logged_in: bool, url: str | None = None) -> None:
        self.logged_in = logged_in
        self.checked_at = datetime.now().astimezone()
        # Learn the show id from dashboard URLs so the wizard URL can be built.
        if logged_in and url and not self.settings.spotify_show_id:
            if (m := re.search(sel.SHOW_ID_PATTERN, url)) and m.group(1) != self.show_id:
                self.show_id = m.group(1)
                self._state_file.write_text(json.dumps({"show_id": self.show_id}), encoding="utf-8")
                log.info("Spotify show id: %s", self.show_id)

    # ------------------------------------------------------------ login

    @staticmethod
    async def _login_state(page: Page) -> bool | None:
        """True = logged in, False = login page, None = still loading/unknown."""
        url = page.url
        if any(m in url for m in sel.LOGIN_URL_MARKERS):
            return False
        try:
            if await page.locator(sel.LOGIN_PAGE_MARKER).count():
                return False
        except PlaywrightError:
            return None
        if urlparse(url).hostname == sel.CREATORS_HOST:
            return True
        return None

    async def _goto_logged_in(self, page: Page, url: str) -> bool:
        await page.goto(url, wait_until="domcontentloaded")
        # The dashboard first renders at its own URL and only then redirects to
        # accounts.spotify.com via JS, so wait for the network to settle and require the
        # same answer several times in a row.
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeout:
            pass
        deadline = time.monotonic() + LOGIN_CHECK_TIMEOUT_S
        last, streak = None, 0
        while time.monotonic() < deadline:
            state = await self._login_state(page)
            streak = streak + 1 if state is not None and state == last else 1
            last = state
            if state is not None and streak >= LOGIN_STABLE_CHECKS:
                self._remember(state, page.url)
                return state
            await page.wait_for_timeout(1000)
        raise UploadError(M.E_SPOTIFY_NOT_LOADED, url=page.url)

    async def _wait_for_login(self, page: Page) -> Page:
        """Wait until any tab of the window reaches the dashboard; returns that tab."""
        ctx = page.context
        deadline = time.monotonic() + self.settings.spotify_login_timeout_s
        confirmed: dict[Page, int] = {}
        while time.monotonic() < deadline:
            pages = [p for p in ctx.pages if not p.is_closed()]
            if not pages:
                raise LoginRequiredError(M.E_LOGIN_WINDOW_CLOSED)
            for p in pages:
                if await self._login_state(p) is True:
                    confirmed[p] = confirmed.get(p, 0) + 1
                    if confirmed[p] >= LOGIN_STABLE_CHECKS:
                        self._remember(True, p.url)
                        return p
                else:
                    confirmed.pop(p, None)
            await asyncio.sleep(1)
        raise LoginRequiredError(M.E_LOGIN_TIMEOUT)

    async def _interactive_login(self, report: Reporter | None) -> bool:
        async with self._browser(headless=False) as ctx:
            page = await self._page(ctx)
            if await self._goto_logged_in(page, sel.DASHBOARD_URL):
                return True
            if report:
                report(JobStatus.LOGIN_REQUIRED, M.msg(M.P_LOGIN_REQUIRED))
            await self._wait_for_login(page)
            return True

    async def _check_session(self) -> bool:
        async with self._browser(headless=True) as ctx:
            page = await self._page(ctx)
            return await self._goto_logged_in(page, sel.DASHBOARD_URL)

    async def _open_dashboard(self) -> None:
        async with self._browser(headless=False) as ctx:
            page = await self._page(ctx)
            await page.goto(sel.DASHBOARD_URL)
            while not page.is_closed():
                await asyncio.sleep(1)

    # ------------------------------------------------------------ upload

    async def _upload(self, job: Job, report: Reporter, cancel: threading.Event) -> str | None:
        headless = self.settings.spotify_headless
        try:
            return await self._upload_once(job, report, cancel, headless)
        except _NeedHeadedLogin:
            await self._interactive_login(report)
            report(JobStatus.UPLOADING, M.msg(M.P_LOGGED_IN))
            return await self._upload_once(job, report, cancel, headless)

    async def _upload_once(self, job: Job, report: Reporter, cancel: threading.Event,
                           headless: bool) -> str | None:
        async with self._browser(headless) as ctx:
            page = await self._page(ctx)
            flow = _WizardFlow(page, job, report, cancel, self.settings, self.show_id)
            try:
                wizard = sel.wizard_url(self.show_id)
                if not await self._goto_logged_in(page, wizard):
                    if headless:
                        raise _NeedHeadedLogin()
                    report(JobStatus.LOGIN_REQUIRED, M.msg(M.P_LOGIN_REQUIRED))
                    page = await self._wait_for_login(page)
                    flow.page = page
                    report(JobStatus.UPLOADING, M.msg(M.P_LOGGED_IN))
                    await page.goto(wizard, wait_until="domcontentloaded")
                return await flow.run()
            except (_NeedHeadedLogin, UploadCancelled, LoginRequiredError):
                raise
            except Exception as e:
                shot = await flow.capture_failure()
                detail = english_detail(e)
                if shot:
                    raise UploadError(M.E_UPLOAD_STEP_FAILED_SHOT, step_key=flow.step,
                                      detail=detail, screenshot=shot) from e
                raise UploadError(M.E_UPLOAD_STEP_FAILED, step_key=flow.step, detail=detail) from e


def english_detail(e: Exception) -> str:
    """First line of an exception, for the 'detail' of an upload error."""
    text = str(e).strip().splitlines()
    return text[0] if text else type(e).__name__


class _WizardFlow:
    def __init__(self, page: Page, job: Job, report: Reporter, cancel: threading.Event,
                 settings: Settings, show_id: str | None):
        self.page = page
        self.job = job
        self.report = report
        self.cancel = cancel
        self.settings = settings
        self.show_id = show_id
        self.episode_id: str | None = None
        self.step = M.S_OPEN_WIZARD

    def _enter(self, step: str, message: str) -> None:
        """Start a wizard step: ``step`` names it in errors, ``message`` is the progress text."""
        if self.cancel.is_set():
            raise UploadCancelled()
        self.step = step
        log.info("[spotify] %s", step)
        self.report(None, M.msg(message))

    async def capture_failure(self) -> str | None:
        try:
            self.settings.logs_dir.mkdir(parents=True, exist_ok=True)
            stem = self.settings.logs_dir / f"{self.job.id}-{datetime.now():%Y%m%d-%H%M%S}"
            await self.page.screenshot(path=f"{stem}.png", full_page=True)
            Path(f"{stem}.html").write_text(await self.page.content(), encoding="utf-8")
            return f"{stem}.png"
        except Exception:
            log.exception("Could not capture failure screenshot")
            return None

    # ---------------------------------------------------------------- helpers

    async def _click_button(self, text: str, exact: bool = True) -> None:
        await self.page.get_by_role("button", name=text, exact=exact).first.click()

    async def _optional_click(self, selector: str, timeout: int = 2000) -> bool:
        loc = self.page.locator(selector).first
        try:
            await loc.wait_for(state="visible", timeout=timeout)
            await loc.click()
            return True
        except PlaywrightTimeout:
            return False

    async def _set_flag(self, selector: str, wanted: bool) -> None:
        inputs = self.page.locator(selector)
        await inputs.first.wait_for(state="attached")
        kind = await inputs.first.get_attribute("type")
        if kind == "radio":
            target = self.page.locator(f'{selector}[value="{str(wanted).lower()}"]')
            await target.check(force=True)
        elif await inputs.first.is_checked() != wanted:
            await inputs.first.set_checked(wanted, force=True)

    async def _fill_number(self, selector: str, value: int | None, label: str) -> None:
        if value is None:
            return
        loc = self.page.locator(selector).first
        if not await loc.count():
            raise UploadError(M.E_FIELD_MISSING, field_key=label)
        await loc.fill(str(value))

    async def _paste_into(self, selector: str, text: str) -> None:
        # The description is a rich-text editor; a synthetic paste keeps line breaks.
        editor = self.page.locator(selector).first
        await editor.click()
        await self.page.keyboard.press("ControlOrMeta+A")
        await self.page.keyboard.press("Delete")
        await editor.evaluate(
            """(el, text) => {
                const dt = new DataTransfer();
                dt.setData('text/plain', text);
                el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
            }""",
            text,
        )
        await self.page.wait_for_timeout(300)
        if not (await editor.inner_text()).strip():
            await self.page.keyboard.insert_text(text)

    async def _pick_schedule(self, when: datetime) -> None:
        """Set the react-dates calendar and the hour/minute/AM-PM pickers (local time)."""
        page = self.page
        await page.locator(sel.PUBLISH_SCHEDULE_RADIO).check(force=True)
        if not await page.locator(sel.CALENDAR_ANY_DAY).first.is_visible():
            await page.locator("button").filter(
                has_text=re.compile(sel.SCHEDULE_DATE_BUTTON_PATTERN)).first.click()
        label = f"{when:%A}, {when:%B} {when.day}, {when.year}"
        day = page.locator(sel.CALENDAR_DAY.format(label=label))
        for _ in range(36):
            if await day.count() and await day.first.is_visible():
                break
            await page.locator(sel.CALENDAR_NEXT).first.click()
            await page.wait_for_timeout(300)
        else:
            raise UploadError(M.E_CALENDAR_DAY_MISSING, date=label)
        await day.first.click()
        await page.get_by_test_id(sel.HOUR_PICKER_TESTID).fill(f"{when:%I}")
        await page.get_by_test_id(sel.MINUTE_PICKER_TESTID).fill(f"{when:%M}")
        await page.get_by_test_id(sel.MERIDIEM_PICKER_TESTID).select_option(f"{when:%p}")
        await page.keyboard.press("Tab")

    async def _submit(self, button_text: str) -> None:
        """Click the final button, confirming a follow-up dialog if Spotify shows one."""
        page = self.page
        await self._click_button(button_text)
        deadline = time.monotonic() + 90
        confirmed = False
        while "/wizard" in page.url and time.monotonic() < deadline:
            dialog = page.get_by_role("dialog").filter(has_not_text="Privacy Preference Center")
            confirm = dialog.get_by_role("button", name=re.compile(rf"^({button_text}|Confirm)$"))
            if not confirmed and await confirm.count() and await confirm.first.is_visible():
                await confirm.first.click()
                confirmed = True
            await page.wait_for_timeout(500)
        if "/wizard" in page.url:
            raise UploadError(M.E_WIZARD_STUCK)

    # ---------------------------------------------------------------- flow

    async def run(self) -> str | None:
        page, meta = self.page, self.job.meta

        self._enter(M.S_PREPARE_PAGE, M.P_OPENING_WIZARD)
        await self._optional_click(sel.COOKIE_ACCEPT)
        await self._optional_click(sel.AUTH_ACCEPT)
        await page.get_by_text(sel.WIZARD_READY_TEXT).first.wait_for()

        self._enter(M.S_UPLOAD_AUDIO, M.P_UPLOADING_AUDIO)
        await page.locator(sel.AUDIO_FILE_INPUT).set_input_files(str(self.job.audio_path))
        await page.get_by_text(sel.UPLOAD_DONE_TEXT).first.wait_for(
            timeout=self.settings.spotify_upload_timeout_s * 1000)
        # The upload already created a draft; its id is now in the URL.
        if m := re.search(sel.WIZARD_EPISODE_ID_PATTERN, page.url):
            self.episode_id = m.group(1)

        self._enter(M.S_TITLE, M.P_FILLING_DETAILS)
        title = page.locator(sel.TITLE_INPUT)
        await title.wait_for(state="visible")
        await page.wait_for_timeout(1000)  # the form re-renders right after the upload
        await title.fill(meta.title)

        self._enter(M.S_DESCRIPTION, M.P_FILLING_DETAILS)
        await self._paste_into(sel.DESCRIPTION_EDITOR, meta.description)

        if self.job.artwork_path:
            self._enter(M.S_ARTWORK, M.P_UPLOADING_ARTWORK)
            await page.locator(sel.ARTWORK_FILE_INPUT).first.set_input_files(str(self.job.artwork_path))
            dialog = page.locator(sel.ARTWORK_DIALOG)
            await dialog.wait_for(state="visible")
            await dialog.get_by_role("button", name=sel.ARTWORK_SAVE_BUTTON_TEXT, exact=True).click()
            await dialog.wait_for(state="hidden", timeout=120_000)

        self._enter(M.S_NUMBERS, M.P_FILLING_NUMBERS)
        await self._fill_number(sel.SEASON_INPUT, meta.season, M.F_SEASON)
        await self._fill_number(sel.EPISODE_NUMBER_INPUT, meta.episode, M.F_EPISODE)
        await page.locator(sel.EPISODE_TYPE_INPUT.format(value=meta.episode_type.value)).check(force=True)

        self._enter(M.S_CONTENT_CHECKS, M.P_CONTENT_CHECKS)
        await self._set_flag(sel.EXPLICIT_INPUT, meta.explicit)
        await self._set_flag(sel.SPONSORED_INPUT, meta.sponsored)

        self._enter(M.S_NEXT, M.P_GOING_TO_REVIEW)
        await self._click_button(sel.NEXT_BUTTON_TEXT)
        await page.locator(sel.PUBLISH_NOW_RADIO).wait_for(state="attached")

        if meta.publish_mode is PublishMode.DRAFT:
            self._enter(M.S_SAVE_DRAFT, M.P_SAVING_DRAFT)
            await self._click_button(sel.CLOSE_BUTTON_TEXT)
            await page.get_by_role("dialog").get_by_role(
                "button", name=sel.SAVE_DRAFT_BUTTON_TEXT, exact=True).click()
            await page.wait_for_url(lambda u: "/wizard" not in u, timeout=60_000)
        elif meta.publish_mode is PublishMode.NOW:
            self._enter(M.S_PUBLISH, M.P_PUBLISHING)
            await page.locator(sel.PUBLISH_NOW_RADIO).check(force=True)
            await self._submit(sel.PUBLISH_BUTTON_TEXT)
        else:
            self._enter(M.S_SCHEDULE, M.P_SCHEDULING)
            await self._pick_schedule(meta.publish_at.astimezone())
            await self._submit(sel.SCHEDULE_BUTTON_TEXT)

        self._enter(M.S_CONFIRM, M.P_WAITING_SAVE)
        # Closing too fast has been seen to leave an "Untitled" draft; let it settle.
        await page.wait_for_timeout(3000)
        if self.show_id and self.episode_id:
            return sel.episode_url(self.show_id, self.episode_id)
        return None
