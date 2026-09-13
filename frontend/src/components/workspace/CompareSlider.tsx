import { useCallback, useEffect, useRef, useState } from 'react'
import {
  clampComparePercent,
  percentFromPointer,
} from './compareSliderMath'

type CompareSliderProps = {
  beforeUrl: string
  afterUrl: string
  beforeLabel?: string
  afterLabel?: string
  legendLabel?: string
  zoom?: number
  initialPercent?: number
}

export function CompareSlider({
  beforeUrl,
  afterUrl,
  beforeLabel = 'Before',
  afterLabel = 'After',
  legendLabel,
  zoom = 1,
  initialPercent = 50,
}: CompareSliderProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const [percent, setPercent] = useState(() =>
    clampComparePercent(initialPercent),
  )
  const [rootWidth, setRootWidth] = useState(0)

  useEffect(() => {
    const el = rootRef.current
    if (!el) return
    const update = () => setRootWidth(el.clientWidth)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const moveTo = useCallback((clientX: number) => {
    const el = rootRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setPercent(percentFromPointer(clientX, rect.left, rect.width))
  }, [])

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      if (!dragging.current) return
      moveTo(event.clientX)
    }
    const onUp = () => {
      dragging.current = false
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
  }, [moveTo])

  return (
    <div
      ref={rootRef}
      className="relative mx-auto h-full w-full max-w-full touch-none select-none overflow-hidden rounded-md bg-[#0a1220]/40"
      style={{ transform: `scale(${zoom})`, transformOrigin: 'center center' }}
      role="slider"
      aria-label="Before and after comparison"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percent)}
      aria-valuetext={`${Math.round(percent)}% before`}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'ArrowLeft') {
          event.preventDefault()
          setPercent((p) => clampComparePercent(p - 2))
        }
        if (event.key === 'ArrowRight') {
          event.preventDefault()
          setPercent((p) => clampComparePercent(p + 2))
        }
      }}
    >
      {/* After = full frame (right side of wipe) */}
      <img
        src={afterUrl}
        alt=""
        draggable={false}
        className="absolute inset-0 h-full w-full object-contain object-[100%_center]"
      />

      {/* Before = clipped from the left */}
      <div
        className="absolute inset-y-0 left-0 overflow-hidden"
        style={{ width: `${percent}%` }}
      >
        <img
          src={beforeUrl}
          alt=""
          draggable={false}
          className="absolute left-0 top-0 h-full max-w-none object-contain object-left"
          style={{ width: rootWidth || '100%' }}
        />
      </div>

      <span className="pointer-events-none absolute left-3 top-3 rounded bg-navy/80 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-white uppercase">
        {beforeLabel}
      </span>
      <span className="pointer-events-none absolute right-3 top-3 rounded bg-navy/80 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-white uppercase">
        {afterLabel}
      </span>

      {legendLabel ? (
        <div className="pointer-events-none absolute bottom-3 right-3 flex items-center gap-2 rounded-md border border-border bg-bg/95 px-2.5 py-1.5 text-xs text-ink shadow-sm">
          <span
            className="inline-block h-3 w-3 rounded-sm bg-change"
            aria-hidden
          />
          {legendLabel}
        </div>
      ) : null}

      {/* Divider + handle */}
      <div
        className="absolute inset-y-0 z-10 w-px bg-white shadow-[0_0_8px_rgba(0,0,0,0.45)]"
        style={{ left: `${percent}%` }}
      >
        <button
          type="button"
          aria-label="Drag to compare before and after"
          className="absolute top-1/2 left-1/2 flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full border-2 border-white bg-navy text-white shadow-md"
          onPointerDown={(event) => {
            event.preventDefault()
            dragging.current = true
            moveTo(event.clientX)
          }}
        >
          <span className="text-sm leading-none" aria-hidden>
            ‹ ›
          </span>
        </button>
      </div>

      {/* Click anywhere on the frame to jump the wipe */}
      <button
        type="button"
        className="absolute inset-0 z-0 cursor-ew-resize bg-transparent"
        aria-hidden
        tabIndex={-1}
        onPointerDown={(event) => {
          dragging.current = true
          moveTo(event.clientX)
        }}
      />
    </div>
  )
}
