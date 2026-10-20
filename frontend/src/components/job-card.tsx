import { zodResolver } from "@hookform/resolvers/zod"
import {
  CheckCircle2Icon,
  ExternalLinkIcon,
  Loader2Icon,
  PencilIcon,
  RotateCcwIcon,
  Trash2Icon,
  UploadIcon,
} from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { z } from "zod"

import { ArtworkPicker } from "@/components/artwork-picker"
import { EpisodeDetailsFields, type WithDetails } from "@/components/episode-details-fields"
import { SourceBadge } from "@/components/source-badge"
import { StatusBadge } from "@/components/status-badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { formatDateTime } from "@/i18n/format"
import { useMessageText } from "@/i18n/messages"
import { api, artworkUrl, audioUrl, type Job } from "@/lib/api"
import { detailsSchema, detailsToMeta, metaToDetails } from "@/lib/schema"
import { formatLength, formatTime, toLocalInput } from "@/lib/time"

const editSchema = z.object({ details: detailsSchema })

function useAction() {
  const [busy, setBusy] = useState<string | null>(null)
  const run = async (name: string, fn: () => Promise<unknown>, success?: string) => {
    setBusy(name)
    try {
      await fn()
      if (success) toast.success(success)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(null)
    }
  }
  return { busy, run }
}

function EditDetails({ job, onDone }: { job: Job; onDone: () => void }) {
  const { t } = useTranslation()
  const form = useForm<WithDetails>({
    resolver: zodResolver(editSchema),
    mode: "onTouched",
    defaultValues: { details: metaToDetails(job.meta, toLocalInput) },
  })
  const [artwork, setArtwork] = useState<File | null>(null)

  const onSubmit = async (values: WithDetails) => {
    try {
      await api.updateMeta(job.id, detailsToMeta(values.details))
      if (artwork) await api.uploadArtwork(job.id, artwork)
      toast.success(t("job.details_saved"))
      onDone()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4 rounded-lg border p-4">
      <EpisodeDetailsFields form={form} idPrefix={`edit-${job.id}`} />
      <ArtworkPicker
        file={artwork}
        onChange={setArtwork}
        existingUrl={job.has_artwork ? artworkUrl(job.id, job.updated_at) : null}
        onRemoveExisting={() => api.deleteArtwork(job.id).catch((e) => toast.error(e.message))}
      />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("job.cancel")}
        </Button>
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting && <Loader2Icon className="animate-spin" />}
          {t("job.save_details")}
        </Button>
      </div>
    </form>
  )
}

function MetaSummary({ job }: { job: Job }) {
  const { t } = useTranslation()
  const m = job.meta
  const se = [m.season && `S${m.season}`, m.episode && `E${m.episode}`].filter(Boolean).join(" · ")
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      <dt className="text-muted-foreground">{t("job.clip")}</dt>
      <dd className="font-mono text-xs leading-5">
        {formatTime(job.start_s)} → {formatTime(job.end_s)} ({formatLength(job.end_s - job.start_s)})
      </dd>
      {se && (
        <>
          <dt className="text-muted-foreground">{t("job.number")}</dt>
          <dd>
            {se}
            {m.episode_type !== "full" && ` · ${t(`details.type_${m.episode_type}`)}`}
          </dd>
        </>
      )}
      <dt className="text-muted-foreground">{t("job.content")}</dt>
      <dd>
        {m.explicit ? t("job.explicit") : t("job.not_explicit")}
        {m.sponsored && ` · ${t("job.sponsored")}`}
        {job.has_artwork && ` · ${t("job.custom_artwork")}`}
      </dd>
      <dt className="text-muted-foreground">{t("job.on_upload")}</dt>
      <dd>
        {t(`details.mode_${m.publish_mode}`)}
        {m.publish_at && ` · ${formatDateTime(m.publish_at)}`}
      </dd>
    </dl>
  )
}

