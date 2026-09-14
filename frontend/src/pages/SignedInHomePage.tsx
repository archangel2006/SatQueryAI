// import { useCallback, useEffect, useRef, useState } from 'react'
// import { Link } from 'react-router-dom'
// import { useAuth, useUser, UserButton } from '@clerk/clerk-react'
// import { motion, useReducedMotion } from 'framer-motion'
// import { Logo } from '../components/Logo'
// import { ThemeToggle } from '../components/ThemeToggle'
// import { JobCards } from '../components/home/JobCards'
// import { RecentChats } from '../components/home/RecentChats'
// import { RecentReports } from '../components/home/RecentReports'
// import { listSessions, type SessionListItem } from '../lib/api'
// import { useTheme } from '../ThemeContext'
// import { ROUTES } from '../routes'

// export function SignedInHomePage() {
//   const { theme, toggleTheme } = useTheme()
//   const { user } = useUser()
//   const { getToken, isLoaded, isSignedIn } = useAuth()
//   const getTokenRef = useRef(getToken)
//   getTokenRef.current = getToken
//   const reduce = useReducedMotion()

//   const [sessions, setSessions] = useState<SessionListItem[]>([])
//   const [loading, setLoading] = useState(true)
//   const [error, setError] = useState<string | null>(null)

//   const tokenFn = useCallback(async () => getTokenRef.current(), [])

//   useEffect(() => {
//     if (!isLoaded || !isSignedIn) return
//     let cancelled = false
//       ; (async () => {
//         setLoading(true)
//         setError(null)
//         try {
//           const rows = await listSessions(tokenFn)
//           if (!cancelled) setSessions(rows.slice(0, 8))
//         } catch (err) {
//           if (!cancelled) {
//             setError(err instanceof Error ? err.message : 'Could not load chats')
//           }
//         } finally {
//           if (!cancelled) setLoading(false)
//         }
//       })()
//     return () => {
//       cancelled = true
//     }
//   }, [isLoaded, isSignedIn, tokenFn])

//   const firstName = user?.firstName

//   return (
//     <div className="relative min-h-screen overflow-x-hidden bg-bg text-ink">
//       {/* Soft atmosphere — not a flat white slab */}
//       <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
//         <div className="absolute -left-24 top-0 h-[28rem] w-[28rem] rounded-full bg-accent/[0.09] blur-3xl" />
//         <div className="absolute -right-16 top-40 h-[22rem] w-[22rem] rounded-full bg-navy/[0.06] blur-3xl dark:bg-accent/[0.06]" />
//         <div className="absolute bottom-0 left-1/3 h-64 w-64 rounded-full bg-water/[0.06] blur-3xl" />
//         <div
//           className="absolute inset-0 opacity-[0.35] dark:opacity-[0.2]"
//           style={{
//             backgroundImage:
//               'radial-gradient(circle at 1px 1px, color-mix(in oklab, var(--sq-ink) 8%, transparent) 1px, transparent 0)',
//             backgroundSize: '24px 24px',
//           }}
//         />
//       </div>

     

//       <header className="sticky top-0 z-30 border-b border-border/70 bg-bg/75 backdrop-blur-md">
//         <div className="h-0.5 w-full bg-gradient-to-r from-accent via-accent to-builtup" aria-hidden />
//         <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
//           <Link to={ROUTES.home} className="no-underline">
//             <Logo theme={theme} />
//           </Link>
//           <div className="flex items-center gap-3">
//             <ThemeToggle theme={theme} onToggle={toggleTheme} />
//             <UserButton afterSignOutUrl={ROUTES.home} />
//           </div>
//         </div>
//       </header>

//       <main className="relative mx-auto max-w-6xl px-6 pb-20 pt-10 sm:pt-14">
//         <motion.div
//           initial={reduce ? false : { opacity: 0, y: 18 }}
//           animate={{ opacity: 1, y: 0 }}
//           transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
//           className="max-w-2xl"
//         >
//           {firstName ? (
//             <p className="text-sm font-medium text-accent">
//               Welcome back, {firstName}
//             </p>
//           ) : (
//             <p className="text-sm font-medium text-accent">Job console</p>
//           )}
//           <h1 className="mt-2 font-display text-4xl font-bold tracking-tight text-ink sm:text-5xl">
//             What do you need{' '}
//             <span className="bg-gradient-to-r from-accent to-builtup bg-clip-text text-transparent">
//               to know?
//             </span>
//           </h1>
//           <p className="mt-4 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
//             Pick a job. Upload the matching pictures. Type a question. We choose
//             the models — you stay with the map.
//           </p>
//         </motion.div>

