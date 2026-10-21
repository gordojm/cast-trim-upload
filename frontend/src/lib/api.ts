import i18n from "@/i18n"
import { isApiMessage, translateMessage, type ApiMessage } from "@/i18n/messages"

export type SourceKind = "youtube" | "twitch"
export type PublishMode = "draft" | "now" | "schedule"
export type EpisodeType = "full" | "trailer" | "bonus"
export type JobStatus =
  | "queued"
  | "downloading"
  | "converting"
  | "ready_for_review"
  | "login_required"
  | "uploading"
  | "done"
  | "failed"
  | "cancelled"

export interface EpisodeMeta {
  title: string
  description: string
  season: number | null
  episode: number | null
  episode_type: EpisodeType
  explicit: boolean
  sponsored: boolean
  publish_mode: PublishMode
  publish_at: string | null
}

export interface Job {
  id: string
  created_at: string
  updated_at: string
  url: string
  source_kind: SourceKind
  source_id: string
  source_title: string | null
  start_s: number
  end_s: number
  meta: EpisodeMeta
  status: JobStatus
  progress: number | null
  message: ApiMessage | null
  error: ApiMessage | null
  has_artwork: boolean
  audio_duration_s: number | null
  spotify_url: string | null
  audio_ready: boolean
}

export interface ProbeResult {
  kind: SourceKind
  id: string
  title: string | null
  duration_s: number | null
  thumbnail: string | null
  uploader: string | null
}

export interface ToolHealth {
  ffmpeg: string | null
  twitch_cli: string | null
  js_runtime: string | null
  chromium: boolean
  yt_dlp_version: string
  ok: boolean
}

export interface SpotifySession {
  logged_in: boolean | null
  checked_at: string | null
  busy: boolean
}

export const ACTIVE_STATUSES: JobStatus[] = [
  "queued",
  "downloading",
  "converting",
  "login_required",
  "uploading",
]

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail
  if (isApiMessage(detail)) return translateMessage(detail)
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((p: unknown) => p !== "body").join(".") : ""
        const msg = String(d?.msg ?? d).replace(/^Value error, /, "")
        return loc ? `${loc}: ${msg}` : msg
      })
      .join("; ")
  }
  return i18n.t("app.request_failed")
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers:
      init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json", ...init.headers }
        : init?.headers,
  })
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      detail = (await res.json()).detail
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, describe(detail))
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

const json = (body: unknown) => JSON.stringify(body)

export const api = {
  health: (refresh = false) => request<ToolHealth>(`/health${refresh ? "?refresh=true" : ""}`),
  probe: (url: string) => request<ProbeResult>("/probe", { method: "POST", body: json({ url }) }),
  suggest: () => request<{ season: number | null; episode: number | null }>("/suggest"),
  jobs: () => request<Job[]>("/jobs"),
  createJob: (
    body: { url: string; start: string; end: string; meta: EpisodeMeta },
    sourceTitle?: string | null
  ) =>
    request<Job>(
      `/jobs${sourceTitle ? `?source_title=${encodeURIComponent(sourceTitle)}` : ""}`,
      { method: "POST", body: json(body) }
    ),
  updateMeta: (id: string, meta: EpisodeMeta) =>
    request<Job>(`/jobs/${id}/meta`, { method: "PUT", body: json(meta) }),
  uploadArtwork: (id: string, file: File) => {
    const form = new FormData()
    form.append("file", file)
    return request<Job>(`/jobs/${id}/artwork`, { method: "POST", body: form })
  },
  deleteArtwork: (id: string) => request<Job>(`/jobs/${id}/artwork`, { method: "DELETE" }),
  startUpload: (id: string) => request<Job>(`/jobs/${id}/upload`, { method: "POST" }),
  retry: (id: string) => request<Job>(`/jobs/${id}/retry`, { method: "POST" }),
  discard: (id: string) => request<Job>(`/jobs/${id}`, { method: "DELETE" }),
  deleteHistory: (id: string) => request<void>(`/history/${id}`, { method: "DELETE" }),
  spotifySession: (refresh = false) =>
    request<SpotifySession>(`/spotify/session${refresh ? "?refresh=true" : ""}`),
  spotifyLogin: () => request<SpotifySession>("/spotify/login", { method: "POST" }),
}

export const audioUrl = (id: string, version: string) => `/api/jobs/${id}/audio?v=${encodeURIComponent(version)}`
export const artworkUrl = (id: string, version: string) =>
  `/api/jobs/${id}/artwork?v=${encodeURIComponent(version)}`
