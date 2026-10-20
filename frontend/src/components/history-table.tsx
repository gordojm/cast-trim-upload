import { ExternalLinkIcon, Trash2Icon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"

import { StatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { formatDate } from "@/i18n/format"
import { api, type Job } from "@/lib/api"
import { formatLength } from "@/lib/time"

export function HistoryTable({ jobs, onRemoved }: { jobs: Job[]; onRemoved: (id: string) => void }) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("history.title")}</CardTitle>
        <CardDescription>{t("history.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        {jobs.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t("history.empty")}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("history.date")}</TableHead>
                <TableHead>{t("history.episode")}</TableHead>
                <TableHead className="hidden sm:table-cell">{t("history.length")}</TableHead>
                <TableHead>{t("history.result")}</TableHead>
                <TableHead className="w-0" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <TableRow key={job.id}>
                  <TableCell className="whitespace-nowrap text-muted-foreground">{formatDate(job.updated_at)}</TableCell>
                  <TableCell className="max-w-64">
                    <div className="truncate font-medium">{job.meta.title}</div>
                    <div className="text-xs text-muted-foreground">
                      {[job.meta.season && `S${job.meta.season}`, job.meta.episode && `E${job.meta.episode}`]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </div>
                  </TableCell>
                  <TableCell className="hidden tabular-nums sm:table-cell">
                    {formatLength(job.end_s - job.start_s)}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={job.status} />
                      {job.status === "done" && (
                        <span className="text-xs text-muted-foreground">
                          {t(`history.mode_${job.meta.publish_mode}`)}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      {job.spotify_url && (
                        <Button variant="ghost" size="icon-sm" asChild>
                          <a href={job.spotify_url} target="_blank" rel="noreferrer" aria-label={t("history.open_spotify")}>
                            <ExternalLinkIcon />
                          </a>
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t("history.remove")}
                        onClick={() =>
                          api
                            .deleteHistory(job.id)
                            .then(() => onRemoved(job.id))
                            .catch((e) => toast.error(e.message))
                        }
                      >
                        <Trash2Icon />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
