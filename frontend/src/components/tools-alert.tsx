import { TriangleAlertIcon } from "lucide-react"
import { useEffect, useState } from "react"
import { Trans, useTranslation } from "react-i18next"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { api, type ToolHealth } from "@/lib/api"

/** Shown only when a required tool is missing. */
export function ToolsAlert() {
  const { t } = useTranslation()
  const [health, setHealth] = useState<ToolHealth | null>(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setOffline(true))
  }, [])

  if (offline) {
    return (
      <Alert variant="destructive">
        <TriangleAlertIcon />
        <AlertTitle>{t("tools.offline_title")}</AlertTitle>
        <AlertDescription>{t("tools.offline_body")}</AlertDescription>
      </Alert>
    )
  }
  if (!health || health.ok) return null

  // ffmpeg and TwitchDownloaderCLI are product names; the others are descriptions.
  const missing = [
    !health.ffmpeg && "ffmpeg",
    !health.twitch_cli && "TwitchDownloaderCLI",
    !health.chromium && t("tools.chromium"),
    !health.js_runtime && t("tools.js_runtime"),
  ].filter(Boolean)

  return (
    <Alert variant="destructive">
      <TriangleAlertIcon />
      <AlertTitle>{t("tools.missing_title")}</AlertTitle>
      <AlertDescription>
        <Trans
          i18nKey="tools.missing_body"
          values={{ tools: missing.join(", ") }}
          components={{ code: <code className="font-mono" /> }}
        />
      </AlertDescription>
    </Alert>
  )
}
