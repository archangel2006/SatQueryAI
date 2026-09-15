// import { useRef } from 'react'
// import { Button } from '../Button'
// import { CompareSlider } from './CompareSlider'

// type SlotProps = {
//   label: string
//   filename: string | null
//   onFile: (file: File) => void
//   busy?: boolean
// }

// function UploadSlot({ label, filename, onFile, busy }: SlotProps) {
//   const inputRef = useRef<HTMLInputElement>(null)

//   return (
//     <div className="relative flex min-w-0 flex-1 flex-col gap-1.5 rounded-lg border border-dashed border-border bg-bg px-3 py-2.5">
//       <div className="flex items-center justify-between gap-2">
//         <p className="text-xs font-semibold tracking-wide text-ink uppercase">
//           {label}
//         </p>

//         <Button
//           variant="secondary"
//           className="shrink-0 px-2.5 text-xs"
//           disabled={busy}
//           onClick={() => inputRef.current?.click()}
//         >
//           Upload
//         </Button>
//       </div>

//       <p className="truncate text-[11px] text-muted">
//         {filename ?? 'GeoTIFF or PNG/JPEG · drop-in for this date'}
//       </p>

//       {busy ? (
//         <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-bg/90">
//           <div className="flex items-center gap-2 text-xs text-muted">
//             <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
//             Uploading…
//           </div>
//         </div>
//       ) : null}

//       <input
//         ref={inputRef}
//         type="file"
//         accept=".tif,.tiff,.png,.jpg,.jpeg,image/tiff,image/png,image/jpeg"
//         className="sr-only"
//         onChange={(event) => {
//           const file = event.target.files?.[0]
//           if (file) onFile(file)
//           event.target.value = ''
//         }}
//       />
//     </div>
//   )
// }

// type BeforeAfterRendererProps = {
//   beforeUrl: string
//   afterUrl: string
//   beforeFilename?: string | null
//   afterFilename?: string | null
//   title?: string
//   subtitle?: string
//   legendLabel?: string | null
//   zoom: number
//   onZoomChange: (zoom: number) => void
//   onExpand: () => void
//   onCloseToSplit: () => void
//   expanded?: boolean
//   onUploadBefore: (file: File) => void
//   onUploadAfter: (file: File) => void
//   uploadBusy?: boolean
// }

// export function BeforeAfterRenderer({
//   beforeUrl,
//   afterUrl,
//   beforeFilename,
//   afterFilename,
//   title = 'Before · After',
//   subtitle,
//   legendLabel = 'New built-up',
//   zoom,
//   onZoomChange,
//   onExpand,
//   onCloseToSplit,
//   expanded,
//   onUploadBefore,
//   onUploadAfter,
//   uploadBusy,
// }: BeforeAfterRendererProps) {
//   function download() {
//     const a = document.createElement('a')
//     a.href = afterUrl
//     a.download = 'satquery-after-preview.png'
//     a.click()
//   }

//   return (
//     <div className="flex h-full min-h-0 flex-col bg-surface">
//       <div className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-3 py-2">
//         <div className="min-w-0 flex-1">
//           <p className="truncate text-sm font-medium text-ink">{title}</p>
//           {subtitle ? <p className="text-xs text-muted">{subtitle}</p> : null}
//         </div>
//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() => onZoomChange(Math.max(0.5, zoom - 0.25))}
//         >
//           −
//         </Button>
//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() => onZoomChange(1)}
//         >
//           Fit
//         </Button>
//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() => onZoomChange(Math.min(4, zoom + 0.25))}
//         >
//           +
//         </Button>
//         <Button variant="secondary" className="text-xs" onClick={download}>
//           Download
//         </Button>
//         {expanded ? (
//           <Button variant="secondary" className="text-xs" onClick={onCloseToSplit}>
//             Close
//           </Button>
//         ) : (
//           <Button variant="secondary" className="text-xs" onClick={onExpand}>
//             Expand
//           </Button>
//         )}
//       </div>

