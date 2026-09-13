import { useEffect, useRef, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { SignedIn, SignedOut } from '@clerk/clerk-react'
import { Button } from '../components/Button'
import { Navbar } from '../components/Navbar'
import {
  postFusion,
  postPreview,
  previewToObjectUrl,
  type FusionResponse,
  type ImageMetadata,
} from '../lib/api'
import { ROUTES } from '../routes'

type SlotKey = 'optical' | 'sar'

type SceneSlot = {
  file: File | null
  previewUrl: string | null
  metadata: ImageMetadata | null
}

const EMPTY_SLOT: SceneSlot = { file: null, previewUrl: null, metadata: null }

function UploadSlot({
  label,
  hint,
  slot,
  busy,
  onFile,
}: {
  label: string
  hint: string
  slot: SceneSlot
  busy: boolean
  onFile: (file: File) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3 rounded-lg border border-dashed border-border bg-bg p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink">{label}</p>
          <p className="mt-1 text-xs text-muted">{hint}</p>
        </div>
        <Button
          variant="secondary"
          className="shrink-0 text-xs"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          Choose file
        </Button>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".tif,.tiff,.png,.jpg,.jpeg,image/tiff,image/png,image/jpeg"
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onFile(file)
          event.target.value = ''
        }}
      />
      <div className="flex h-64 min-h-44 items-center justify-center overflow-hidden rounded-md border border-border bg-surface">
        {slot.previewUrl ? (
          <img
            src={slot.previewUrl}
            alt={`${label} preview`}
            className="h-full max-h-56 w-full object-contain"
          />
        ) : (
          <p className="px-4 text-center text-xs text-muted">Preview appears here</p>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 text-[11px] text-muted">
        <span className="truncate">{slot.file?.name ?? 'No file selected'}</span>
        {slot.metadata ? (
          <span className="shrink-0 text-right">
            {slot.metadata.modality_guess} · {slot.metadata.width} × {slot.metadata.height}
          </span>
        ) : null}
      </div>
    </div>
  )
}

function Evidence({ result }: { result: FusionResponse }) {
  const evidence = result.evidence
  const rows = [
    ['Water-like area', evidence.water_pct, '%'],
    ['Built-up-like area', evidence.built_up_pct, '%'],
    ['Modality agreement', evidence.modality_agreement, ''],
    ['Valid pixels', evidence.valid_pct, '%'],
  ] as const

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {rows.map(([label, value, suffix]) => (
        <div key={label} className="rounded-md border border-border bg-bg px-3 py-2">
          <p className="text-[11px] text-muted">{label}</p>
          <p className="mt-1 text-sm font-semibold text-ink">
            {typeof value === 'number' ? `${value.toFixed(1)}${suffix}` : 'Unavailable'}
          </p>
        </div>
      ))}
    </div>
  )
}

