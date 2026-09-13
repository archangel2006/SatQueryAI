import { useMemo } from 'react'
import { Button } from '../Button'
import type { ImageMetadata } from '../../lib/api'

type ImageRendererProps = {
  previewUrl: string | null
  metadata: ImageMetadata | null
  zoom: number
  onZoomChange: (zoom: number) => void
  onExpand: () => void
  onCloseToSplit: () => void
  expanded?: boolean
}

export function ImageRenderer({
  previewUrl,
  metadata,
  zoom,
  onZoomChange,
  onExpand,
  onCloseToSplit,
  expanded,
}: ImageRendererProps) {
  const chip = useMemo(() => {
    if (!metadata) return null
    if (metadata.format_kind === 'raster') return 'Benchmark image · no CRS'
    return metadata.modality_guess === 'sar' ? 'SAR' : 'Optical'
  }, [metadata])

  function download() {
    if (!previewUrl) return
    const a = document.createElement('a')
    a.href = previewUrl
    a.download = metadata?.filename
      ? `${metadata.filename.replace(/\.[^.]+$/, '')}-preview.png`
      : 'satquery-preview.png'
    a.click()
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">
            {metadata?.filename ?? 'Renderer'}
          </p>
          {chip ? <p className="text-xs text-muted">{chip}</p> : null}
        </div>
        <Button
          variant="ghost"
          className="px-2 text-xs"
          onClick={() => onZoomChange(Math.max(0.5, zoom - 0.25))}
          disabled={!previewUrl}
        >
          −
        </Button>
        <Button
          variant="ghost"
          className="px-2 text-xs"
          onClick={() => onZoomChange(1)}
          disabled={!previewUrl}
        >
          Fit
        </Button>
        <Button
          variant="ghost"
          className="px-2 text-xs"
          onClick={() => onZoomChange(Math.min(4, zoom + 0.25))}
          disabled={!previewUrl}
        >
          +
        </Button>
        <Button
          variant="secondary"
          className="text-xs"
          onClick={download}
          disabled={!previewUrl}
        >
          Download
        </Button>
        {expanded ? (
          <Button variant="secondary" className="text-xs" onClick={onCloseToSplit}>
            Close
          </Button>
        ) : (
          <Button variant="secondary" className="text-xs" onClick={onExpand}>
            Expand
          </Button>
        )}
      </div>

      <div className="relative min-h-0 flex-1 overflow-auto bg-[#0a1220]/5 dark:bg-black/40">
        {previewUrl ? (
          <div className="flex h-full min-h-full w-full items-center justify-center p-4">
            <img
              src={previewUrl}
              alt="Satellite preview"
              className="h-full w-full origin-center rounded-md object-contain shadow-sm transition-transform"
              style={{ transform: `scale(${zoom})` }}
            />
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-sm font-medium text-ink">Preview appears here</p>
            <p className="max-w-sm text-xs text-muted">
              Attach a GeoTIFF (or practice PNG/JPEG). Dev 1 stretch/log preview
              renders on the right; chat stays on the left.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
