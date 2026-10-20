import { useTranslation } from "react-i18next"

import { Badge } from "@/components/ui/badge"
import type { JobStatus } from "@/lib/api"
import { cn } from "@/lib/utils"

const TONES: Partial<Record<JobStatus, string>> = {
  ready_for_review: "border-sky-500/40 text-sky-700 dark:text-sky-300",
  login_required: "border-amber-500/50 text-amber-700 dark:text-amber-300",
  done: "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
  failed: "border-destructive/50 text-destructive",
  cancelled: "text-muted-foreground",
}

export function StatusBadge({ status }: { status: JobStatus }) {
  const { t } = useTranslation()
  return (
    <Badge variant="outline" className={cn("whitespace-nowrap", TONES[status])}>
      {t(`status.${status}`)}
    </Badge>
  )
}
