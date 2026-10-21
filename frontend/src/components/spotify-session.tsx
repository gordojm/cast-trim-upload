import { Loader2Icon, LogInIcon, RefreshCwIcon } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { formatClock } from "@/i18n/format"
import { api, type SpotifySession } from "@/lib/api"
import { cn } from "@/lib/utils"

export function SpotifySessionIndicator() {
  const { t } = useTranslation()
  const [session, setSession] = useState<SpotifySession | null>(null)
  const [action, setAction] = useState<"check" | "login" | null>(null)

  const check = useCallback(async () => {
    setAction("check")
    try {
      setSession(await api.spotifySession(true))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setAction(null)
    }
  }, [])

  useEffect(() => {
    api
      .spotifySession()
      .then((s) => {
        setSession(s)
        if (s.logged_in === null && !s.busy) check()
      })
      .catch(() => {})
  }, [check])

  const login = async () => {
    setAction("login")
    toast.info(t("spotify.login_opening"))
    try {
      setSession(await api.spotifyLogin())
      toast.success(t("spotify.login_success"))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setAction(null)
    }
  }

  const state = session?.logged_in
  const label =
    action === "check"
      ? t("spotify.checking")
      : state
        ? t("spotify.connected")
        : state === false
          ? t("spotify.logged_out")
          : t("spotify.unknown")

  return (
    <div className="flex items-center gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="hidden items-center gap-2 rounded-full border px-2.5 py-1 text-xs sm:flex">
            <span
              className={cn(
                "size-2 rounded-full",
                state ? "bg-emerald-500" : state === false ? "bg-amber-500" : "bg-muted-foreground/40"
              )}
            />
            {label}
          </span>
        </TooltipTrigger>
        <TooltipContent>
          {session?.checked_at ? t("spotify.checked_at", { time: formatClock(session.checked_at) }) : t("spotify.not_checked")}
        </TooltipContent>
      </Tooltip>
      <Button variant="ghost" size="icon-sm" aria-label={t("spotify.check")} disabled={!!action} onClick={check}>
        <RefreshCwIcon className={action === "check" ? "animate-spin" : undefined} />
      </Button>
      {state !== true && (
        <Button variant="outline" size="sm" disabled={!!action} onClick={login}>
          {action === "login" ? <Loader2Icon className="animate-spin" /> : <LogInIcon />}
          {t("spotify.login")}
        </Button>
      )}
    </div>
  )
}
