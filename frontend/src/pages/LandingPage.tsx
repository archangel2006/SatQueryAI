import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  SignedIn,
  SignedOut,
} from '@clerk/clerk-react'
import { useScroll, useTransform } from 'framer-motion'

import { Button } from '../components/Button'
import { BeneficiariesReel } from '../components/landing/BeneficiariesReel'
import { FeatureMissions } from '../components/landing/FeatureMissions'
import { LandingCta } from '../components/landing/LandingCta'
import { LandingHero } from '../components/landing/LandingHero'
import { LanguageVoice } from '../components/landing/LanguageVoice'
import { LitIndiaBackground } from '../components/landing/LitIndiaBackground'
import { TrustStrip } from '../components/landing/TrustStrip'
import { ThemeToggle } from '../components/ThemeToggle'

import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'
import { useTheme } from '../ThemeContext'
import { ROUTES } from '../routes'
import { SignedInHomePage } from './SignedInHomePage'


/* ============================================================
   LANDING NAVIGATION
   ============================================================ */

function LandingNav() {
  const { theme, toggleTheme } = useTheme()

  const isDark = theme === 'dark'

  return (
    <header className="absolute inset-x-0 top-0 z-50">

      {/* Mission-status line */}
      <div
        className="
          relative h-px w-full
          bg-border/50
          dark:bg-white/10
        "
      >
        <div className="absolute left-0 top-0 h-px w-32 bg-accent sm:w-48" />

        <div
          className="
            absolute right-0 top-0 h-px w-24
            bg-border/40
            dark:bg-white/5
          "
        />
      </div>


      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">

        {/* ====================================================
            LOGO
            ==================================================== */}

        <Link
          to={ROUTES.home}
          className="group flex items-center gap-3 no-underline"
        >

          {/* Logo mark */}
          <div
            className="
              relative flex h-9 w-9 items-center justify-center
              rounded-lg
              border border-border
              bg-surface/70
              backdrop-blur-md
              transition-all duration-300
              group-hover:border-accent/50
              group-hover:bg-surface
              dark:border-white/15
              dark:bg-white/[0.035]
              dark:group-hover:bg-white/[0.06]
            "
          >
            <span
              className="
                absolute inset-[5px]
                rounded-md
                border border-border/70
                dark:border-white/10
              "
            />

            <span
              className="
                relative h-2.5 w-2.5 rounded-full
                bg-accent
                shadow-[0_0_16px_rgba(255,190,0,0.45)]
              "
            />
          </div>


          <div>
            <div
              className="
                font-display text-[16px] font-bold tracking-tight
                text-ink
                dark:text-white
              "
            >
              SatQuery AI
            </div>

            <div
              className="
                mt-0.5 hidden font-mono text-[7px]
                uppercase tracking-[0.28em]
                text-muted
                sm:block
                dark:text-white/35
              "
            >
              Earth Observation Intelligence
            </div>
          </div>

        </Link>


        {/* ====================================================
            RIGHT CONTROLS
            ==================================================== */}

        <div className="flex items-center gap-3">

          {/* System status */}
          <div
            className="
              hidden items-center gap-2
              font-mono text-[9px]
              uppercase tracking-[0.18em]
              text-muted
              lg:flex
              dark:text-white/40
            "
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute h-full w-full animate-ping rounded-full bg-emerald-400/40" />
              <span className="relative h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </span>

            System online
          </div>


          <div
            className="
              hidden h-4 w-px
              bg-border
              lg:block
              dark:bg-white/10
            "
          />


          {/* Theme toggle */}
          <ThemeToggle
            theme={theme}
            onToggle={toggleTheme}
          />


          {/* Language */}
          <div
            className="
              hidden items-center
              font-mono text-[10px]
              text-muted
              sm:flex
              dark:text-white/45
            "
            aria-label="Language"
          >
            <span className="font-medium text-ink dark:text-white">
              EN
            </span>

            <span className="mx-2 text-border dark:text-white/20">
              /
            </span>

            <span>
              हिं
            </span>
          </div>


          {/* Sign in */}
          <Link to={ROUTES.signIn}>
            <Button
              variant="secondary"
              className="
                border-border
                bg-surface/60
                text-ink
                backdrop-blur-md
                transition-all duration-300
                hover:border-accent/40
                hover:bg-surface
                dark:border-white/25
                dark:bg-white/[0.025]
                dark:text-white
                dark:hover:border-white/40
                dark:hover:bg-white/[0.08]
              "
            >
              Sign in
            </Button>
          </Link>


          {/* Primary CTA */}
          <Link
            to={ROUTES.signUp}
            className="hidden sm:inline-flex"
          >
            <Button
              variant="primary"
              className="
                bg-accent
                text-navy
                shadow-[0_0_25px_rgba(255,190,0,0.12)]
                transition-all duration-300
                hover:scale-[1.02]
                hover:shadow-[0_0_30px_rgba(255,190,0,0.2)]
                hover:opacity-95
              "
            >
              Start exploring
            </Button>
          </Link>

        </div>
      </div>
    </header>
  )
}