function CloudSceneWorkspace() {
  const [optical, setOptical] = useState<SceneSlot>(EMPTY_SLOT)
  const [sar, setSar] = useState<SceneSlot>(EMPTY_SLOT)
  const [query, setQuery] = useState('Identify water and built-up regions using both images.')
  const [result, setResult] = useState<FusionResponse | null>(null)
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null)
  const [busySlot, setBusySlot] = useState<SlotKey | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    return () => {
      if (optical.previewUrl) URL.revokeObjectURL(optical.previewUrl)
      if (sar.previewUrl) URL.revokeObjectURL(sar.previewUrl)
      if (overlayUrl) URL.revokeObjectURL(overlayUrl)
    }
  }, [optical.previewUrl, sar.previewUrl, overlayUrl])

  async function chooseFile(kind: SlotKey, file: File) {
    setBusySlot(kind)
    setError(null)
    try {
      const preview = await postPreview(file)
      const nextSlot = {
        file,
        previewUrl: previewToObjectUrl(preview.preview_png_base64),
        metadata: preview.metadata,
      }
      if (kind === 'optical') setOptical(nextSlot)
      else setSar(nextSlot)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not preview image')
    } finally {
      setBusySlot(null)
    }
  }

  async function analyze() {
    if (!optical.file || !sar.file) {
      setError('Choose both an optical image and a SAR image first.')
      return
    }
    setAnalyzing(true)
    setError(null)
    try {
      const nextResult = await postFusion(optical.file, sar.file, query)
      if (overlayUrl) URL.revokeObjectURL(overlayUrl)
      setOverlayUrl(
        nextResult.overlay_png_base64
          ? previewToObjectUrl(nextResult.overlay_png_base64)
          : null,
      )
      setResult(nextResult)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Fusion failed')
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="min-h-screen bg-bg text-ink">
      <Navbar />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-accent">Optical + SAR</p>
          <h1 className="mt-2 font-display text-3xl font-bold">See through cloud</h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Pair optical context with radar structure, then inspect the evidence produced by the fusion baseline.
          </p>
        </div>

        <section className="mt-8 grid gap-4 lg:grid-cols-2">
          <UploadSlot
            label="Optical image"
            hint="GeoTIFF preferred; PNG/JPEG accepted for practice"
            slot={optical}
            busy={busySlot === 'optical' || analyzing}
            onFile={(file) => void chooseFile('optical', file)}
          />
          <UploadSlot
            label="SAR image"
            hint="Single-band SAR GeoTIFF with matching dimensions"
            slot={sar}
            busy={busySlot === 'sar' || analyzing}
            onFile={(file) => void chooseFile('sar', file)}
          />
        </section>

        <section className="mt-4 border-y border-border py-4">
          <label htmlFor="fusion-query" className="text-xs font-semibold uppercase tracking-wide text-ink">
            Analysis question
          </label>
          <div className="mt-2 flex flex-col gap-3 sm:flex-row">
            <textarea
              id="fusion-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows={2}
              className="min-h-12 flex-1 resize-y rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
            <Button
              variant="primary"
              className="shrink-0 self-end bg-accent text-white hover:opacity-90 dark:text-navy"
              disabled={analyzing || busySlot !== null}
              onClick={() => void analyze()}
            >
              {analyzing ? 'Analyzing…' : 'Run fusion'}
            </Button>
          </div>
        </section>

        {error ? <p className="mt-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p> : null}

        {result ? (
          <section className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">
            <div className="overflow-hidden rounded-lg border border-border bg-surface">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <div>
                  <h2 className="text-sm font-semibold text-ink">Fused evidence overlay</h2>
                  <p className="text-xs text-muted">Blue: water-like · red: built-up-like</p>
                </div>
                {overlayUrl ? (
                  <a href={overlayUrl} download="satquery-fusion-overlay.png" className="text-xs font-medium text-accent">
                    Download overlay
                  </a>
                ) : null}
              </div>
              <div className="flex h-96 min-h-72 items-center justify-center bg-[#0a1220]/5 p-5 dark:bg-black/30">
                {overlayUrl ? <img src={overlayUrl} alt="Optical-SAR fusion overlay" className="h-full w-full object-contain" /> : <p className="text-sm text-muted">No overlay returned.</p>}
              </div>
            </div>
            <div className="rounded-lg border border-border bg-surface p-4">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-sm font-semibold text-ink">Specialist result</h2>
                <span className="text-xs text-muted">Score {result.score == null ? '—' : result.score.toFixed(2)}</span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-ink">{result.text}</p>
              <div className="mt-5">
                <Evidence result={result} />
              </div>
            </div>
          </section>
        ) : null}
      </main>
    </div>
  )
}

export function CloudScenePage() {
  return (
    <>
      <SignedOut>
        <Navigate to={ROUTES.signIn} replace />
      </SignedOut>
      <SignedIn>
        <CloudSceneWorkspace />
      </SignedIn>
    </>
  )
}