import { Link, Navigate } from 'react-router-dom'
import { SignedIn, SignedOut, UserButton } from '@clerk/clerk-react'
import { motion, useReducedMotion } from 'framer-motion'
import { Button } from '../components/Button'
import { Logo } from '../components/Logo'
import { ThemeToggle } from '../components/ThemeToggle'
import { useTheme } from '../ThemeContext'
import { CloudScenePage } from './CloudScenePage'
import { ROUTES } from '../routes'

type JobStubPageProps = {
  title: string
  body: string
}

function JobStubChrome({ title, body }: JobStubPageProps) {
  const { theme, toggleTheme } = useTheme()
  const reduce = useReducedMotion()

  return (
    <div className="relative min-h-screen overflow-hidden bg-bg text-ink">
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="absolute -left-20 top-10 h-72 w-72 rounded-full bg-accent/10 blur-3xl" />
        <div className="absolute -right-10 bottom-20 h-64 w-64 rounded-full bg-navy/5 blur-3xl dark:bg-accent/5" />
      </div>
      <header className="relative z-10 border-b border-border/70 bg-bg/75 backdrop-blur-md">
        <div className="h-0.5 w-full bg-gradient-to-r from-accent to-builtup" aria-hidden />
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <Link to={ROUTES.home} className="no-underline">
            <Logo theme={theme} />
          </Link>
          <div className="flex items-center gap-3">
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            <UserButton afterSignOutUrl={ROUTES.home} />
          </div>
        </div>
      </header>
      <main className="relative z-10 mx-auto flex max-w-lg flex-col items-center px-6 py-24 text-center">
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-accent">
            Coming soon
          </p>
          <h1 className="mt-3 font-display text-3xl font-bold text-ink">{title}</h1>
          <p className="mt-4 text-sm leading-relaxed text-muted">{body}</p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link to={ROUTES.home}>
              <Button variant="secondary">Back to home</Button>
            </Link>
            <Link to={ROUTES.ask}>
              <Button
                variant="primary"
                className="bg-accent text-white hover:opacity-90 dark:text-navy"
              >
                Ask this scene
              </Button>
            </Link>
          </div>
        </motion.div>
      </main>
    </div>
  )
}

export function ChangeJobPage() {
  return (
    <>
      <SignedOut>
        <Navigate to={ROUTES.signIn} replace />
      </SignedOut>
      <SignedIn>
        <JobStubChrome
          title="Before vs after"
          body="Two dates of the same place — what changed, and where. Dual Date slots and a compare slider ship next."
        />
      </SignedIn>
    </>
  )
}

export function CloudJobPage() {
  return <CloudScenePage />
}