//       <div className="relative min-h-0 flex-1 overflow-hidden p-3">
//         <CompareSlider
//           beforeUrl={beforeUrl}
//           afterUrl={afterUrl}
//           legendLabel={legendLabel ?? undefined}
//           zoom={zoom}
//         />
//       </div>

//       <div className="border-t border-border px-3 py-3">
//         <div className="flex flex-col gap-2 sm:flex-row">
//           <UploadSlot
//             label="Before (left)"
//             filename={beforeFilename ?? null}
//             onFile={onUploadBefore}
//             busy={uploadBusy}
//           />
//           <UploadSlot
//             label="After (right)"
//             filename={afterFilename ?? null}
//             onFile={onUploadAfter}
//             busy={uploadBusy}
//           />
//         </div>
//         <p className="mt-2 text-center text-[11px] text-muted">
//           Drag the handle to compare · upload replaces each side
//         </p>
//       </div>
//     </div>
//   )
// }













// import { useRef } from 'react'
// import { Button } from '../Button'
// import { CompareSlider } from './CompareSlider'

// type SlotProps = {
//   label: string
//   filename: string | null
//   onFile: (file: File) => void
//   busy?: boolean
//   side: 'before' | 'after'
// }

// function UploadSlot({
//   label,
//   filename,
//   onFile,
//   busy,
//   side,
// }: SlotProps) {
//   const inputRef = useRef<HTMLInputElement>(null)

//   const hasFile = Boolean(filename)

//   return (
//     <div className="flex min-w-0 flex-1 items-center gap-3 rounded-lg border border-border bg-bg px-3 py-2.5">
//       <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-surface">
//         <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
//           {side === 'before' ? '01' : '02'}
//         </span>
//       </div>

//       <div className="min-w-0 flex-1">
//         <div className="flex items-center gap-2">
//           <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
//             {label}
//           </p>

//           {hasFile ? (
//             <span className="h-1.5 w-1.5 rounded-full bg-ink" />
//           ) : null}
//         </div>

//         <p
//           className="mt-0.5 truncate text-xs text-ink"
//           title={filename ?? undefined}
//         >
//           {filename ?? 'No scene selected'}
//         </p>
//       </div>

//       <Button
//         variant="secondary"
//         className="shrink-0 px-2.5 text-xs"
//         disabled={busy}
//         onClick={() => inputRef.current?.click()}
//       >
//         {hasFile ? 'Replace' : 'Upload'}
//       </Button>

//       <input
//         ref={inputRef}
//         type="file"
//         accept=".tif,.tiff,.png,.jpg,.jpeg,image/tiff,image/png,image/jpeg"
//         className="sr-only"
//         onChange={(event) => {
//           const file = event.target.files?.[0]

//           if (file) {
//             onFile(file)
//           }

//           event.target.value = ''
//         }}
//       />
//     </div>
//   )
// }

// type BeforeAfterRendererProps = {
//   beforeUrl: string
//   afterUrl: string
//   beforeFilename?: string | null
//   afterFilename?: string | null
//   title?: string
//   subtitle?: string
//   legendLabel?: string | null
//   zoom: number
//   onZoomChange: (zoom: number) => void
//   onExpand: () => void
//   onCloseToSplit: () => void
//   expanded?: boolean
//   onUploadBefore: (file: File) => void
//   onUploadAfter: (file: File) => void
//   uploadBusy?: boolean
// }

// export function BeforeAfterRenderer({
//   beforeUrl,
//   afterUrl,
//   beforeFilename,
//   afterFilename,
//   title = 'Before · After',
//   subtitle,
//   legendLabel = 'New built-up',
//   zoom,
//   onZoomChange,
//   onExpand,
//   onCloseToSplit,
//   expanded,
//   onUploadBefore,
//   onUploadAfter,
//   uploadBusy,
// }: BeforeAfterRendererProps) {
//   function download() {
//     const a = document.createElement('a')
//     a.href = afterUrl
//     a.download = 'satquery-after-preview.png'
//     a.click()
//   }