//         <div className="mt-12">
//           <JobCards />
//         </div>

//         <div className="mt-12 grid min-h-[280px] gap-5 lg:grid-cols-2">
//           <RecentChats sessions={sessions} loading={loading} error={error} />
//           <RecentReports />
//         </div>

//         <motion.p
//           initial={reduce ? false : { opacity: 0 }}
//           animate={{ opacity: 1 }}
//           transition={{ delay: 0.45 }}
//           className="mt-16 text-center text-xs text-muted"
//         >
//           <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/80 px-4 py-2 backdrop-blur">
//             <span className="h-1.5 w-1.5 rounded-full bg-accent" />
//             GeoTIFF preferred · Generic photo-chatbots are not used on pixels
//           </span>
//         </motion.p>
//       </main>
//     </div>
//   )
// }










import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth, useUser, UserButton } from '@clerk/clerk-react'
import { motion, useReducedMotion } from 'framer-motion'

import { Logo } from '../components/Logo'
import { ThemeToggle } from '../components/ThemeToggle'
import { JobCards } from '../components/home/JobCards'
import { RecentChats } from '../components/home/RecentChats'
import { RecentReports } from '../components/home/RecentReports'
import { listSessions, type SessionListItem } from '../lib/api'
import { useTheme } from '../ThemeContext'
import { ROUTES } from '../routes'

