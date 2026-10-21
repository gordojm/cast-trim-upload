import { AudioLinesIcon, WifiOffIcon } from "lucide-react"
import { useTranslation } from "react-i18next"

import { HistoryTable } from "@/components/history-table"
import { JobCard } from "@/components/job-card"
import { LanguageSelect } from "@/components/language-select"
import { NewEpisodeForm } from "@/components/new-episode-form"
import { SpotifySessionIndicator } from "@/components/spotify-session"
import { ThemeToggle } from "@/components/theme-toggle"
import { ToolsAlert } from "@/components/tools-alert"
import { useJobs } from "@/hooks/use-jobs"

export default function App() {
  const { t } = useTranslation()
  const { jobs, remove, connected } = useJobs()
  const active = jobs.filter((j) => j.status !== "done" && j.status !== "cancelled")
  const finished = jobs.filter((j) => j.status === "done" || j.status === "cancelled")

  return (
    <div className="min-h-svh bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
          <AudioLinesIcon className="size-5 shrink-0 text-primary" />
          <h1 className="truncate font-heading text-base font-semibold">{t("app.title")}</h1>
          {!connected && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <WifiOffIcon className="size-3.5" /> {t("app.reconnecting")}
            </span>
          )}
          <div className="ml-auto flex items-center gap-1 sm:gap-2">
            <SpotifySessionIndicator />
            <LanguageSelect />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6">
        <ToolsAlert />
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <NewEpisodeForm />
          <section className="flex flex-col gap-4" aria-label={t("app.in_progress_aria")}>
            <h2 className="text-sm font-medium text-muted-foreground">{t("app.in_progress")}</h2>
            {active.length === 0 ? (
              <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                {t("app.in_progress_empty")}
              </div>
            ) : (
              active.map((job) => <JobCard key={job.id} job={job} />)
            )}
          </section>
        </div>
        <HistoryTable jobs={finished} onRemoved={remove} />
      </main>
    </div>
  )
}