//   return (
//     <div className="flex h-full min-h-0 flex-col bg-surface">
//       <div className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-3 py-2">
//         <div className="min-w-0 flex-1">
//           <p className="truncate text-sm font-medium text-ink">
//             {title}
//           </p>

//           {subtitle ? (
//             <p className="text-xs text-muted">{subtitle}</p>
//           ) : null}
//         </div>

//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() =>
//             onZoomChange(Math.max(0.5, zoom - 0.25))
//           }
//         >
//           −
//         </Button>

//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() => onZoomChange(1)}
//         >
//           Fit
//         </Button>

//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() =>
//             onZoomChange(Math.min(4, zoom + 0.25))
//           }
//         >
//           +
//         </Button>

//         <Button
//           variant="secondary"
//           className="text-xs"
//           onClick={download}
//         >
//           Download
//         </Button>

//         {expanded ? (
//           <Button
//             variant="secondary"
//             className="text-xs"
//             onClick={onCloseToSplit}
//           >
//             Close
//           </Button>
//         ) : (
//           <Button
//             variant="secondary"
//             className="text-xs"
//             onClick={onExpand}
//           >
//             Expand
//           </Button>
//         )}
//       </div>

//       <div className="relative min-h-0 flex-1 overflow-hidden p-3">
//         <CompareSlider
//           beforeUrl={beforeUrl}
//           afterUrl={afterUrl}
//           legendLabel={legendLabel ?? undefined}
//           zoom={zoom}
//         />
//       </div>

//       <div className="border-t border-border bg-bg px-3 py-3">
//         <div className="mb-2.5 flex items-center justify-between">
//           <div>
//             <p className="text-xs font-semibold text-ink">
//               Scene setup
//             </p>

//             <p className="mt-0.5 text-[11px] text-muted">
//               Choose the two scenes to compare
//             </p>
//           </div>

//           {beforeFilename && afterFilename ? (
//             <span className="text-[10px] font-medium uppercase tracking-wider text-muted">
//               Ready
//             </span>
//           ) : null}
//         </div>

//         <div className="flex flex-col gap-2 sm:flex-row">
//           <UploadSlot
//             label="Before"
//             side="before"
//             filename={beforeFilename ?? null}
//             onFile={onUploadBefore}
//             busy={uploadBusy}
//           />

//           <UploadSlot
//             label="After"
//             side="after"
//             filename={afterFilename ?? null}
//             onFile={onUploadAfter}
//             busy={uploadBusy}
//           />
//         </div>

//         <p className="mt-2 text-center text-[10px] text-muted">
//           GeoTIFF, PNG or JPEG · replacing a scene updates that side
//         </p>
//       </div>
//     </div>
//   )
// }






// import { useRef } from 'react'
// import { Button } from '../Button'
// import { CompareSlider } from './CompareSlider'

// type SlotProps = {
//   label: string
//   filename: string | null
//   onFile: (file: File) => void
//   busy?: boolean
//   side: 'before' | 'after'
// }

// function UploadSlot({
//   label,
//   filename,
//   onFile,
//   busy,
//   side,
// }: SlotProps) {
//   const inputRef = useRef<HTMLInputElement>(null)

//   const hasFile = Boolean(filename)

//   return (
//     <div
//       className={[
//         'flex min-w-0 flex-1 items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors',
//         side === 'before'
//           ? 'border-border bg-bg'
//           : 'border-border bg-surface',
//         hasFile ? 'ring-1 ring-emerald-500/15' : '',
//       ].join(' ')}
//     >
//       <div
//         className={[
//           'flex h-9 w-9 shrink-0 items-center justify-center rounded-md border',
//           hasFile
//             ? 'border-emerald-500/30 bg-emerald-500/10'
//             : side === 'before'
//               ? 'border-border bg-surface'
//               : 'border-border bg-bg',
//         ].join(' ')}
//       >
//         {hasFile ? (
//           <svg
//             viewBox="0 0 20 20"
//             fill="none"
//             className="h-4 w-4 text-emerald-600"
//             aria-hidden="true"
//           >
//             <path
//               d="M5 10.5L8.2 13.5L15 6.5"
//               stroke="currentColor"
//               strokeWidth="2"
//               strokeLinecap="round"
//               strokeLinejoin="round"
//             />
//           </svg>
//         ) : (
//           <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
//             {side === 'before' ? '01' : '02'}
//           </span>
//         )}
//       </div>

