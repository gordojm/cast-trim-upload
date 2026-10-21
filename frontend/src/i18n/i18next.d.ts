// Types t() keys from en.json, so a misspelled key fails the build.
import "i18next"

import type en from "@/locales/en.json"

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation"
    resources: { translation: typeof en }
  }
}