export function SignedInHomePage() {
  const { theme, toggleTheme } = useTheme()
  const { user } = useUser()
  const { getToken, isLoaded, isSignedIn } = useAuth()

  const getTokenRef = useRef(getToken)
  getTokenRef.current = getToken

  const reduce = useReducedMotion()

  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const tokenFn = useCallback(async () => getTokenRef.current(), [])

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return

    let cancelled = false

    ;(async () => {
      setLoading(true)
      setError(null)

      try {
        const rows = await listSessions(tokenFn)

        if (!cancelled) {
          setSessions(rows.slice(0, 8))
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'Could not load chats',
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

  const firstName = user?.firstName

  return (
    <div className="relative min-h-screen overflow-hidden bg-bg text-ink selection:bg-accent/20">

      {/* =========================================================
          BACKGROUND SYSTEM
      ========================================================= */}

      <div
        className="pointer-events-none fixed inset-0 z-0 opacity-[0.035]"
        aria-hidden="true"
      >
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: `
              linear-gradient(to right, currentColor 1px, transparent 1px),
              linear-gradient(to bottom, currentColor 1px, transparent 1px)
            `,
            backgroundSize: '48px 48px',
          }}
        />
      </div>

      <div
        className="pointer-events-none fixed inset-0 z-0"
        aria-hidden="true"
      >
        <div className="absolute left-1/2 top-[15%] h-[500px] w-[700px] -translate-x-1/2 rounded-full bg-accent/[0.035] blur-[120px]" />
        <div className="absolute -right-40 top-[40%] h-[400px] w-[400px] rounded-full bg-accent/[0.025] blur-[100px]" />
      </div>

      {/* =========================================================
          CORNER FRAME
      ========================================================= */}

      <div
        className="pointer-events-none fixed inset-0 z-50 p-4"
        aria-hidden="true"
      >
        <div className="flex justify-between">
          <span className="h-3 w-3 border-l border-t border-border/70" />
          <span className="h-3 w-3 border-r border-t border-border/70" />
        </div>

        <div className="absolute bottom-4 left-4 right-4 flex justify-between">
          <span className="h-3 w-3 border-b border-l border-border/70" />
          <span className="h-3 w-3 border-b border-r border-border/70" />
        </div>
      </div>

      {/* =========================================================
          TELEMETRY BAR
      ========================================================= */}

      <div className="relative z-40 border-b border-border/40 bg-surface/40 px-6 py-2 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between">

          <div className="flex items-center gap-4 font-mono text-[10px] tracking-wider">

            <div className="flex items-center gap-2 text-ink">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
              </span>

              <span className="font-semibold">
                SATQUERY
              </span>

              <span className="text-muted">
                // AGENTIC INTELLIGENCE
              </span>
            </div>

            <span className="hidden text-border md:block">|</span>

            <span className="hidden text-muted md:block">
              ORBIT: CO-REGISTERED
            </span>

            <span className="hidden text-muted lg:block">
              S1 / S2
            </span>
          </div>

          <div className="flex items-center gap-4 font-mono text-[9px] tracking-[0.18em] text-muted">
            <span className="hidden sm:block">
              LINK STABLE
            </span>

            <span className="text-accent">
              NODE: SIH-26167
            </span>
          </div>

        </div>
      </div>

      {/* =========================================================
          NAVIGATION
      ========================================================= */}

      <header className="sticky top-0 z-40 border-b border-border/50 bg-bg/75 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3.5">

          <Link
            to={ROUTES.home}
            className="group no-underline"
          >
            <div className="transition-transform duration-300 group-hover:scale-[1.02]">
              <Logo theme={theme} />
            </div>
          </Link>

          <div className="flex items-center gap-3">

            <div className="hidden items-center gap-2 rounded-full border border-border/70 bg-surface/50 px-3 py-1.5 font-mono text-[10px] backdrop-blur md:flex">

              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                <span className="relative h-1.5 w-1.5 rounded-full bg-emerald-400" />
              </span>

              <span className="text-muted">
                OPERATOR
              </span>

              <span className="text-ink">
                {firstName || 'AUTHENTICATED'}
              </span>

            </div>

            <ThemeToggle
              theme={theme}
              onToggle={toggleTheme}
            />

            <UserButton
              afterSignOutUrl={ROUTES.home}
            />
          </div>
        </div>
      </header>

      {/* =========================================================
          MAIN
      ========================================================= */}

      <main className="relative z-10 mx-auto max-w-7xl px-6 pb-24 pt-8">

        {/* =======================================================
            HERO / MISSION CONTROL
        ======================================================= */}

        <motion.section
          initial={reduce ? false : { opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.5,
            ease: [0.16, 1, 0.3, 1],
          }}
          className="group relative overflow-hidden rounded-2xl border border-border/70 bg-surface/50 shadow-[0_20px_80px_rgba(0,0,0,0.08)] backdrop-blur-xl"
        >

          {/* atmospheric glow */}
          <div className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-accent/[0.07] blur-3xl transition-opacity duration-700 group-hover:bg-accent/[0.1]" />

          {/* orbital rings */}
          <div
            className="pointer-events-none absolute right-[-80px] top-1/2 hidden h-[420px] w-[420px] -translate-y-1/2 rounded-full border border-border/20 lg:block"
            aria-hidden="true"
          >
            <div className="absolute inset-8 rounded-full border border-border/15" />
            <div className="absolute inset-20 rounded-full border border-border/10" />

            <motion.div
              animate={
                reduce
                  ? undefined
                  : { rotate: 360 }
              }
              transition={{
                duration: 30,
                repeat: Infinity,
                ease: 'linear',
              }}
              className="absolute inset-0"
            >
              <span className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 rounded-full bg-accent shadow-[0_0_16px_currentColor]" />
            </motion.div>

            <motion.div
              animate={
                reduce
                  ? undefined
                  : { rotate: -360 }
              }
              transition={{
                duration: 45,
                repeat: Infinity,
                ease: 'linear',
              }}
              className="absolute inset-8"
            >
              <span className="absolute bottom-8 right-4 h-1.5 w-1.5 rounded-full bg-accent/70" />
            </motion.div>
          </div>

          {/* technical coordinates */}
          <div className="pointer-events-none absolute right-6 top-5 hidden font-mono text-[8px] uppercase tracking-[0.2em] text-muted/50 lg:block">
            28.6139° N
            <br />
            77.2090° E
          </div>

          <div className="relative p-8 sm:p-10 lg:p-12">

            <div className="max-w-3xl">

              <div className="flex items-center gap-3">

                <div className="inline-flex items-center gap-2 rounded-md border border-accent/20 bg-accent/[0.07] px-2.5 py-1 font-mono text-[10px] font-medium tracking-wider text-accent">
                  <span className="h-1 w-1 rounded-full bg-accent" />
                  WORKSPACE CONSOLE
                </div>

                <span className="font-mono text-[9px] tracking-widest text-muted/60">
                  v2.4.1
                </span>

              </div>

              <h1 className="mt-5 max-w-2xl font-display text-4xl font-bold leading-[1.05] tracking-tight text-ink sm:text-5xl lg:text-[3.6rem]">
                Ask questions.
                <br />
                <span className="text-accent">
                  Understand Earth.
                </span>
              </h1>

              <p className="mt-5 max-w-2xl text-sm leading-7 text-muted sm:text-base">
                Explore satellite imagery and temporal datasets through
                natural-language queries, specialist vision agents, and
                evidence-grounded analysis.
              </p>

              {/* STATUS STRIP */}

              <div className="mt-8 flex flex-wrap gap-2">

                <StatusPill
                  label="SATELLITE LINK"
                  value="ACTIVE"
                />

                <StatusPill
                  label="VISION MODEL"
                  value="READY"
                />

                <StatusPill
                  label="AGENT ROUTER"
                  value="ONLINE"
                />

                <StatusPill
                  label="IMAGERY"
                  value="MULTISPECTRAL"
                />

              </div>

            </div>

            {/* metrics */}

            <div className="mt-10 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border/50 bg-border/30 sm:grid-cols-4">

              <Metric
                label="Pipeline"
                value="Agentic Router"
              />

              <Metric
                label="Imagery"
                value="GeoTIFF"
              />

              <Metric
                label="Bands"
                value="Dual / Multi"
              />

              <Metric
                label="Inference"
                value="Grounded"
              />

            </div>

          </div>
        </motion.section>

        {/* =======================================================
            PIPELINES
        ======================================================= */}

        <section className="mt-12">

          <div className="mb-5 flex items-end justify-between">

            <div>
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
                <span className="h-px w-5 bg-accent" />
                Mission Modules
              </div>

              <h2 className="mt-2 font-display text-xl font-semibold tracking-tight text-ink">
                Analysis Pipelines
              </h2>
            </div>

            <span className="hidden font-mono text-[9px] uppercase tracking-widest text-muted sm:block">
              Select operation →
            </span>

          </div>

          <JobCards />

        </section>

        {/* =======================================================
            ACTIVITY
        ======================================================= */}

        <section className="mt-12">

          <div className="mb-5 flex items-center justify-between">

            <div>
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-accent">
                <span className="h-px w-5 bg-accent" />
                Mission History
              </div>

              <h2 className="mt-2 font-display text-xl font-semibold tracking-tight text-ink">
                Recent Activity
              </h2>
            </div>

            <div className="hidden items-center gap-2 font-mono text-[9px] text-muted sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              LIVE DATA
            </div>

          </div>

          <div className="grid min-h-[280px] gap-6 lg:grid-cols-2">

            <RecentChats
              sessions={sessions}
              loading={loading}
              error={error}
            />

            <RecentReports />

          </div>

        </section>

        {/* =======================================================
            FOOTER
        ======================================================= */}

        <motion.div
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="mt-20"
        >

          <div className="mx-auto flex max-w-3xl items-center gap-4">

            <div className="h-px flex-1 bg-border/50" />

            <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.18em] text-muted">

              <span className="h-1 w-1 rounded-full bg-accent" />

              <span>
                Department of Space
              </span>

              <span className="text-border">
                //
              </span>

              <span>
                Specialist ML Infrastructure
              </span>

            </div>

            <div className="h-px flex-1 bg-border/50" />

          </div>

          <div className="mt-4 text-center font-mono text-[8px] tracking-[0.25em] text-muted/50">
            EARTH OBSERVATION · MULTIMODAL INTELLIGENCE · EVIDENCE GROUNDED
          </div>

        </motion.div>

      </main>
    </div>
  )
}

/* ===============================================================
   SMALL UI COMPONENTS
   =============================================================== */

function StatusPill({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-border/50 bg-bg/30 px-2.5 py-1.5 font-mono text-[9px]">
      <span className="h-1 w-1 rounded-full bg-emerald-400" />

      <span className="text-muted">
        {label}
      </span>

      <span className="font-semibold text-ink">
        {value}
      </span>
    </div>
  )
}

function Metric({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="bg-surface/70 px-4 py-3.5">
      <div className="font-mono text-[8px] uppercase tracking-[0.18em] text-muted">
        {label}
      </div>

      <div className="mt-1 font-mono text-[11px] font-semibold text-ink">
        {value}
      </div>
    </div>
  )
}