/* ============================================================
   CINEMATIC HERO OVERLAYS
   ============================================================ */

function HeroAtmosphere() {
  return (
    <>
      {/* Main vignette */}
      <div
        className="
          pointer-events-none absolute inset-0 z-[5]
          dark:opacity-100
          opacity-60
        "
        style={{
          background:
            'radial-gradient(circle at 50% 45%, transparent 25%, rgba(5,10,20,0.10) 55%, rgba(5,10,20,0.42) 100%)',
        }}
        aria-hidden="true"
      />


      {/* Dark top gradient — only really visible in dark mode */}
      <div
        className="
          pointer-events-none absolute inset-x-0 top-0 z-[5]
          h-40
          opacity-30
          dark:opacity-100
        "
        style={{
          background:
            'linear-gradient(to bottom, rgba(5,10,20,0.60), transparent)',
        }}
        aria-hidden="true"
      />


      {/* Bottom transition */}
      <div
        className="
          pointer-events-none absolute inset-x-0 bottom-0 z-[6]
          h-32
          bg-gradient-to-b
          from-transparent
          to-bg
        "
        aria-hidden="true"
      />


      {/* Subtle scan texture */}
      <div
        className="
          pointer-events-none absolute inset-0 z-[6]
          opacity-[0.018]
          dark:opacity-[0.025]
        "
        style={{
          backgroundImage:
            'repeating-linear-gradient(to bottom, transparent 0px, transparent 3px, rgba(120,140,160,0.35) 4px)',
        }}
        aria-hidden="true"
      />
    </>
  )
}


/* ============================================================
   TECHNICAL CORNER FRAME
   ============================================================ */

function HeroFrame() {
  return (
    <div
      className="
        pointer-events-none absolute inset-6 z-[8]
        hidden
        border border-border/30
        lg:block
        dark:border-white/[0.055]
      "
      aria-hidden="true"
    >
      <span className="absolute -left-px -top-px h-6 w-6 border-l border-t border-accent/60" />
      <span className="absolute -right-px -top-px h-6 w-6 border-r border-t border-accent/60" />
      <span className="absolute -bottom-px -left-px h-6 w-6 border-b border-l border-accent/60" />
      <span className="absolute -bottom-px -right-px h-6 w-6 border-b border-r border-accent/60" />
    </div>
  )
}


/* ============================================================
   HERO TELEMETRY
   ============================================================ */

