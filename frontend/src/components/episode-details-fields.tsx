import { Controller, type UseFormReturn } from "react-hook-form"
import { useTranslation } from "react-i18next"

import { FieldErrorText } from "@/components/field-error-text"
import { Field, FieldDescription, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { DESCRIPTION_MAX, TITLE_MAX, type DetailsValues } from "@/lib/schema"
import { cn } from "@/lib/utils"

export type WithDetails = { details: DetailsValues }

function Counter({ value, max }: { value: string; max: number }) {
  const n = value?.length ?? 0
  return (
    <span className={cn("ml-auto text-xs tabular-nums text-muted-foreground", n > max && "text-destructive")}>
      {n}/{max}
    </span>
  )
}

function Required() {
  return (
    <span aria-hidden className="text-destructive">
      *
    </span>
  )
}

/** Episode details shared by the "new episode" and "edit details" forms. */
export function EpisodeDetailsFields({ form, idPrefix }: { form: UseFormReturn<WithDetails>; idPrefix: string }) {
  const { t } = useTranslation()
  const { register, control, watch, formState } = form
  const errors = formState.errors.details
  const id = (name: string) => `${idPrefix}-${name}`
  const publishMode = watch("details.publish_mode")

  return (
    <FieldGroup>
      <Field data-invalid={!!errors?.title}>
        <div className="flex items-baseline">
          <FieldLabel htmlFor={id("title")}>
            {t("details.title_label")} <Required />
          </FieldLabel>
          <Counter value={watch("details.title")} max={TITLE_MAX} />
        </div>
        <Input id={id("title")} aria-invalid={!!errors?.title} {...register("details.title")} />
        <FieldErrorText error={errors?.title} />
      </Field>

      <Field data-invalid={!!errors?.description}>
        <div className="flex items-baseline">
          <FieldLabel htmlFor={id("description")}>
            {t("details.description_label")} <Required />
          </FieldLabel>
          <Counter value={watch("details.description")} max={DESCRIPTION_MAX} />
        </div>
        <Textarea
          id={id("description")}
          rows={6}
          aria-invalid={!!errors?.description}
          {...register("details.description")}
        />
        <FieldErrorText error={errors?.description} />
      </Field>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field data-invalid={!!errors?.season}>
          <FieldLabel htmlFor={id("season")}>{t("details.season")}</FieldLabel>
          <Input id={id("season")} inputMode="numeric" placeholder="—" {...register("details.season")} />
          <FieldErrorText error={errors?.season} />
        </Field>
        <Field data-invalid={!!errors?.episode}>
          <FieldLabel htmlFor={id("episode")}>{t("details.episode")}</FieldLabel>
          <Input id={id("episode")} inputMode="numeric" placeholder="—" {...register("details.episode")} />
          <FieldErrorText error={errors?.episode} />
        </Field>
        <Field className="col-span-2 sm:col-span-1">
          <FieldLabel htmlFor={id("type")}>{t("details.episode_type")}</FieldLabel>
          <Controller
            control={control}
            name="details.episode_type"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={id("type")} className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="full">{t("details.type_full")}</SelectItem>
                  <SelectItem value="trailer">{t("details.type_trailer")}</SelectItem>
                  <SelectItem value="bonus">{t("details.type_bonus")}</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </Field>
      </div>

      <FieldSet data-invalid={!!errors?.explicit}>
        <FieldLegend variant="label">
          {t("details.explicit_legend")} <Required />
        </FieldLegend>
        <Controller
          control={control}
          name="details.explicit"
          render={({ field }) => (
            <RadioGroup
              value={field.value ?? ""}
              onValueChange={field.onChange}
              className="flex gap-6"
              aria-invalid={!!errors?.explicit}
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="no" id={id("explicit-no")} />
                <Label htmlFor={id("explicit-no")}>{t("details.explicit_no")}</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="yes" id={id("explicit-yes")} />
                <Label htmlFor={id("explicit-yes")}>{t("details.explicit_yes")}</Label>
              </div>
            </RadioGroup>
          )}
        />
        <FieldErrorText error={errors?.explicit} />
      </FieldSet>

      <Field orientation="horizontal">
        <Controller
          control={control}
          name="details.sponsored"
          render={({ field }) => (
            <Switch id={id("sponsored")} checked={field.value} onCheckedChange={field.onChange} />
          )}
        />
        <FieldLabel htmlFor={id("sponsored")} className="font-normal">
          {t("details.sponsored")}
        </FieldLabel>
      </Field>

      <FieldSet>
        <FieldLegend variant="label">{t("details.publish_legend")}</FieldLegend>
        <Controller
          control={control}
          name="details.publish_mode"
          render={({ field }) => (
            <RadioGroup value={field.value} onValueChange={field.onChange} className="flex flex-wrap gap-6">
              {(["draft", "now", "schedule"] as const).map((value) => (
                <div key={value} className="flex items-center gap-2">
                  <RadioGroupItem value={value} id={id(`mode-${value}`)} />
                  <Label htmlFor={id(`mode-${value}`)}>{t(`details.mode_${value}`)}</Label>
                </div>
              ))}
            </RadioGroup>
          )}
        />
        {publishMode === "schedule" && (
          <Field data-invalid={!!errors?.publish_at} className="max-w-xs">
            <FieldLabel htmlFor={id("publish-at")}>
              {t("details.publish_on")} <Required />
            </FieldLabel>
            <Input
              id={id("publish-at")}
              type="datetime-local"
              aria-invalid={!!errors?.publish_at}
              {...register("details.publish_at")}
            />
            <FieldDescription>{t("details.local_time")}</FieldDescription>
            <FieldErrorText error={errors?.publish_at} />
          </Field>
        )}
      </FieldSet>
    </FieldGroup>
  )
}
