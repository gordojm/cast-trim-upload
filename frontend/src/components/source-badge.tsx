import { Badge } from "@/components/ui/badge"
import type { SourceKind } from "@/lib/api"

export function SourceBadge({ kind }: { kind: SourceKind }) {
  return kind === "youtube" ? (
    <Badge variant="outline" className="border-red-500/40 text-red-600 dark:text-red-400">
      YouTube
    </Badge>
  ) : (
    <Badge variant="outline" className="border-violet-500/40 text-violet-600 dark:text-violet-400">
      Twitch
    </Badge>
  )
}
