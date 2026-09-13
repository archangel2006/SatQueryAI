import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { ROUTES } from '../../routes'

type JobCardDef = {
  n: string
  title: string
  short: string
  blurb: string
  to: string
  live?: boolean
  art: 'ask' | 'change' | 'cloud'
}

const JOBS: JobCardDef[] = [
  {
    n: '01',
    title: 'Ask this scene',
    short: 'One image',
    blurb: 'Describe or highlight water, fields, buildings.',
    to: ROUTES.ask,
    live: true,
    art: 'ask',
  },
  {
    n: '02',
    title: 'Before vs after',
    short: 'Two dates',
    blurb: 'What changed, and where?',
    to: ROUTES.change,
    art: 'change',
  },
  {
    n: '03',
    title: 'See through cloud',
    short: 'Optical + radar',
    blurb: 'When colour fails, radar still sees structure.',
    to: ROUTES.cloud,
    art: 'cloud',
  },
]

function JobArt({ kind }: { kind: JobCardDef['art'] }) {
  if (kind === 'ask') {
    return (
      <svg viewBox="0 0 320 180" className="h-full w-full" aria-hidden>
        <defs>
          <linearGradient id="askSky" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#0b1f3a" />
            <stop offset="100%" stopColor="#1e3a5f" />
          </linearGradient>
          <linearGradient id="askGlow" x1="0.5" y1="0" x2="0.5" y2="1">
            <stop offset="0%" stopColor="#e85d04" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#e85d04" stopOpacity="0" />
          </linearGradient>
        </defs>
        <rect width="320" height="180" fill="url(#askSky)" />
        <path d="M0 120 Q80 90 160 115 T320 100 L320 180 L0 180Z" fill="#0d9488" opacity="0.45" />
        <path d="M0 140 Q100 120 200 145 T320 130 L320 180 L0 180Z" fill="#14532d" opacity="0.5" />
        <circle cx="250" cy="48" r="28" fill="url(#askGlow)" />
        <rect x="188" y="58" width="72" height="52" rx="8" fill="#e85d04" opacity="0.85" />
        <rect x="198" y="68" width="28" height="20" rx="3" fill="#fff" opacity="0.9" />
      </svg>
    )
  }
  if (kind === 'change') {
    return (
      <svg viewBox="0 0 320 180" className="h-full w-full" aria-hidden>
        <rect width="160" height="180" fill="#0b1f3a" />
        <rect x="160" width="160" height="180" fill="#1a2744" />
        <path d="M0 110 L80 95 L160 120 L160 180 L0 180Z" fill="#334155" />
        <path d="M160 100 L220 70 L320 110 L320 180 L160 180Z" fill="#dc2626" opacity="0.55" />
        <path d="M160 100 L220 70 L280 95 L320 90" fill="none" stroke="#e85d04" strokeWidth="3" />
        <line x1="160" y1="20" x2="160" y2="160" stroke="#f8fafc" strokeWidth="2" strokeDasharray="4 6" opacity="0.7" />
        <circle cx="160" cy="100" r="7" fill="#e85d04" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 320 180" className="h-full w-full" aria-hidden>
      <defs>
        <linearGradient id="cloudFog" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#94a3b8" />
          <stop offset="100%" stopColor="#0b1f3a" />
        </linearGradient>
      </defs>
      <rect width="160" height="180" fill="url(#cloudFog)" />
      <ellipse cx="60" cy="50" rx="50" ry="22" fill="#fff" opacity="0.55" />
      <ellipse cx="110" cy="62" rx="40" ry="18" fill="#fff" opacity="0.4" />
      <rect x="160" width="160" height="180" fill="#0b1f3a" />
      <g opacity="0.7" stroke="#94a3b8" strokeWidth="1">
        {Array.from({ length: 12 }).map((_, i) => (
          <line key={i} x1="170" y1={30 + i * 12} x2="310" y2={40 + i * 11} />
        ))}
      </g>
      <rect x="200" y="70" width="50" height="60" fill="#e85d04" opacity="0.75" />
      <path d="M170 150 Q240 120 310 145" fill="none" stroke="#2dd4bf" strokeWidth="4" />
    </svg>
  )
}

export function JobCards() {
  const reduce = useReducedMotion()

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      {JOBS.map((job, index) => (
        <motion.div
          key={job.to}
          initial={reduce ? false : { opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.08 + index * 0.07, ease: [0.22, 1, 0.36, 1] }}
        >
          <Link
            to={job.to}
            className={`group relative flex h-full flex-col overflow-hidden rounded-2xl border no-underline transition-shadow duration-300 hover:-translate-y-0.5 hover:shadow-[0_20px_40px_-24px_rgba(232,93,4,0.55)] ${
              job.live
                ? 'border-accent/40 bg-surface ring-1 ring-accent/20'
                : 'border-border bg-surface hover:border-accent/30'
            }`}
          >
            <div className="relative aspect-[16/9] overflow-hidden bg-navy">
              <div className="absolute inset-0 transition-transform duration-500 group-hover:scale-[1.04]">
                <JobArt kind={job.art} />
              </div>
              <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-surface to-transparent" />
              {!job.live ? (
                <span className="absolute right-3 top-3 rounded-full bg-bg/90 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted backdrop-blur">
                  Open
                </span>
              ) : (
                <span className="absolute right-3 top-3 rounded-full bg-accent px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-white">
                  Open
                </span>
              )}
            </div>
            <div className="flex flex-1 flex-col p-5 pt-3">
              <div className="flex items-baseline gap-2">
                <span className="font-display text-xs font-semibold tracking-widest text-accent">
                  {job.n}
                </span>
                <span className="text-[11px] text-muted">{job.short}</span>
              </div>
              <h2 className="mt-1 font-display text-xl font-bold text-ink transition-colors group-hover:text-accent">
                {job.title}
              </h2>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">
                {job.blurb}
              </p>
              <span
                className={`mt-4 inline-flex items-center gap-1 text-sm font-semibold ${
                  job.live ? 'text-accent' : 'text-muted'
                }`}
              >
                {job.live ? 'Start' : 'Preview'}
                <span className="transition-transform group-hover:translate-x-0.5">→</span>
              </span>
            </div>
          </Link>
        </motion.div>
      ))}
    </div>
  )
}
