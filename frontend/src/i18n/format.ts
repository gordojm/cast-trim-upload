import i18n from "./index"

// Dates follow the selected language (19/10/2026 in Spanish, 10/19/2026 in English).

export const formatDate = (iso: string) =>
  new Intl.DateTimeFormat(i18n.language, { dateStyle: "short" }).format(new Date(iso))

export const formatDateTime = (iso: string) =>
  new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(new Date(iso))

export const formatClock = (iso: string) =>
  new Intl.DateTimeFormat(i18n.language, { timeStyle: "short" }).format(new Date(iso))
