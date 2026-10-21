# cast-trim-upload

Turn part of a YouTube video or Twitch VOD into a MultiCast episode on Spotify. Paste a link, set the start and end times, and fill in the episode details. The app downloads only that section as MP3 320 kbps, lets you listen to it, and uploads it to Spotify for Creators. Spotify then distributes the show to the other platforms through its RSS feed.

The Spotify step drives the Spotify for Creators website with a scripted browser, because Spotify has no public upload API. Its selectors still need checking against the live site with a real account: test with "Save as draft" first.

## Install once

You need Python 3.12 or newer and Node.js 20 or newer. Node.js is also what yt-dlp uses to read YouTube.

1. Create the Python environment and install the app:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Download the external tools into `data/tools/`: TwitchDownloaderCLI, ffmpeg and the Chromium browser for Playwright.

   ```bash
   cast-trim-upload setup
   ```

3. Build the web interface:

   ```bash
   cd frontend
   npm install
   npm run build
   ```

4. Check that everything is in place. Every line should say `OK`.

   ```bash
   cast-trim-upload doctor
   ```

## Publish an episode

1. Double-click `start.bat` in the project folder. The app opens in your browser at `http://127.0.0.1:8765`. Keep the black window open while you use the app; closing it stops the app. Double-clicking again while it runs just reopens the page.
2. Paste a YouTube or Twitch VOD link. The app shows the video title and length.
3. Enter the start and end times as `hh:mm:ss`, `mm:ss` or seconds.
4. Fill in the episode details. Title, description and the explicit-content choice are required. Season and episode are suggested from the last upload.
5. Choose what happens on Spotify: save as draft, publish now, or schedule a date.
6. Click "Prepare audio". The episode appears under "In progress" with its download progress.
7. When it says "Ready to review", listen to the start and the end of the clip. You can still edit the details or the artwork.
8. Click "Upload to Spotify". When it finishes, the temporary files are deleted and the episode moves to "History".

If the upload fails, the audio stays on disk and "Retry upload" tries again without downloading. "Discard" deletes the episode and its temporary files.

## Log in to Spotify once

The first upload opens a browser window on the Spotify login page. Log in there, including any code Spotify sends you, and the upload continues by itself. The session is saved in `data/browser-profile/` and reused until Spotify expires it.

You can also log in ahead of time with `cast-trim-upload login` or the "Log in" button in the app header. The app never stores your password.

## Settings

Copy `.env.example` to `.env` to change a setting. All of them are optional.

| Variable | Default | What it does |
|---|---|---|
| `CTU_SPOTIFY_SHOW_ID` | empty | Show to upload to, if the account manages more than one. It is the id after `/pod/show/` in the dashboard URL. |
| `CTU_SPOTIFY_HEADLESS` | `false` | Hides the browser during uploads. A window still opens when a login is needed. |
| `CTU_PORT` | `8765` | Port of the web app. |
| `CTU_OPEN_BROWSER` | `true` | Opens the app in your browser on start. |
| `CTU_FFMPEG_PATH`, `CTU_TWITCH_CLI_PATH` | empty | Use tools from another location instead of `data/tools/`. |
| `CTU_DATA_DIR` | `./data` | Where the session, temporary files, logs and history live. |

## When an upload breaks

Spotify changes its website from time to time, and the upload then stops at a specific step. The error in the app names that step and points to a screenshot in `data/logs/`. Next to it is an HTML copy of the page.

All selectors and button texts the uploader uses live in `backend/cast_trim_upload/spotify/selectors.py`. Fixing a broken upload usually means updating one or two lines there.

If YouTube downloads start failing, update yt-dlp with `cast-trim-upload setup --update`.

## Add a language

The app ships in English and Spanish; the language menu in the header switches between them. Every text the app shows, including the backend's progress and error messages, lives in one file per language in `frontend/src/locales/`.

1. Copy `frontend/src/locales/en.json` to `<code>.json`, for example `pt.json`, and translate the values. Keep the keys, the `{{placeholders}}` and the `<tags>` as they are.
2. Add the language to `frontend/src/i18n/languages.ts`, for example `{ code: "pt", name: "Português" }`.
3. Run `pytest tests/test_locales.py`. It names any missing key, dropped placeholder or unregistered language. Then rebuild with `npm run build`.

## Develop

Run the backend and the Vite dev server in two terminals. Vite forwards `/api` to the backend.

```bash
cast-trim-upload serve --no-browser --reload
cd frontend && npm run dev
```

Run the tests. Tests marked `network` download real clips from YouTube and Twitch.

```bash
pytest -m "not network"
pytest -m network
```

## Annex: how it works

| Step | Tool | Detail |
|---|---|---|
| Detect the source | `sources.py` | Recognizes YouTube (`watch`, `youtu.be`, `live`, `shorts`) and Twitch (`videos/<id>`) links. |
| YouTube section | yt-dlp and ffmpeg | yt-dlp finds the audio stream; ffmpeg reads only the requested range and encodes MP3 in one pass. The cut is accurate to the audio sample. |
| Twitch section | TwitchDownloaderCLI | Downloads only the range, audio only (`.m4a`). ffmpeg then converts it to MP3. |
| Check the result | `audio.py` | Fails if the MP3 length differs from end minus start by more than 1.5 s. |
| Upload | Playwright | Uploads the file, fills in the form and submits it in a Chromium browser with a saved profile. |
| Clean up | `workspace.py` | Deletes the episode folder in `data/tmp/` after an upload or discard. On start, deletes folders older than 24 hours that no episode uses. |

The backend is FastAPI (`backend/cast_trim_upload/`). It sends live progress to the page through Server-Sent Events and keeps the history in SQLite (`data/history.db`). The interface is React with Tailwind and shadcn/ui (`frontend/`), with light, dark and system themes.

Everything in `data/` is local and ignored by git. It holds the Spotify session cookies, so do not share it.
