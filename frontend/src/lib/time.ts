// Mirrors backend/cast_trim_upload/timeparse.py
import i18n from "@/i18n"

const SECONDS_RE = /^\d+(?:\.\d+)?$/
const CLOCK_RE = /^(?:(\d+):)?(\d{1,2}):(\d+(?:\.\d+)?)$/

/** Seconds for "hh:mm:ss[.fff]", "mm:ss" or plain seconds; null when invalid. */
export function parseTime(value: string): number | null {
  const text = value.trim()
  if (SECONDS_RE.test(text)) return Number(text)
  const m = CLOCK_RE.exec(text)
  if (!m) return null
  const hours = m[1] !== undefined ? Number(m[1]) : 0
  const minutes = Number(m[2])
  const seconds = Number(m[3])
  if (seconds >= 60 || (m[1] !== undefined && minutes >= 60)) return null
  return hours * 3600 + minutes * 60 + seconds
}

export function formatTime(totalSeconds: number): string {
  const ms = Math.round(totalSeconds * 1000)
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  const rest = ms % 1000
  const base = `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
  return rest ? `${base}.${String(rest).padStart(3, "0")}` : base
}

/** "1 h 02 min" style length for display, in the current language. */
export function formatLength(seconds: number): string {
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (n: number) => String(n).padStart(2, "0")
  if (h) return i18n.t("time.hours_minutes", { h, mm: pad(m) })
  if (m) return i18n.t("time.minutes_seconds", { m, ss: pad(s) })
  return i18n.t("time.seconds", { s })
}

/** Value for <input type="datetime-local"> from an ISO string (local time). */
export function toLocalInput(iso: string | null): string {
  if (!iso) return ""
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