//       <div className="min-w-0 flex-1">
//         <div className="flex items-center gap-2">
//           <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
//             {label}
//           </p>

//           {hasFile ? (
//             <span className="text-[9px] font-medium uppercase tracking-wide text-emerald-600">
//               Attached
//             </span>
//           ) : null}
//         </div>

//         <p
//           className="mt-0.5 truncate text-xs text-ink"
//           title={filename ?? undefined}
//         >
//           {filename ?? 'No scene selected'}
//         </p>
//       </div>

//       <Button
//         variant="secondary"
//         className="shrink-0 px-2.5 text-xs"
//         disabled={busy}
//         onClick={() => inputRef.current?.click()}
//       >
//         {hasFile ? 'Replace' : 'Upload'}
//       </Button>

//       <input
//         ref={inputRef}
//         type="file"
//         accept=".tif,.tiff,.png,.jpg,.jpeg,image/tiff,image/png,image/jpeg"
//         className="sr-only"
//         onChange={(event) => {
//           const file = event.target.files?.[0]

//           if (file) {
//             onFile(file)
//           }

//           event.target.value = ''
//         }}
//       />
//     </div>
//   )
// }

// type BeforeAfterRendererProps = {
//   beforeUrl: string
//   afterUrl: string
//   beforeFilename?: string | null
//   afterFilename?: string | null
//   title?: string
//   subtitle?: string
//   legendLabel?: string | null
//   zoom: number
//   onZoomChange: (zoom: number) => void
//   onExpand: () => void
//   onCloseToSplit: () => void
//   expanded?: boolean
//   onUploadBefore: (file: File) => void
//   onUploadAfter: (file: File) => void
//   uploadBusy?: boolean
// }

// export function BeforeAfterRenderer({
//   beforeUrl,
//   afterUrl,
//   beforeFilename,
//   afterFilename,
//   title = 'Before · After',
//   subtitle,
//   legendLabel = 'New built-up',
//   zoom,
//   onZoomChange,
//   onExpand,
//   onCloseToSplit,
//   expanded,
//   onUploadBefore,
//   onUploadAfter,
//   uploadBusy,
// }: BeforeAfterRendererProps) {
//   function download() {
//     const a = document.createElement('a')
//     a.href = afterUrl
//     a.download = 'satquery-after-preview.png'
//     a.click()
//   }

//   return (
//     <div className="flex h-full min-h-0 flex-col bg-surface">
//       <div className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-3 py-2">
//         <div className="min-w-0 flex-1">
//           <p className="truncate text-sm font-medium text-ink">
//             {title}
//           </p>

//           {subtitle ? (
//             <p className="text-xs text-muted">{subtitle}</p>
//           ) : null}
//         </div>

//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() =>
//             onZoomChange(Math.max(0.5, zoom - 0.25))
//           }
//         >
//           −
//         </Button>

//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() => onZoomChange(1)}
//         >
//           Fit
//         </Button>

//         <Button
//           variant="ghost"
//           className="px-2 text-xs"
//           onClick={() =>
//             onZoomChange(Math.min(4, zoom + 0.25))
//           }
//         >
//           +
//         </Button>

//         <Button
//           variant="secondary"
//           className="text-xs"
//           onClick={download}
//         >
//           Download
//         </Button>

