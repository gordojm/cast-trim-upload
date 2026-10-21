import { z } from "zod"

import type { ApiMessage } from "@/i18n/messages"

import type { EpisodeMeta } from "./api"
import { parseTime } from "./time"

// Keep in sync with backend/cast_trim_upload/models.py
export const TITLE_MAX = 200
export const DESCRIPTION_MAX = 4000
export const ARTWORK_MIN_PX = 1400
export const ARTWORK_MAX_MB = 10
export const ARTWORK_MAX_BYTES = ARTWORK_MAX_MB * 1024 * 1024

// Validation messages are locale keys (validation.*); these fill their {{placeholders}}.
export const VALIDATION_PARAMS = {
  titleMax: TITLE_MAX,
  descriptionMax: DESCRIPTION_MAX,
  min: ARTWORK_MIN_PX,
  mb: ARTWORK_MAX_MB,
}

const YOUTUBE_RE =
  /^(https?:\/\/)?((www|m|music)\.)?(youtube\.com\/(watch\?(.*&)?v=|live\/|shorts\/|embed\/)|youtu\.be\/)[A-Za-z0-9_-]{11}/i
const TWITCH_RE =
  /^(https?:\/\/)?((www|m|player)\.)?twitch\.tv\/(videos\/\d+|[A-Za-z0-9_]+\/v(ideo)?\/\d+|\?(.*&)?video=v?\d+)/i

export function detectKind(url: string): "youtube" | "twitch" | null {
  const text = url.trim()
  if (YOUTUBE_RE.test(text)) return "youtube"
  if (TWITCH_RE.test(text)) return "twitch"
  return null
}

const optionalPositiveInt = z
  .string()
  .trim()
  .refine((v) => v === "" || /^[1-9]\d*$/.test(v), "validation.number_positive")

export const detailsSchema = z
  .object({
    title: z.string().trim().min(1, "validation.title_required").max(TITLE_MAX, "validation.title_max"),
    description: z
      .string()
      .trim()
      .min(1, "validation.description_required")
      .max(DESCRIPTION_MAX, "validation.description_max"),
    season: optionalPositiveInt,
    episode: optionalPositiveInt,
    episode_type: z.enum(["full", "trailer", "bonus"]),
    explicit: z.enum(["yes", "no"], { error: "validation.explicit_required" }),
    sponsored: z.boolean(),
    publish_mode: z.enum(["draft", "now", "schedule"]),
    publish_at: z.string(),
  })
  // `when` makes these run even while other fields are invalid (zod skips object
  // refinements otherwise), so every error shows up on the first submit.
  .refine((v) => v.publish_mode !== "schedule" || !!v.publish_at, {
    path: ["publish_at"],
    message: "validation.publish_at_required",
    when: () => true,
  })
  .refine(
    (v) => v.publish_mode !== "schedule" || !v.publish_at || new Date(v.publish_at).getTime() > Date.now(),
    { path: ["publish_at"], message: "validation.publish_at_future", when: () => true }
  )

export type DetailsValues = z.infer<typeof detailsSchema>

const timeField = (requiredKey: string) =>
  z
    .string()
    .trim()
    .min(1, requiredKey)
    .refine((v) => parseTime(v) !== null, "validation.time_format")

/** Source fields; `getDuration` supplies the probed video length (if known). */
export function makeEpisodeSchema(getDuration: () => number | null) {
  const times = (v: { start: string; end: string }) => [parseTime(v.start), parseTime(v.end)] as const
  return z
    .object({
      url: z
        .string()
        .trim()
        .min(1, "validation.url_required")
        .refine((v) => detectKind(v) !== null, "validation.url_invalid"),
      start: timeField("validation.start_required"),
      end: timeField("validation.end_required"),
      details: detailsSchema,
    })
    .refine(
      (v) => {
        const [start, end] = times(v)
        return start === null || end === null || end > start
      },
      { path: ["end"], message: "validation.end_after_start", when: () => true }
    )
    .refine(
      (v) => {
        const [, end] = times(v)
        const duration = getDuration()
        return end === null || !duration || end <= duration + 1
      },
      { path: ["end"], message: "validation.end_past_video", when: () => true }
    )
}

export type EpisodeValues = z.infer<ReturnType<typeof makeEpisodeSchema>>

export const emptyDetails: DetailsValues = {
  title: "",
  description: "",
  season: "",
  episode: "",
  episode_type: "full",
  explicit: undefined as unknown as "yes" | "no",
  sponsored: false,
  publish_mode: "draft",
  publish_at: "",
}

export function detailsToMeta(v: DetailsValues): EpisodeMeta {
  return {
    title: v.title.trim(),
    description: v.description.trim(),
    season: v.season ? Number(v.season) : null,
    episode: v.episode ? Number(v.episode) : null,
    episode_type: v.episode_type,
    explicit: v.explicit === "yes",
    sponsored: v.sponsored,
    publish_mode: v.publish_mode,
    publish_at: v.publish_mode === "schedule" && v.publish_at ? new Date(v.publish_at).toISOString() : null,
  }
}

export function metaToDetails(m: EpisodeMeta, toLocal: (iso: string | null) => string): DetailsValues {
  return {
    title: m.title,
    description: m.description,
    season: m.season ? String(m.season) : "",
    episode: m.episode ? String(m.episode) : "",
    episode_type: m.episode_type,
    explicit: m.explicit ? "yes" : "no",
    sponsored: m.sponsored,
    publish_mode: m.publish_mode,
    publish_at: toLocal(m.publish_at),
  }
}

/** Check type, size and dimensions of an artwork file; returns a translatable problem or null. */
export async function validateArtwork(file: File): Promise<ApiMessage | null> {
  if (!["image/jpeg", "image/png"].includes(file.type)) return { key: "validation.artwork_type" }
  if (file.size > ARTWORK_MAX_BYTES) return { key: "validation.artwork_too_big", params: { mb: ARTWORK_MAX_MB } }
  const url = URL.createObjectURL(file)
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    const [w, h] = [img.naturalWidth, img.naturalHeight]
    if (w !== h) return { key: "validation.artwork_not_square", params: { w, h } }
    if (w < ARTWORK_MIN_PX) return { key: "validation.artwork_too_small", params: { min: ARTWORK_MIN_PX } }
    return null
  } catch {
    return { key: "validation.artwork_unreadable" }
  } finally {
    URL.revokeObjectURL(url)
  }
}
