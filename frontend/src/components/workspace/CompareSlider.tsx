// import { useCallback, useRef, useState } from 'react'
// import { clampComparePercent } from './compareSliderMath'

// type CompareSliderProps = {
//   beforeUrl: string
//   afterUrl: string
//   beforeLabel?: string
//   afterLabel?: string
//   legendLabel?: string
//   zoom?: number
//   initialPercent?: number
// }

// export function CompareSlider({
//   beforeUrl,
//   afterUrl,
//   beforeLabel = 'Before',
//   afterLabel = 'After',
//   legendLabel,
//   zoom = 1,
//   initialPercent = 50,
// }: CompareSliderProps) {
//   const rootRef = useRef<HTMLDivElement>(null)
//   const dragging = useRef(false)

//   const [percent, setPercent] = useState(() =>
//     clampComparePercent(initialPercent),
//   )

//   const moveTo = useCallback((clientX: number) => {
//     const el = rootRef.current
//     if (!el) return

//     const rect = el.getBoundingClientRect()

//     if (rect.width <= 0) return

//     const nextPercent =
//       ((clientX - rect.left) / rect.width) * 100

//     setPercent(clampComparePercent(nextPercent))
//   }, [])

//   const startDragging = useCallback(
//     (clientX: number, pointerId?: number) => {
//       const el = rootRef.current
//       if (!el) return

//       dragging.current = true

//       if (pointerId !== undefined) {
//         try {
//           el.setPointerCapture(pointerId)
//         } catch {
//           // Pointer capture is not available in some browsers.
//         }
//       }

//       moveTo(clientX)
//     },
//     [moveTo],
//   )

//   const stopDragging = useCallback((pointerId?: number) => {
//     const el = rootRef.current

//     dragging.current = false

//     if (el && pointerId !== undefined) {
//       try {
//         if (el.hasPointerCapture(pointerId)) {
//           el.releasePointerCapture(pointerId)
//         }
//       } catch {
//         // Ignore pointer-capture cleanup errors.
//       }
//     }
//   }, [])

//   const handlePointerMove = useCallback(
//     (event: React.PointerEvent<HTMLDivElement>) => {
//       if (!dragging.current) return

//       event.preventDefault()
//       moveTo(event.clientX)
//     },
//     [moveTo],
//   )

//   const handlePointerDown = useCallback(
//     (event: React.PointerEvent<HTMLDivElement>) => {
//       if (event.button !== 0 && event.pointerType !== 'touch') return

//       event.preventDefault()

//       startDragging(event.clientX, event.pointerId)
//     },
//     [startDragging],
//   )

//   const handlePointerUp = useCallback(
//     (event: React.PointerEvent<HTMLDivElement>) => {
//       stopDragging(event.pointerId)
//     },
//     [stopDragging],
//   )

//   const handlePointerCancel = useCallback(
//     (event: React.PointerEvent<HTMLDivElement>) => {
//       stopDragging(event.pointerId)
//     },
//     [stopDragging],
//   )

//   const handleKeyDown = (
//     event: React.KeyboardEvent<HTMLDivElement>,
//   ) => {
//     if (event.key === 'ArrowLeft') {
//       event.preventDefault()
//       setPercent((current) =>
//         clampComparePercent(current - 2),
//       )
//     }

//     if (event.key === 'ArrowRight') {
//       event.preventDefault()
//       setPercent((current) =>
//         clampComparePercent(current + 2),
//       )
//     }

//     if (event.key === 'Home') {
//       event.preventDefault()
//       setPercent(0)
//     }

//     if (event.key === 'End') {
//       event.preventDefault()
//       setPercent(100)
//     }
//   }

//   const safeZoom = Math.max(0.5, Math.min(4, zoom))

//   return (
//     <div
//       ref={rootRef}
//       className="relative mx-auto h-full min-h-0 w-full min-w-0 max-w-full touch-none select-none overflow-hidden rounded-xl border border-border bg-[#0a1220]/50 shadow-sm"
//       role="slider"
//       aria-label="Before and after comparison"
//       aria-valuemin={0}
//       aria-valuemax={100}
//       aria-valuenow={Math.round(percent)}
//       aria-valuetext={`${Math.round(percent)}% before`}
//       tabIndex={0}
//       onKeyDown={handleKeyDown}
//       onPointerDown={handlePointerDown}
//       onPointerMove={handlePointerMove}
//       onPointerUp={handlePointerUp}
//       onPointerCancel={handlePointerCancel}
//     >
//       {/* AFTER — complete scene */}
//       <div className="absolute inset-0 overflow-hidden">
//         <img
//           src={afterUrl}
//           alt=""
//           draggable={false}
//           className="absolute inset-0 h-full w-full object-contain"
//           style={{
//             transform: `scale(${safeZoom})`,
//             transformOrigin: 'center center',
//           }}
//         />
//       </div>

