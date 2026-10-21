import { ImageIcon, XIcon } from "lucide-react"
import { useEffect, useId, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field"
import { translateMessage, type ApiMessage } from "@/i18n/messages"
import { ARTWORK_MIN_PX, validateArtwork } from "@/lib/schema"

interface Props {
  file: File | null
  onChange: (file: File | null) => void
  /** Preview of artwork already stored on the server (edit mode). */
  existingUrl?: string | null
  onRemoveExisting?: () => void
}

export function ArtworkPicker({ file, onChange, existingUrl, onRemoveExisting }: Props) {
  const { t } = useTranslation()
  const id = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<ApiMessage | null>(null)
  const [preview, setPreview] = useState<string | null>(null)

  useEffect(() => {
    if (!file) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const pick = async (f: File | undefined) => {
    if (!f) return
    const problem = await validateArtwork(f)
    setError(problem)
    if (!problem) onChange(f)
    if (inputRef.current) inputRef.current.value = ""
  }

  const shown = preview ?? existingUrl ?? null

  return (
    <Field data-invalid={!!error}>
      <FieldLabel htmlFor={id}>{t("artwork.label")}</FieldLabel>
      <div className="flex items-center gap-4">
        <div className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted">
          {shown ? (
            <img src={shown} alt={t("artwork.preview_alt")} className="size-full object-cover" />
          ) : (
            <ImageIcon className="size-6 text-muted-foreground" />
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => inputRef.current?.click()}>
            {shown ? t("artwork.replace") : t("artwork.choose")}
          </Button>
          {shown && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setError(null)
                if (file) onChange(null)
                else onRemoveExisting?.()
              }}
            >
              <XIcon /> {t("artwork.remove")}
            </Button>
          )}
        </div>
        <input
          ref={inputRef}
          id={id}
          type="file"
          accept="image/jpeg,image/png"
          className="sr-only"
          onChange={(e) => pick(e.target.files?.[0])}
        />
      </div>
      <FieldDescription>{t("artwork.hint", { min: ARTWORK_MIN_PX })}</FieldDescription>
      <FieldError>{error && translateMessage(error)}</FieldError>
    </Field>
  )
}