function HeroTelemetry() {
  return (
    <>
      {/* Mission label */}
      <div
        className="
          pointer-events-none absolute left-8 top-32 z-10
          hidden font-mono text-[8px]
          uppercase tracking-[0.2em]
          text-muted/50
          lg:block
          dark:text-white/25
        "
      >
        <div>
          MISSION 01
        </div>

        <div className="mt-1 text-muted/30 dark:text-white/15">
          EARTH OBSERVATION
        </div>
      </div>


      {/* Right telemetry */}
      <div
        className="
          pointer-events-none absolute right-8 top-32 z-10
          hidden text-right font-mono text-[8px]
          uppercase tracking-[0.18em]
          text-muted/50
          lg:block
          dark:text-white/25
        "
      >
        <div>
          NODE // SIH-26167
        </div>

        <div className="mt-1 text-muted/30 dark:text-white/15">
          S1 / S2 · MULTISPECTRAL
        </div>
      </div>


      {/* Coordinates */}
      <div
        className="
          pointer-events-none absolute bottom-20 left-8 z-10
          hidden font-mono text-[8px]
          uppercase tracking-[0.18em]
          text-muted/40
          lg:block
          dark:text-white/20
        "
      >
        <div>
          LAT 20.5937° N
        </div>

        <div className="mt-1">
          LON 78.9629° E
        </div>
      </div>


      {/* Engine status */}
      <div
        className="
          pointer-events-none absolute bottom-20 right-8 z-10
          hidden text-right font-mono text-[8px]
          uppercase tracking-[0.18em]
          lg:block
        "
      >
        <div className="text-muted/40 dark:text-white/20">
          VISION ENGINE
        </div>

        <div className="mt-1 text-accent/70">
          READY
        </div>
      </div>
    </>
  )
}


/* ============================================================
   SCROLL INDICATOR
   ============================================================ */

function ScrollIndicator({
  reducedMotion,
}: {
  reducedMotion: boolean
}) {
  return (
    <div className="pointer-events-none absolute bottom-7 left-1/2 z-20 -translate-x-1/2">

      <div className="flex flex-col items-center gap-3">

        <span
          className="
            font-mono text-[8px]
            uppercase tracking-[0.32em]
            text-muted/60
            dark:text-white/30
          "
        >
          Explore
        </span>

        <div
          className="
            relative h-9 w-px overflow-hidden
            bg-border
            dark:bg-white/10
          "
        >
          {!reducedMotion && (
            <div
              className="absolute left-0 top-0 h-1/2 w-px bg-accent"
              style={{
                animation:
                  'satquery-scroll-line 1.8s ease-in-out infinite',
              }}
            />
          )}
        </div>

      </div>
    </div>
  )
}


/* ============================================================
   LANDING PAGE
   ============================================================ */