//         {expanded ? (
//           <Button
//             variant="secondary"
//             className="text-xs"
//             onClick={onCloseToSplit}
//           >
//             Close
//           </Button>
//         ) : (
//           <Button
//             variant="secondary"
//             className="text-xs"
//             onClick={onExpand}
//           >
//             Expand
//           </Button>
//         )}
//       </div>

//       <div className="relative min-h-0 flex-1 overflow-hidden p-3">
//         <CompareSlider
//           beforeUrl={beforeUrl}
//           afterUrl={afterUrl}
//           legendLabel={legendLabel ?? undefined}
//           zoom={zoom}
//         />
//       </div>

//       <div className="border-t border-border bg-bg px-3 py-3">
//         <div className="mb-2.5 flex items-center justify-between">
//           <div>
//             <p className="text-xs font-semibold text-ink">
//               Scene setup
//             </p>

//             <p className="mt-0.5 text-[11px] text-muted">
//               Choose the two scenes to compare
//             </p>
//           </div>

//           {beforeFilename && afterFilename ? (
//             <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-emerald-600">
//               <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500/10">
//                 <svg
//                   viewBox="0 0 20 20"
//                   fill="none"
//                   className="h-2.5 w-2.5"
//                   aria-hidden="true"
//                 >
//                   <path
//                     d="M5 10.5L8.2 13.5L15 6.5"
//                     stroke="currentColor"
//                     strokeWidth="2"
//                     strokeLinecap="round"
//                     strokeLinejoin="round"
//                   />
//                 </svg>
//               </span>
//               Ready
//             </span>
//           ) : null}
//         </div>

//         <div className="flex flex-col gap-2 sm:flex-row">
//           <UploadSlot
//             label="Before"
//             side="before"
//             filename={beforeFilename ?? null}
//             onFile={onUploadBefore}
//             busy={uploadBusy}
//           />

//           <UploadSlot
//             label="After"
//             side="after"
//             filename={afterFilename ?? null}
//             onFile={onUploadAfter}
//             busy={uploadBusy}
//           />
//         </div>

//         <p className="mt-2 text-center text-[10px] text-muted">
//           GeoTIFF, PNG or JPEG · replacing a scene updates that side
//         </p>
//       </div>
//     </div>
//   )
// }









import { useRef } from 'react'
import { Button } from '../Button'
import { CompareSlider } from './CompareSlider'

type SlotProps = {
  label: string
  filename: string | null
  onFile: (file: File) => void
  busy?: boolean
  side: 'before' | 'after'
}

function UploadSlot({
  label,
  filename,
  onFile,
  busy,
  side,
}: SlotProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  const hasFile = Boolean(filename)

  return (
    <div
      className={[
        'flex min-w-0 flex-1 items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors',
        side === 'before'
          ? 'border-border bg-bg'
          : 'border-border bg-surface',
        hasFile ? 'ring-1 ring-emerald-500/15' : '',
      ].join(' ')}
    >
      <div
        className={[
          'flex h-9 w-9 shrink-0 items-center justify-center rounded-md border',
          hasFile
            ? 'border-emerald-500/30 bg-emerald-500/10'
            : side === 'before'
              ? 'border-border bg-surface'
              : 'border-border bg-bg',
        ].join(' ')}
      >
        {hasFile ? (
          <svg
            viewBox="0 0 20 20"
            fill="none"
            className="h-4 w-4 text-emerald-600"
            aria-hidden="true"
          >
            <path
              d="M5 10.5L8.2 13.5L15 6.5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : (
          <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
            {side === 'before' ? '01' : '02'}
          </span>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            {label}
          </p>

          {hasFile ? (
            <span className="text-[9px] font-medium uppercase tracking-wide text-emerald-600">
              Attached
            </span>
          ) : null}
        </div>

        <p
          className="mt-0.5 truncate text-xs text-ink"
          title={filename ?? undefined}
        >
          {filename ?? 'No scene selected'}
        </p>
      </div>

      <Button
        variant="secondary"
        className="shrink-0 px-2.5 text-xs"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {hasFile ? 'Replace' : 'Upload'}
      </Button>

      <input
        ref={inputRef}
        type="file"
        accept=".tif,.tiff,.png,.jpg,.jpeg,image/tiff,image/png,image/jpeg"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0]

          if (file) {
            onFile(file)
          }

          event.target.value = ''
        }}
      />
    </div>
  )
}

