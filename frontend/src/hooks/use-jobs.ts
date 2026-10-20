import { useCallback, useEffect, useState } from "react"

import { api, type Job } from "@/lib/api"

/** All jobs (active + history), kept live through the /api/events stream. */
export function useJobs() {
  const [jobs, setJobs] = useState<Record<string, Job>>({})
  const [connected, setConnected] = useState(false)

  const upsert = useCallback((job: Job) => {
    setJobs((prev) => {
      const existing = prev[job.id]
      if (existing && existing.updated_at > job.updated_at) return prev
      return { ...prev, [job.id]: job }
    })
  }, [])

  const remove = useCallback((id: string) => {
    setJobs((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }, [])

  const reload = useCallback(async () => {
    const list = await api.jobs()
    setJobs(Object.fromEntries(list.map((j) => [j.id, j])))
  }, [])

  useEffect(() => {
    const source = new EventSource("/api/events")
    source.onopen = () => {
      setConnected(true)
      // Catch up on anything missed while disconnected.
      reload().catch(() => {})
    }
    source.onerror = () => setConnected(false)
    source.onmessage = (e) => {
      const event = JSON.parse(e.data)
      if (event.type === "job") upsert(event.job as Job)
    }
    return () => source.close()
  }, [reload, upsert])

  const sorted = Object.values(jobs).sort((a, b) => b.created_at.localeCompare(a.created_at))
  return { jobs: sorted, upsert, remove, reload, connected }
}
