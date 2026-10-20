"""Every Spotify for Creators URL, selector and UI text the uploader relies on.

When Spotify changes their site, this is the file to fix. Failure screenshots and HTML
dumps land in data/logs/ to help.

Verified against the live site on 2026-10-19 (draft upload with artwork, season,
episode, episode type and a schedule date). Not yet exercised: the final click of
"Publish" and "Schedule", which publish for real.
"""

BASE = "https://creators.spotify.com"
DASHBOARD_URL = f"{BASE}/pod/dashboard/home"  # redirects to /home/show/<show id>


def wizard_url(show_id: str | None) -> str:
    if show_id:
        return f"{BASE}/pod/show/{show_id}/episode/wizard"
    return f"{BASE}/pod/dashboard/episode/wizard"


def episode_url(show_id: str, episode_id: str) -> str:
    return f"{BASE}/pod/show/{show_id}/episode/{episode_id}/details"


# URL fragments that mean "not logged in" (login form, captcha, emailed-code step,
# and the creators.spotify.com/pod/login/... OAuth callback)
LOGIN_URL_MARKERS = ("accounts.spotify.com", "challenge.spotify.com", "/login")
# Elements only present on a login screen (Spotify accounts form, old creators landing)
LOGIN_PAGE_MARKER = '#login-username, input[name="username"], button:has-text("Continue with Spotify")'
# Any creators.spotify.com page that is not a login step means "logged in".
# Since late 2026 the dashboard lives at /home/show/<show id>.
CREATORS_HOST = "creators.spotify.com"
# Show id inside dashboard URLs (/home/show/<id>, /pod/show/<id>)
SHOW_ID_PATTERN = r"/show/([A-Za-z0-9]{22})"
# Once a file is uploaded, the wizard URL carries the new episode's id
WIZARD_EPISODE_ID_PATTERN = r"/episode/([A-Za-z0-9]{22})/wizard"

COOKIE_ACCEPT = "#onetrust-accept-btn-handler"
AUTH_ACCEPT = 'button[data-testid="auth-accept"]'

# Step 1: upload. Uploading creates the episode as a draft right away.
WIZARD_READY_TEXT = "Select a file"
AUDIO_FILE_INPUT = "#uploadAreaInput"
UPLOAD_DONE_TEXT = "Preview ready!"

# Step 2: details (title max 200, description max 4000 characters)
TITLE_INPUT = "#title-input"
DESCRIPTION_EDITOR = 'div[role="textbox"]'  # Slate rich-text editor; each line becomes a paragraph
ARTWORK_FILE_INPUT = 'input[type="file"][accept*="image"]'
ARTWORK_SAVE_BUTTON_TEXT = "Save"  # in the crop dialog that opens after choosing the image
ARTWORK_DIALOG = '[data-encore-id="dialogConfirmation"]'
EXPLICIT_INPUT = 'input[name="podcastEpisodeIsExplicit"]'  # checkbox
SPONSORED_INPUT = 'input[name="podcastEpisodeContainsSponsoredContent"]'  # checkbox
SEASON_INPUT = 'input[name="podcastSeasonNumber"]'
EPISODE_NUMBER_INPUT = 'input[name="podcastEpisodeNumber"]'
EPISODE_TYPE_INPUT = 'input[name="podcastEpisodeType"][value="{value}"]'  # full / trailer / bonus
NEXT_BUTTON_TEXT = "Next"

# Step 3: review & publish
PUBLISH_NOW_RADIO = "#publish-date-now"
PUBLISH_SCHEDULE_RADIO = "#publish-date-schedule"
# Schedule: a button showing MM/DD/YYYY opens a react-dates calendar; time is three
# controls in the browser's local time zone.
SCHEDULE_DATE_BUTTON_PATTERN = r"^\d{2}/\d{2}/\d{4}$"
CALENDAR_DAY = '[data-visible="true"] td[role="button"][aria-label="{label}"]'  # "Friday, November 20, 2026"
CALENDAR_ANY_DAY = '[data-visible="true"] td[role="button"]'
CALENDAR_NEXT = '[class*="calendarDatePicker__navIcon--right"]'
HOUR_PICKER_TESTID = "hour-picker"
MINUTE_PICKER_TESTID = "minute-picker"
MERIDIEM_PICKER_TESTID = "meridiem-picker"  # <select> with AM / PM
PUBLISH_BUTTON_TEXT = "Publish"
SCHEDULE_BUTTON_TEXT = "Schedule"

# Draft: the header "Close" button asks "Save draft?" with "Keep editing" / "Save draft"
CLOSE_BUTTON_TEXT = "Close"
SAVE_DRAFT_BUTTON_TEXT = "Save draft"
