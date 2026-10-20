import { zodResolver } from "@hookform/resolvers/zod"
import { Loader2Icon, ScissorsIcon } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useForm, type UseFormReturn } from "react-hook-form"
import { Trans, useTranslation } from "react-i18next"
import { toast } from "sonner"

import { ArtworkPicker } from "@/components/artwork-picker"
import { EpisodeDetailsFields, type WithDetails } from "@/components/episode-details-fields"
import { FieldErrorText } from "@/components/field-error-text"
import { SourceBadge } from "@/components/source-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { api, type ProbeResult } from "@/lib/api"
import { detailsToMeta, detectKind, emptyDetails, makeEpisodeSchema, type EpisodeValues } from "@/lib/schema"
import { formatLength, formatTime, parseTime } from "@/lib/time"

const PROBE_DEBOUNCE_MS = 600

function SectionTitle({ step, children }: { step: number; children: React.ReactNode }) {
  return (
    <h3 className="flex items-center gap-2 text-sm font-medium">
      <span className="flex size-5 items-center justify-center rounded-full bg-primary text-[0.7rem] text-primary-foreground">
        {step}
      </span>
      {children}
    </h3>
  )
}

function Required() {
  return <span className="text-destructive">*</span>
}

export function NewEpisodeForm() {
  const { t } = useTranslation()
  const durationRef = useRef<number | null>(null)
  const schema = useMemo(() => makeEpisodeSchema(() => durationRef.current), [])
  const form = useForm<EpisodeValues>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: { url: "", start: "", end: "", details: emptyDetails },
  })
  const { register, handleSubmit, watch, formState, setValue, reset } = form
  const errors = formState.errors

  const [artwork, setArtwork] = useState<File | null>(null)
  const [probe, setProbe] = useState<ProbeResult | null>(null)
  const [probing, setProbing] = useState(false)
  const [probeError, setProbeError] = useState<string | null>(null)

  // Suggest season / next episode number from history.
  useEffect(() => {
    api
      .suggest()
      .then((s) => {
        if (s.season) setValue("details.season", String(s.season))
        if (s.episode) setValue("details.episode", String(s.episode))
      })
      .catch(() => {})
  }, [setValue])

  const url = watch("url")
  const kind = detectKind(url ?? "")

  useEffect(() => {
    setProbe(null)
    setProbeError(null)
    durationRef.current = null
    if (!kind) return
    let cancelled = false
    const timer = setTimeout(async () => {
      setProbing(true)
      try {
        const result = await api.probe(url)
        if (cancelled) return
        setProbe(result)
        durationRef.current = result.duration_s
        if (formState.touchedFields.end) form.trigger("end")
      } catch (e) {
        if (!cancelled) setProbeError((e as Error).message)
      } finally {
        if (!cancelled) setProbing(false)
      }
    }, PROBE_DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, kind])

  const start = parseTime(watch("start") ?? "")
  const end = parseTime(watch("end") ?? "")
  const length = start !== null && end !== null && end > start ? end - start : null

  const onSubmit = async (values: EpisodeValues) => {
    try {
      const job = await api.createJob(
        { url: values.url, start: values.start, end: values.end, meta: detailsToMeta(values.details) },
        probe?.title
      )
      if (artwork) {
        try {
          await api.uploadArtwork(job.id, artwork)
        } catch (e) {
          toast.error(t("form.toast_artwork_failed", { error: (e as Error).message }))
        }
      }
      toast.success(t("form.toast_preparing"))
      const nextEpisode = values.details.episode ? String(Number(values.details.episode) + 1) : ""
      reset({
        url: "",
        start: "",
        end: "",
        details: { ...emptyDetails, season: values.details.season, episode: nextEpisode },
      })
      setArtwork(null)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("form.title")}</CardTitle>
        <CardDescription>
          <Trans i18nKey="form.intro" components={{ req: <span className="text-destructive" /> }} />
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <CardContent className="flex flex-col gap-6">
          <section className="flex flex-col gap-4">
            <SectionTitle step={1}>{t("form.step_source")}</SectionTitle>
            <FieldGroup>
              <Field data-invalid={!!errors.url}>
                <div className="flex items-center justify-between">
                  <FieldLabel htmlFor="url">
                    {t("form.url_label")} <Required />
                  </FieldLabel>
                  {kind && <SourceBadge kind={kind} />}
                </div>
                <Input
                  id="url"
                  type="url"
                  placeholder={t("form.url_placeholder")}
                  aria-invalid={!!errors.url}
                  autoComplete="off"
                  {...register("url")}
                />
                <FieldErrorText error={errors.url} />
                {probing && (
                  <FieldDescription className="flex items-center gap-1.5">
                    <Loader2Icon className="size-3.5 animate-spin" /> {t("form.reading_info")}
                  </FieldDescription>
                )}
                {probeError && (
                  <FieldDescription className="text-amber-600 dark:text-amber-400">{probeError}</FieldDescription>
                )}
              </Field>

              {probe && (
                <div className="flex gap-3 rounded-lg border bg-muted/40 p-3">
                  {probe.thumbnail && (
                    <img src={probe.thumbnail} alt="" className="aspect-video w-28 shrink-0 rounded object-cover" />
                  )}
                  <div className="min-w-0 text-sm">
                    <p className="line-clamp-2 font-medium">{probe.title}</p>
                    <p className="text-muted-foreground">
                      {[probe.uploader, probe.duration_s ? formatTime(probe.duration_s) : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field data-invalid={!!errors.start}>
                  <FieldLabel htmlFor="start">
                    {t("form.start_label")} <Required />
                  </FieldLabel>
                  <Input
                    id="start"
                    placeholder="0:12:30"
                    className="font-mono"
                    aria-invalid={!!errors.start}
                    {...register("start")}
                  />
                  <FieldErrorText error={errors.start} />
                </Field>
                <Field data-invalid={!!errors.end}>
                  <div className="flex items-center justify-between">
                    <FieldLabel htmlFor="end">
                      {t("form.end_label")} <Required />
                    </FieldLabel>
                    {probe?.duration_s && (
                      <Button
                        type="button"
                        variant="link"
                        size="xs"
                        className="h-auto p-0"
                        onClick={() =>
                          setValue("end", formatTime(probe.duration_s!), { shouldValidate: true, shouldTouch: true })
                        }
                      >
                        {t("form.use_video_end")}
                      </Button>
                    )}
                  </div>
                  <Input
                    id="end"
                    placeholder="1:45:00"
                    className="font-mono"
                    aria-invalid={!!errors.end}
                    {...register("end")}
                  />
                  <FieldErrorText error={errors.end} />
                </Field>
              </div>
              <FieldDescription className="flex items-center gap-1.5">
                <ScissorsIcon className="size-3.5" />
                {length !== null
                  ? t("form.length_hint", { length: formatLength(length) })
                  : t("form.time_format_hint")}
              </FieldDescription>
            </FieldGroup>
          </section>

          <Separator />

          <section className="flex flex-col gap-4">
            <SectionTitle step={2}>{t("form.step_details")}</SectionTitle>
            <EpisodeDetailsFields form={form as unknown as UseFormReturn<WithDetails>} idPrefix="new" />
            <ArtworkPicker file={artwork} onChange={setArtwork} />
          </section>
        </CardContent>
        <CardFooter className="mt-6 flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">{t("form.footer_hint")}</p>
          <Button type="submit" size="lg" disabled={formState.isSubmitting}>
            {formState.isSubmitting && <Loader2Icon className="animate-spin" />}
            {t("form.submit")}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
