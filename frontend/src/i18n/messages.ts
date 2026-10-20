import { useTranslation } from "react-i18next"

import i18n from "./index"

/** A message from the backend: a locale key plus its parameters. */
export interface ApiMessage {
  key: string
  params?: Record<string, string | number | null>
}

/** Keys come from the backend or from zod at runtime, so they aren't statically typed. */
type DynamicT = (key: string, params?: Record<string, unknown>) => string

const dynamicT = (): DynamicT => i18n.t as unknown as DynamicT

/**
 * Translate a backend message. Params named `*_key` hold another key and are translated
 * first; `detail` and `text` carry raw tool output and are shown as-is. Unknown keys fall
 * back to the raw text, so nothing renders blank.
 */
export function translateMessage(m: ApiMessage | string): string {
  // A plain string comes from a backend older than message keys; show it as-is.
  if (typeof m === "string") return m
  const t = dynamicT()
  const params = Object.fromEntries(
    Object.entries(m.params ?? {}).map(([k, v]) => [
      k,
      k.endsWith("_key") && typeof v === "string" && i18n.exists(v) ? t(v) : (v ?? ""),
    ])
  )
  if (!i18n.exists(m.key)) return String(m.params?.text ?? m.params?.detail ?? m.key)
  return t(m.key, params)
}

export function isApiMessage(value: unknown): value is ApiMessage {
  return typeof value === "object" && value !== null && typeof (value as ApiMessage).key === "string"
}

/** Hook form of translateMessage; re-renders when the language changes. */
export function useMessageText() {
  useTranslation()
  return (m: ApiMessage | string | null | undefined) => (m ? translateMessage(m) : "")
}

/** Translate a validation message (a key from lib/schema.ts) with the shared limits. */
export function translateValidation(message: string | undefined, params: Record<string, unknown> = {}) {
  if (!message) return undefined
  if (!i18n.exists(message)) return message
  return dynamicT()(message, params)
}
