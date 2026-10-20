import i18n from "i18next"
import { initReactI18next } from "react-i18next"

import { DEFAULT_LANGUAGE, LANGUAGES } from "./languages"

// Every src/locales/<code>.json is bundled automatically.
const files = import.meta.glob<{ default: Record<string, unknown> }>("../locales/*.json", { eager: true })
const resources = Object.fromEntries(
  Object.entries(files).map(([path, mod]) => [path.match(/([\w-]+)\.json$/)![1], { translation: mod.default }])
)

const STORAGE_KEY = "ctu-lang"
const SUPPORTED: string[] = LANGUAGES.map((l) => l.code)

/** Saved choice, else the first browser language we support (es-AR → es), else English. */
function detectLanguage(): string {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && SUPPORTED.includes(saved)) return saved
  } catch {
    /* storage unavailable */
  }
  const preferred = navigator.languages?.length ? navigator.languages : [navigator.language]
  for (const tag of preferred) {
    const base = tag?.toLowerCase().split("-")[0]
    if (base && SUPPORTED.includes(base)) return base
  }
  return DEFAULT_LANGUAGE
}

i18n.use(initReactI18next).init({
  resources,
  lng: detectLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: SUPPORTED,
  interpolation: { escapeValue: false }, // React already escapes
})

function applyToDocument(lng: string) {
  document.documentElement.lang = lng
  document.title = i18n.t("app.title")
}
applyToDocument(i18n.language)
i18n.on("languageChanged", applyToDocument)

/** Switch language and remember the choice (an explicit pick beats the browser setting). */
export function setLanguage(code: string) {
  try {
    localStorage.setItem(STORAGE_KEY, code)
  } catch {
    /* storage unavailable */
  }
  void i18n.changeLanguage(code)
}

export default i18n
