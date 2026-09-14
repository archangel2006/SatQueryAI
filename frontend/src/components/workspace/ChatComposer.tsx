import { useRef, type FormEvent } from 'react'
import { Button } from '../Button'

type ChatComposerProps = {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  stagedFile: File | null
  stagedPreviewUrl: string | null
  onStageFile: (file: File) => void
  onClearStaged: () => void
  disabled?: boolean
  busy?: boolean
}

export function ChatComposer({
  value,
  onChange,
  onSend,
  stagedFile,
  stagedPreviewUrl,
  onStageFile,
  onClearStaged,
  disabled,
  busy,
}: ChatComposerProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const canSend = Boolean(value.trim()) && !disabled && !busy

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (canSend) onSend()
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="border-t border-border bg-bg px-3 py-3"
    >
      {stagedFile ? (
        <div className="mb-2 inline-flex max-w-[220px] items-center gap-2 rounded-xl border border-border bg-surface px-2 py-2 shadow-sm">
          {stagedPreviewUrl ? (
            <img
              src={stagedPreviewUrl}
              alt=""
              className="h-12 w-12 shrink-0 rounded-lg object-cover"
            />
          ) : null}

          <div className="min-w-0">
            <p className="max-w-[120px] truncate text-[11px] font-medium text-ink">
              {stagedFile.name}
            </p>
            <p className="mt-0.5 text-[9px] text-muted">
              Image attached
            </p>
          </div>

          <button
            type="button"
            className="ml-1 shrink-0 rounded-full px-1.5 py-1 text-xs text-muted hover:bg-bg hover:text-ink"
            onClick={onClearStaged}
            disabled={busy}
            aria-label="Remove attachment"
            title="Remove attachment"
          >
            ×
          </button>
        </div>
      ) : null}
      <div className="flex items-end gap-2">
        <input
          ref={fileRef}
          type="file"
          accept=".tif,.tiff,.png,.jpg,.jpeg,image/tiff,image/png,image/jpeg"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onStageFile(file)
            e.target.value = ''
          }}
        />
        <button
          type="button"
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border bg-surface text-ink hover:bg-bg ${stagedFile
              ? 'border-accent text-accent ring-1 ring-accent/40'
              : 'border-border'
            }`}
          title="Attach GeoTIFF or benchmark image"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
        >
          <PaperclipIcon />
        </button>
        <button
          type="button"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-muted opacity-60"
          title="Voice questions — coming soon"
          disabled
        >
          <MicIcon />
        </button>
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={2}
          placeholder={
            stagedFile
              ? 'Ask about this scene…'
              : 'Ask about water, fields, buildings…'
          }
          className="min-h-[2.5rem] flex-1 resize-none rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          disabled={busy}
        />
        <Button
          type="submit"
          variant="primary"
          disabled={!canSend}
          className="bg-accent text-white hover:opacity-90 dark:bg-accent dark:text-navy"
        >
          {busy ? '…' : 'Send'}
        </Button>
      </div>
      <p className="mt-2 text-[11px] text-muted">
        Attach a scene, write your question, then Send · GeoTIFF preferred
      </p>
    </form>
  )
}

function PaperclipIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M21 12.5 12 21.5a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9.5 9.5a2 2 0 0 1-2.8-2.8L15 8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M5 11a7 7 0 0 0 14 0M12 18v3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}