export function LandingPage() {
  const heroRef = useRef<HTMLElement>(null)

  const reducedMotion = usePrefersReducedMotion()

  const { scrollYProgress } = useScroll({
    target: heroRef,
    offset: ['start start', 'end start'],
  })


  const [progress, setProgress] = useState(
    reducedMotion ? 0.5 : 0,
  )

  const progressMotion = useTransform(
    scrollYProgress,
    [0, 1],
    [0, 1],
  )


  useEffect(() => {
    if (reducedMotion) return

    return progressMotion.on('change', (value) => {
      setProgress(value)
    })
  }, [
    progressMotion,
    reducedMotion,
  ])


  const heroProgress = reducedMotion
    ? 0.5
    : progress


  return (
    <div
      className="
        min-h-screen
        overflow-x-hidden
        bg-bg
        text-ink
      "
      data-testid="landing"
    >

      {/* ======================================================
          NAVIGATION
          ====================================================== */}

      <LandingNav />


      {/* ======================================================
          HERO
          ====================================================== */}

      <section
        ref={heroRef}
        className="relative h-screen"
        aria-label="SatQuery AI introduction"
      >

        <div className="sticky top-0 h-screen overflow-hidden">

          {/* Satellite / India visual */}
          <LitIndiaBackground
            progress={heroProgress}
            reducedMotion={reducedMotion}
          />


          {/* Cinematic atmosphere */}
          <HeroAtmosphere />


          {/* Existing hero content */}
          <LandingHero
            progress={heroProgress}
          />


          {/* Technical frame */}
          <HeroFrame />


          {/* Telemetry */}
          <HeroTelemetry />


          {/* Scroll indicator */}
          <ScrollIndicator
            reducedMotion={reducedMotion}
          />

        </div>
      </section>


      {/* ======================================================
          MAIN PRODUCT EXPERIENCE
          ====================================================== */}

      <div className="relative z-30 bg-bg">

        {/* Soft transition glow */}
        <div
          className="
            pointer-events-none absolute
            left-1/2 top-0
            h-48 w-[70%]
            -translate-x-1/2 -translate-y-1/2
            rounded-full
            bg-accent/[0.035]
            blur-[100px]
            dark:bg-accent/[0.045]
          "
          aria-hidden="true"
        />


        {/* Thin transition line */}
        <div
          className="
            pointer-events-none absolute
            inset-x-0 top-0 h-px
            bg-gradient-to-r
            from-transparent
            via-accent/20
            to-transparent
          "
          aria-hidden="true"
        />


        <div className="relative">

          <FeatureMissions />

          <LanguageVoice />

          <BeneficiariesReel />

          <TrustStrip />

          <LandingCta />

        </div>


        {/* ====================================================
            FOOTER
            ==================================================== */}

        <footer
          className="
            relative overflow-hidden
            border-t border-border
            bg-bg
            px-6 py-12
          "
        >

          {/* Subtle technical grid */}
          <div
            className="pointer-events-none absolute inset-0 opacity-[0.025]"
            style={{
              backgroundImage: `
                linear-gradient(to right, currentColor 1px, transparent 1px),
                linear-gradient(to bottom, currentColor 1px, transparent 1px)
              `,
              backgroundSize: '40px 40px',
            }}
            aria-hidden="true"
          />


          <div className="relative mx-auto max-w-7xl">

            <div className="flex flex-col gap-8 sm:flex-row sm:items-end sm:justify-between">

              {/* Brand */}
              <div>

                <div className="flex items-center gap-3">

                  <div
                    className="
                      flex h-8 w-8 items-center justify-center
                      rounded-md
                      border border-border
                      bg-surface
                    "
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                  </div>

                  <p className="font-display font-bold text-ink">
                    SatQuery AI
                  </p>

                </div>


                <p className="mt-3 max-w-md text-xs leading-6 text-muted">
                  Natural-language intelligence for satellite
                  imagery and Earth observation.
                </p>

              </div>


              {/* Capabilities */}
              <div
                className="
                  grid grid-cols-2 gap-x-10 gap-y-2
                  font-mono text-[9px]
                  uppercase tracking-[0.15em]
                  text-muted
                "
              >
                <span>Earth Observation</span>
                <span>Multimodal AI</span>
                <span>Agentic Analysis</span>
                <span>Evidence Grounded</span>
              </div>

            </div>


            {/* Bottom metadata */}
            <div
              className="
                mt-10 flex flex-col gap-3
                border-t border-border/50
                pt-5
                font-mono text-[8px]
                uppercase tracking-[0.15em]
                text-muted/50
                sm:flex-row sm:items-center sm:justify-between
              "
            >
              <span>
                Department of Space · SIH 26167
              </span>

              <Link
                to={ROUTES.signIn}
                className="
                  text-muted
                  no-underline
                  transition-colors
                  hover:text-ink
                "
              >
                Access console →
              </Link>
            </div>

          </div>
        </footer>

      </div>


      {/* ======================================================
          LOCAL ANIMATION
          ====================================================== */}

      <style>{`
        @keyframes satquery-scroll-line {
          0% {
            transform: translateY(-120%);
            opacity: 0;
          }

          20% {
            opacity: 1;
          }

          70% {
            opacity: 1;
          }

          100% {
            transform: translateY(260%);
            opacity: 0;
          }
        }
      `}</style>

    </div>
  )
}


/* ============================================================
   SIGNED-IN HOME
   ============================================================ */

/**
 * Signed-in hub kept on `/`.
 * Landing is signed-out only.
 */

export {
  SignedInHomePage as SignedInHome,
} from './SignedInHomePage'


/* ============================================================
   HOME GATE
   ============================================================ */

export function HomeGate() {
  return (
    <>
      <SignedOut>
        <LandingPage />
      </SignedOut>

      <SignedIn>
        <SignedInHomePage />
      </SignedIn>
    </>
  )
}