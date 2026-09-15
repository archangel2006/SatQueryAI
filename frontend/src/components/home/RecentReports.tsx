import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { motion, useReducedMotion } from 'framer-motion'

import {
  downloadReport,
  getSessionReports,
  listSessions,
  type Report,
} from '../../lib/api'

export function RecentReports() {
  const reduce = useReducedMotion()
  const { getToken, isLoaded, isSignedIn } = useAuth()

  const getTokenRef = useRef(getToken)
  getTokenRef.current = getToken

  const [reports, setReports] = useState<Report[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

  const tokenFn = useCallback(async () => {
    return getTokenRef.current()
  }, [])

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return

    let cancelled = false

    ;(async () => {
      setLoading(true)
      setError(null)

      try {
        /*
         * Reports belong to sessions, so first get the user's
         * sessions and then load reports from those sessions.
         */
        const sessions = await listSessions(tokenFn)

        const reportGroups = await Promise.all(
          sessions.slice(0, 8).map(async (session) => {
            try {
              return await getSessionReports(tokenFn, session.id)
            } catch {
              return []
            }
          }),
        )

        if (!cancelled) {
          const allReports = reportGroups
            .flat()
            .sort(
              (a, b) =>
                new Date(b.created_at).getTime() -
                new Date(a.created_at).getTime(),
            )

          setReports(allReports.slice(0, 6))
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Could not load reports',
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [isLoaded, isSignedIn, tokenFn])

  async function handleDownload(report: Report) {
    try {
      setDownloadingId(report.id)

      const blob = await downloadReport(
        tokenFn,
        report.session_id,
        report.id,
      )

      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')

      link.href = url
      link.download = `${report.title || 'satquery-report'}.pdf`
        .replace(/[<>:"/\\|?*]+/g, '-')

      document.body.appendChild(link)
      link.click()
      link.remove()

      URL.revokeObjectURL(url)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not download report',
      )
    } finally {
      setDownloadingId(null)
    }
  }

  return (
    <motion.section
      initial={reduce ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.34 }}
      className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-surface/80 backdrop-blur-sm"
    >
      {/* HEADER */}
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div>
          <h2 className="font-display text-base font-bold text-ink">
            Recent reports
          </h2>

          <p className="mt-0.5 text-xs text-muted">
            One-page briefings for your file note
          </p>
        </div>

        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-navy/8 text-navy dark:bg-accent/15 dark:text-accent">
          <DocIcon />
        </span>
      </div>

      {/* CONTENT */}
      <div className="flex flex-1 flex-col px-5 py-4">

        {loading && (
          <div className="flex flex-1 flex-col items-center justify-center py-10">
            <div className="mb-4 h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent" />

            <p className="text-sm text-muted">
              Loading reports...
            </p>
          </div>
        )}

        {!loading && error && (
          <div className="flex flex-1 flex-col items-center justify-center px-4 py-10 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-bg text-muted">
              <DocIcon large />
            </div>

            <p className="text-sm font-medium text-ink">
              Could not load reports
            </p>

            <p className="mt-1 max-w-xs text-xs leading-relaxed text-muted">
              {error}
            </p>
          </div>
        )}

        {!loading && !error && reports.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center px-4 py-10 text-center">
            <div className="relative mb-5">
              <div
                className="absolute -inset-3 rounded-3xl bg-accent/10 blur-md"
                aria-hidden
              />

              <div className="relative flex h-16 w-16 items-center justify-center rounded-2xl border border-accent/25 bg-bg text-accent shadow-sm">
                <DocIcon large />
              </div>
            </div>

            <p className="max-w-xs text-sm leading-relaxed text-muted">
              Reports will appear here after you export a one-page briefing
              from a chat.
            </p>
          </div>
        )}

        {!loading && !error && reports.length > 0 && (
          <div className="space-y-2">
            {reports.map((report) => (
              <motion.div
                key={report.id}
                initial={reduce ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="group flex items-center gap-3 rounded-xl border border-border/70 bg-bg/50 p-3 transition-colors hover:border-accent/30 hover:bg-bg"
              >
                {/* DOCUMENT ICON */}
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-accent/20 bg-accent/[0.06] text-accent">
                  <DocIcon />
                </div>

                {/* REPORT INFO */}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">
                    {report.title}
                  </p>

                  <p className="mt-0.5 font-mono text-[9px] uppercase tracking-wider text-muted">
                    {formatDate(report.created_at)}
                  </p>
                </div>

                {/* DOWNLOAD */}
                <button
                  type="button"
                  onClick={() => handleDownload(report)}
                  disabled={downloadingId === report.id}
                  className="flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-border bg-surface px-2.5 text-[10px] font-medium text-muted transition-colors hover:border-accent/30 hover:bg-accent/[0.06] hover:text-accent disabled:cursor-wait disabled:opacity-50"
                >
                  {downloadingId === report.id ? (
                    <>
                      <span className="h-3 w-3 animate-spin rounded-full border border-muted border-t-accent" />
                      <span className="hidden sm:inline">
                        Opening
                      </span>
                    </>
                  ) : (
                    <>
                      <DownloadIcon />
                      <span className="hidden sm:inline">
                        PDF
                      </span>
                    </>
                  )}
                </button>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </motion.section>
  )
}

function formatDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return 'Unknown date'
  }

  return date.toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function DocIcon({ large }: { large?: boolean }) {
  const s = large ? 28 : 16

  return (
    <svg
      width={s}
      height={s}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M7 3.5h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5.5 20V5A1.5 1.5 0 0 1 7 3.5Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />

      <path
        d="M14 3.5V8h4.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />

      <path
        d="M8.5 12h7M8.5 15.5h5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M12 3v12"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />

      <path
        d="m7 10 5 5 5-5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      <path
        d="M5 20h14"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}