//       {/* BEFORE — clipped at the comparison position */}
//       <div
//         className="absolute inset-0 overflow-hidden"
//         style={{
//           clipPath: `inset(0 ${100 - percent}% 0 0)`,
//         }}
//       >
//         <img
//           src={beforeUrl}
//           alt=""
//           draggable={false}
//           className="absolute inset-0 h-full w-full object-contain"
//           style={{
//             transform: `scale(${safeZoom})`,
//             transformOrigin: 'center center',
//           }}
//         />
//       </div>

//       {/* Scene labels */}
//       <div className="pointer-events-none absolute left-3 top-3 z-20">
//         <span className="inline-flex items-center rounded-md border border-white/15 bg-navy/85 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-white shadow-md backdrop-blur-sm">
//           {beforeLabel}
//         </span>
//       </div>

//       <div className="pointer-events-none absolute right-3 top-3 z-20">
//         <span className="inline-flex items-center rounded-md border border-white/15 bg-navy/85 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-white shadow-md backdrop-blur-sm">
//           {afterLabel}
//         </span>
//       </div>

//       {/* Change legend */}
//       {legendLabel ? (
//         <div className="pointer-events-none absolute bottom-3 right-3 z-20 flex items-center gap-2 rounded-lg border border-border bg-bg/95 px-2.5 py-1.5 text-xs text-ink shadow-md backdrop-blur-sm">
//           <span
//             className="inline-block h-2.5 w-2.5 rounded-sm bg-change"
//             aria-hidden
//           />
//           {legendLabel}
//         </div>
//       ) : null}

//       {/* Comparison divider */}
//       <div
//         className="pointer-events-none absolute inset-y-0 z-30"
//         style={{
//           left: `${percent}%`,
//         }}
//       >
//         {/* Soft divider glow */}
//         <div className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 bg-black/20 blur-[2px]" />

//         {/* Main divider */}
//         <div className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-white shadow-[0_0_10px_rgba(0,0,0,0.45)]" />

//         {/* Drag handle */}
//         <button
//           type="button"
//           aria-label="Drag to compare before and after"
//           className="pointer-events-auto absolute left-1/2 top-1/2 flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full border-2 border-white bg-navy text-white shadow-[0_3px_12px_rgba(0,0,0,0.35)] transition-transform duration-100 hover:scale-105 active:scale-95"
//           onPointerDown={(event) => {
//             event.preventDefault()
//             event.stopPropagation()

//             startDragging(event.clientX, event.pointerId)
//           }}
//         >
//           <span
//             className="flex items-center gap-0.5 text-lg font-light leading-none"
//             aria-hidden
//           >
//             <span className="-mr-0.5">‹</span>
//             <span className="-ml-0.5">›</span>
//           </span>
//         </button>
//       </div>

//       {/* Small position indicator */}
//       <div className="pointer-events-none absolute bottom-3 left-3 z-20 rounded-md border border-white/10 bg-navy/80 px-2 py-1 text-[10px] font-medium tabular-nums text-white/85 shadow-sm backdrop-blur-sm">
//         {Math.round(percent)}%
//       </div>
//     </div>
//   )
// }






















import { useCallback, useRef, useState } from 'react'
import { clampComparePercent } from './compareSliderMath'

type CompareSliderProps = {
  beforeUrl: string
  afterUrl: string
  changeOverlayUrl?: string
  beforeLabel?: string
  afterLabel?: string
  legendLabel?: string
  zoom?: number
  initialPercent?: number
}