export function JobCard({ job }: { job: Job }) {
  const { t } = useTranslation()
  const messageText = useMessageText()
  const [editing, setEditing] = useState(false)
  const { busy, run } = useAction()
  const working = ["queued", "downloading", "converting", "uploading", "login_required"].includes(job.status)
  const canEdit = job.status === "ready_for_review" || job.status === "failed"
  const canDiscard = !["uploading", "login_required", "done", "cancelled"].includes(job.status)
  const mode = t(`details.mode_${job.meta.publish_mode}`)

  return (
    <Card size="sm" className={job.status === "login_required" ? "ring-2 ring-amber-500/60" : undefined}>
      <CardHeader>
        <CardTitle className="line-clamp-2 leading-snug">{job.meta.title}</CardTitle>
        <CardDescription className="flex items-center gap-2 truncate">
          <SourceBadge kind={job.source_kind} />
          <a href={job.url} target="_blank" rel="noreferrer" className="truncate hover:underline">
            {job.source_title ?? job.url}
          </a>
        </CardDescription>
        <CardAction>
          <StatusBadge status={job.status} />
        </CardAction>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {working && (
          <div className="flex flex-col gap-1.5">
            <Progress
              value={job.progress !== null ? job.progress * 100 : 100}
              className={job.progress === null ? "animate-pulse opacity-50" : undefined}
            />
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2Icon className="size-3 animate-spin" />
              {job.message ? messageText(job.message) : t("job.working")}
              {job.progress !== null && <span className="ml-auto tabular-nums">{Math.round(job.progress * 100)}%</span>}
            </p>
          </div>
        )}

        {job.status === "login_required" && (
          <Alert>
            <AlertTitle>{t("job.login_title")}</AlertTitle>
            <AlertDescription>{t("job.login_body")}</AlertDescription>
          </Alert>
        )}

        {job.status === "failed" && job.error && (
          <Alert variant="destructive">
            <AlertTitle>{job.audio_ready ? t("job.upload_failed") : t("job.prepare_failed")}</AlertTitle>
            <AlertDescription className="break-words">{messageText(job.error)}</AlertDescription>
          </Alert>
        )}

        {job.audio_ready && job.status !== "done" && (
          <div className="flex flex-col gap-1">
            <audio controls preload="metadata" src={audioUrl(job.id, job.id)} className="w-full" />
            {job.audio_duration_s && (
              <p className="text-xs text-muted-foreground">
                {t("job.audio_hint", { length: formatLength(job.audio_duration_s) })}
              </p>
            )}
          </div>
        )}

        {job.status === "done" && (
          <p className="flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
            <CheckCircle2Icon className="size-4" /> {messageText(job.message)}
            {job.spotify_url && (
              <a href={job.spotify_url} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center gap-1 underline">
                {t("job.open")} <ExternalLinkIcon className="size-3" />
              </a>
            )}
          </p>
        )}

        {editing ? <EditDetails job={job} onDone={() => setEditing(false)} /> : <MetaSummary job={job} />}
      </CardContent>

      {!editing && (canEdit || canDiscard) && (
        <CardFooter className="flex flex-wrap justify-end gap-2">
          {canDiscard && (
            <Button
              variant="ghost"
              size="sm"
              disabled={!!busy}
              onClick={() => {
                if (confirm(t("job.confirm_discard")))
                  run("discard", () => api.discard(job.id), t("job.discarded"))
              }}
            >
              <Trash2Icon /> {t("job.discard")}
            </Button>
          )}
          {canEdit && (
            <Button variant="outline" size="sm" disabled={!!busy} onClick={() => setEditing(true)}>
              <PencilIcon /> {t("job.edit")}
            </Button>
          )}
          {job.status === "failed" && (
            <Button variant="outline" size="sm" disabled={!!busy} onClick={() => run("retry", () => api.retry(job.id))}>
              {busy === "retry" ? <Loader2Icon className="animate-spin" /> : <RotateCcwIcon />}
              {job.audio_ready ? t("job.retry_upload") : t("job.retry")}
            </Button>
          )}
          {job.status === "ready_for_review" && (
            <Button size="sm" disabled={!!busy} onClick={() => run("upload", () => api.startUpload(job.id))}>
              {busy === "upload" ? <Loader2Icon className="animate-spin" /> : <UploadIcon />}
              {t("job.upload", { mode })}
            </Button>
          )}
        </CardFooter>
      )}
    </Card>
  )
}
