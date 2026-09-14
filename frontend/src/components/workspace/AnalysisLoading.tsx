import { useEffect, useState } from 'react'

const stages = [
  'QUERY RECEIVED',
  'SCENE CLASSIFIED',
  'EXTRACTING VISUAL FEATURES',
  'GENERATING RESPONSE',
]

const telemetry = [
  'INITIALIZING VISION ENGINE',
  'LOCATING SPATIAL FEATURES',
  'ANALYZING IMAGE CONTEXT',
  'MATCHING DETECTED OBJECTS',
  'COMPUTING SCENE RELATIONSHIPS',
  'GROUNDING RESPONSE',
]

export function AnalysisLoading() {
  const [stage, setStage] = useState(0)
  const [telemetryIndex, setTelemetryIndex] = useState(0)

  useEffect(() => {
    const stageTimer = window.setInterval(() => {
      setStage((prev) => Math.min(prev + 1, stages.length - 1))
    }, 1200)

    const telemetryTimer = window.setInterval(() => {
      setTelemetryIndex((prev) => (prev + 1) % telemetry.length)
    }, 850)

    return () => {
      window.clearInterval(stageTimer)
      window.clearInterval(telemetryTimer)
    }
  }, [])

  const progress = Math.min(25 + stage * 22, 91)

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-accent/20 bg-[#060D1A]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inset-0 animate-ping rounded-full bg-accent/50" />
            <span className="relative h-2.5 w-2.5 rounded-full bg-accent" />
          </span>

          <span className="font-mono text-[10px] font-semibold tracking-[0.16em] text-accent">
            SATQUERY VISION ENGINE
          </span>
        </div>

        <span className="font-mono text-[8px] tracking-[0.16em] text-white/30">
          PROCESSING
        </span>
      </div>

      <div className="p-4">
        {/* Radar */}
        <div className="relative mx-auto mb-5 h-32 w-32">
          {/* Outer rings */}
          <div className="absolute inset-0 rounded-full border border-accent/10" />
          <div className="absolute inset-3 rounded-full border border-accent/15" />
          <div className="absolute inset-6 rounded-full border border-accent/20" />

          {/* Crosshair */}
          <div className="absolute left-1/2 top-0 h-full w-px bg-accent/10" />
          <div className="absolute left-0 top-1/2 h-px w-full bg-accent/10" />

          {/* Scanning beam */}
          <div
            className="absolute left-1/2 top-1/2 h-1/2 w-px origin-top bg-gradient-to-b from-accent to-transparent"
            style={{
              animation: 'satquery-radar 2s linear infinite',
            }}
          />

          {/* Target */}
          <div className="absolute left-[53%] top-[34%] h-2 w-2 rounded-full bg-accent shadow-[0_0_12px_rgba(255,190,0,0.8)]">
            <span className="absolute -inset-2 animate-ping rounded-full border border-accent/40" />
          </div>

          {/* Coordinates */}
          <span className="absolute -left-7 top-1/2 -translate-y-1/2 font-mono text-[7px] text-white/20">
            N
          </span>

          <span className="absolute -right-7 top-1/2 -translate-y-1/2 font-mono text-[7px] text-white/20">
            E
          </span>

          <span className="absolute left-1/2 top-1 -translate-x-1/2 font-mono text-[7px] text-white/20">
            AOI
          </span>
        </div>

        {/* Current operation */}
        <div className="mb-4 text-center">
          <div className="font-mono text-[8px] uppercase tracking-[0.2em] text-white/30">
            Current operation
          </div>

          <div
            key={telemetryIndex}
            className="mt-1 font-mono text-[10px] tracking-[0.12em] text-white/80"
            style={{
              animation: 'satquery-fade-up 0.35s ease-out',
            }}
          >
            {telemetry[telemetryIndex]}
          </div>
        </div>

        {/* Pipeline */}
        <div className="space-y-2">
          {stages.map((item, index) => {
            const completed = index < stage
            const active = index === stage

            return (
              <div
                key={item}
                className="flex items-center gap-3"
              >
                <span
                  className={[
                    'flex h-4 w-4 items-center justify-center rounded-full border font-mono text-[7px] transition-all duration-500',
                    completed
                      ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400'
                      : active
                        ? 'border-accent bg-accent/10 text-accent'
                        : 'border-white/10 text-white/20',
                  ].join(' ')}
                >
                  {completed ? '✓' : active ? '◉' : '○'}
                </span>

                <span
                  className={[
                    'font-mono text-[8px] tracking-[0.14em] transition-colors duration-500',
                    completed
                      ? 'text-white/45'
                      : active
                        ? 'text-accent'
                        : 'text-white/20',
                  ].join(' ')}
                >
                  {item}
                </span>

                {active && (
                  <span className="ml-auto font-mono text-[7px] text-accent/60">
                    ACTIVE
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {/* Progress */}
        <div className="mt-5">
          <div className="mb-1.5 flex justify-between font-mono text-[7px] tracking-[0.12em]">
            <span className="text-white/25">
              ANALYSIS DEPTH
            </span>

            <span className="text-accent/70">
              {progress}%
            </span>
          </div>

          <div className="h-px overflow-hidden bg-white/10">
            <div
              className="h-full bg-accent transition-all duration-1000 ease-out"
              style={{
                width: `${progress}%`,
                boxShadow: '0 0 10px rgba(255,190,0,0.6)',
              }}
            />
          </div>
        </div>

        {/* Telemetry footer */}
        <div className="mt-4 flex justify-between border-t border-white/[0.05] pt-3 font-mono text-[7px] uppercase tracking-[0.12em] text-white/20">
          <span>VISION ENGINE // ACTIVE</span>
          <span>AOI LOCKED</span>
        </div>
      </div>

      <style>{`
        @keyframes satquery-radar {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }

        @keyframes satquery-fade-up {
          from {
            opacity: 0;
            transform: translateY(4px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  )
}