export function CompareSlider({
  beforeUrl,
  afterUrl,
  changeOverlayUrl,
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

  const moveTo = useCallback((clientX: number) => {
    const el = rootRef.current
    if (!el) return

    const rect = el.getBoundingClientRect()

    if (rect.width <= 0) return

    const nextPercent =
      ((clientX - rect.left) / rect.width) * 100

    setPercent(clampComparePercent(nextPercent))
  }, [])

  const startDragging = useCallback(
    (clientX: number, pointerId?: number) => {
      const el = rootRef.current
      if (!el) return

      dragging.current = true

      if (pointerId !== undefined) {
        try {
          el.setPointerCapture(pointerId)
        } catch {
          // Pointer capture is not available in some browsers.
        }
      }

      moveTo(clientX)
    },
    [moveTo],
  )

  const stopDragging = useCallback((pointerId?: number) => {
    const el = rootRef.current

    dragging.current = false

    if (el && pointerId !== undefined) {
      try {
        if (el.hasPointerCapture(pointerId)) {
          el.releasePointerCapture(pointerId)
        }
      } catch {
        // Ignore pointer-capture cleanup errors.
      }
    }
  }, [])

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!dragging.current) return

      event.preventDefault()
      moveTo(event.clientX)
    },
    [moveTo],
  )

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.button !== 0 && event.pointerType !== 'touch') return

      event.preventDefault()

      startDragging(event.clientX, event.pointerId)
    },
    [startDragging],
  )

  const handlePointerUp = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      stopDragging(event.pointerId)
    },
    [stopDragging],
  )

  const handlePointerCancel = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      stopDragging(event.pointerId)
    },
    [stopDragging],
  )

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLDivElement>,
  ) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault()
      setPercent((current) =>
        clampComparePercent(current - 2),
      )
    }

    if (event.key === 'ArrowRight') {
      event.preventDefault()
      setPercent((current) =>
        clampComparePercent(current + 2),
      )
    }

    if (event.key === 'Home') {
      event.preventDefault()
      setPercent(0)
    }

    if (event.key === 'End') {
      event.preventDefault()
      setPercent(100)
    }
  }

  const safeZoom = Math.max(0.5, Math.min(4, zoom))

  return (
    <div
      ref={rootRef}
      className="relative mx-auto h-full min-h-0 w-full min-w-0 max-w-full touch-none select-none overflow-hidden rounded-xl border border-border bg-[#0a1220]/50 shadow-sm"
      role="slider"
      aria-label="Before and after comparison"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(percent)}
      aria-valuetext={`${Math.round(percent)}% before`}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerCancel}
    >
      {/* AFTER — complete scene */}
      <div className="absolute inset-0 z-0 overflow-hidden">
        <img
          src={afterUrl}
          alt=""
          draggable={false}
          className="absolute inset-0 h-full w-full object-contain"
          style={{
            transform: `scale(${safeZoom})`,
            transformOrigin: 'center center',
          }}
        />

        {/* CHANGE OVERLAY — model-generated highlighted regions */}
        {changeOverlayUrl ? (
          <img
            src={changeOverlayUrl}
            alt="Detected changes"
            draggable={false}
            className="pointer-events-none absolute inset-0 h-full w-full object-contain"
            style={{
              transform: `scale(${safeZoom})`,
              transformOrigin: 'center center',
            }}
          />
        ) : null}
      </div>

      {/* BEFORE — clipped at the comparison position */}
      <div
        className="absolute inset-0 z-10 overflow-hidden"
        style={{
          clipPath: `inset(0 ${100 - percent}% 0 0)`,
        }}
      >
        <img
          src={beforeUrl}
          alt=""
          draggable={false}
          className="absolute inset-0 h-full w-full object-contain"
          style={{
            transform: `scale(${safeZoom})`,
            transformOrigin: 'center center',
          }}
        />
      </div>

      {/* Scene labels */}
      <div className="pointer-events-none absolute left-3 top-3 z-20">
        <span className="inline-flex items-center rounded-md border border-white/15 bg-navy/85 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-white shadow-md backdrop-blur-sm">
          {beforeLabel}
        </span>
      </div>

      <div className="pointer-events-none absolute right-3 top-3 z-20">
        <span className="inline-flex items-center rounded-md border border-white/15 bg-navy/85 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-white shadow-md backdrop-blur-sm">
          {afterLabel}
        </span>
      </div>

      {/* Change legend */}
      {legendLabel ? (
        <div className="pointer-events-none absolute bottom-3 right-3 z-20 flex items-center gap-2 rounded-lg border border-border bg-bg/95 px-2.5 py-1.5 text-xs text-ink shadow-md backdrop-blur-sm">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm bg-change"
            aria-hidden
          />
          {legendLabel}
        </div>
      ) : null}

      {/* Comparison divider */}
      <div
        className="pointer-events-none absolute inset-y-0 z-30"
        style={{
          left: `${percent}%`,
        }}
      >
        {/* Soft divider glow */}
        <div className="absolute inset-y-0 left-1/2 w-1 -translate-x-1/2 bg-black/20 blur-[2px]" />

        {/* Main divider */}
        <div className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-white shadow-[0_0_10px_rgba(0,0,0,0.45)]" />

        {/* Drag handle */}
        <button
          type="button"
          aria-label="Drag to compare before and after"
          className="pointer-events-auto absolute left-1/2 top-1/2 flex h-12 w-12 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full border-2 border-white bg-navy text-white shadow-[0_3px_12px_rgba(0,0,0,0.35)] transition-transform duration-100 hover:scale-105 active:scale-95"
          onPointerDown={(event) => {
            event.preventDefault()
            event.stopPropagation()

            startDragging(event.clientX, event.pointerId)
          }}
        >
          <span
            className="flex items-center gap-0.5 text-lg font-light leading-none"
            aria-hidden
          >
            <span className="-mr-0.5">‹</span>
            <span className="-ml-0.5">›</span>
          </span>
        </button>
      </div>

      {/* Small position indicator */}
      <div className="pointer-events-none absolute bottom-3 left-3 z-20 rounded-md border border-white/10 bg-navy/80 px-2 py-1 text-[10px] font-medium tabular-nums text-white/85 shadow-sm backdrop-blur-sm">
        {Math.round(percent)}%
      </div>
    </div>
  )
}