type BeforeAfterRendererProps = {
  beforeUrl: string
  afterUrl: string
  changeOverlayUrl?: string | null
  beforeFilename?: string | null
  afterFilename?: string | null
  title?: string
  subtitle?: string
  legendLabel?: string | null
  zoom: number
  onZoomChange: (zoom: number) => void
  onExpand: () => void
  onCloseToSplit: () => void
  expanded?: boolean
  onUploadBefore: (file: File) => void
  onUploadAfter: (file: File) => void
  uploadBusy?: boolean
}

export function BeforeAfterRenderer({
  beforeUrl,
  afterUrl,
  changeOverlayUrl,
  beforeFilename,
  afterFilename,
  title = 'Before · After',
  subtitle,
  legendLabel = 'New built-up',
  zoom,
  onZoomChange,
  onExpand,
  onCloseToSplit,
  expanded,
  onUploadBefore,
  onUploadAfter,
  uploadBusy,
}: BeforeAfterRendererProps) {
  function download() {
    const a = document.createElement('a')
    a.href = afterUrl
    a.download = 'satquery-after-preview.png'
    a.click()
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">
            {title}
          </p>

          {subtitle ? (
            <p className="text-xs text-muted">{subtitle}</p>
          ) : null}
        </div>

        <Button
          variant="ghost"
          className="px-2 text-xs"
          onClick={() =>
            onZoomChange(Math.max(0.5, zoom - 0.25))
          }
        >
          −
        </Button>

        <Button
          variant="ghost"
          className="px-2 text-xs"
          onClick={() => onZoomChange(1)}
        >
          Fit
        </Button>

        <Button
          variant="ghost"
          className="px-2 text-xs"
          onClick={() =>
            onZoomChange(Math.min(4, zoom + 0.25))
          }
        >
          +
        </Button>

        <Button
          variant="secondary"
          className="text-xs"
          onClick={download}
        >
          Download
        </Button>

        {expanded ? (
          <Button
            variant="secondary"
            className="text-xs"
            onClick={onCloseToSplit}
          >
            Close
          </Button>
        ) : (
          <Button
            variant="secondary"
            className="text-xs"
            onClick={onExpand}
          >
            Expand
          </Button>
        )}
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden p-3">
        <CompareSlider
          beforeUrl={beforeUrl}
          afterUrl={afterUrl}
          changeOverlayUrl={changeOverlayUrl ?? undefined}
          legendLabel={legendLabel ?? undefined}
          zoom={zoom}
        />
      </div>

      <div className="border-t border-border bg-bg px-3 py-3">
        <div className="mb-2.5 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-ink">
              Scene setup
            </p>

            <p className="mt-0.5 text-[11px] text-muted">
              Choose the two scenes to compare
            </p>
          </div>

          {beforeFilename && afterFilename ? (
            <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-emerald-600">
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500/10">
                <svg
                  viewBox="0 0 20 20"
                  fill="none"
                  className="h-2.5 w-2.5"
                  aria-hidden="true"
                >
                  <path
                    d="M5 10.5L8.2 13.5L15 6.5"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              Ready
            </span>
          ) : null}
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <UploadSlot
            label="Before"
            side="before"
            filename={beforeFilename ?? null}
            onFile={onUploadBefore}
            busy={uploadBusy}
          />

          <UploadSlot
            label="After"
            side="after"
            filename={afterFilename ?? null}
            onFile={onUploadAfter}
            busy={uploadBusy}
          />
        </div>

        <p className="mt-2 text-center text-[10px] text-muted">
          GeoTIFF, PNG or JPEG · replacing a scene updates that side
        </p>
      </div>
    </div>
  )
}