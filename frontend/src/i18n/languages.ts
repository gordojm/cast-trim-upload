// Languages offered in the selector, by native name.
// To add one: create src/locales/<code>.json (copy en.json and translate it) and list it here.
export const LANGUAGES = [
  { code: "en", name: "English" },
  { code: "es", name: "Español" },
] as const satisfies readonly { code: string; name: string }[]

export type LanguageCode = (typeof LANGUAGES)[number]["code"]

export const DEFAULT_LANGUAGE: LanguageCode = "en"
