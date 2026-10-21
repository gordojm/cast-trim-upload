import { useTranslation } from "react-i18next"

import { FieldError } from "@/components/ui/field"
import { translateValidation } from "@/i18n/messages"
import { VALIDATION_PARAMS } from "@/lib/schema"

/** FieldError for a react-hook-form error whose message is a validation.* key. */
export function FieldErrorText({ error }: { error?: { message?: string } }) {
  useTranslation() // re-render on language change
  return <FieldError>{translateValidation(error?.message, VALIDATION_PARAMS)}</FieldError>
}
