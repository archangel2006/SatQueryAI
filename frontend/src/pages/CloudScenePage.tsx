import { useEffect, useRef, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { SignedIn, SignedOut } from '@clerk/clerk-react'
import { Button } from '../components/Button'
import { Navbar } from '../components/Navbar'
import { ChatPanel } from '../components/workspace/ChatPanel'
import type { ChatMessageData } from '../components/workspace/ChatMessage'
import { SessionSidebar } from '../components/workspace/SessionSidebar'
import { SplitWorkspace } from '../components/workspace/SplitWorkspace'
import type { WorkspaceMode } from '../components/workspace/splitState'
import { postFusion, postFusionFollowUp, postPreview, previewToObjectUrl, type ImageMetadata, type SessionListItem } from '../lib/api'
import { useSpokenLocale } from '../lib/useSpokenLocale'
import { ROUTES } from '../routes'

type SlotKey = 'optical' | 'sar'
type View = 'optical' | 'sar' | 'overlay'
type SceneSlot = { file: File | null; previewUrl: string | null; metadata: ImageMetadata | null }
type FusionContext = { summary: string; evidence: Record<string, unknown> }
type FusionHistory = { id: string; title: string; messages: ChatMessageData[]; context: FusionContext | null; updatedAt: string }

const HISTORY_KEY = 'satquery.opticalSarHistory'

const EMPTY_SLOT: SceneSlot = { file: null, previewUrl: null, metadata: null }
const WELCOME: ChatMessageData = {
  id: 'welcome', role: 'assistant',
  text: 'Upload a six-band **Sentinel-2** GeoTIFF and a two-band **Sentinel-1 VV/VH** GeoTIFF in the renderer, then ask about water. The segmentation model is used first.',
}

function readHistory(): FusionHistory[] {
  try {
    const value = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]') as FusionHistory[]
    return Array.isArray(value) ? value : []
  } catch { return [] }
}

function withoutAttachments(messages: ChatMessageData[]): ChatMessageData[] {
  return messages.map(({ attachment: _attachment, attachments: _attachments, ...message }) => message)
}

function UploadSlot({ label, hint, slot, busy, onFile, isSar = false, showSarPreview = true, onToggleSarPreview }: {
  label: string; hint: string; slot: SceneSlot; busy: boolean; onFile: (file: File) => void
  isSar?: boolean; showSarPreview?: boolean; onToggleSarPreview?: () => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const showPreview = slot.previewUrl && (!isSar || showSarPreview)
  return <div className="flex min-w-0 flex-1 flex-col gap-3 rounded-lg border border-dashed border-border bg-bg p-4">
    <div className="flex items-center justify-between gap-3"><div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-wide text-ink">{label}</p><p className="mt-1 text-xs text-muted">{hint}</p></div><Button variant="secondary" className="shrink-0 text-xs" disabled={busy} onClick={() => inputRef.current?.click()}>Choose file</Button></div>
    <input ref={inputRef} type="file" accept=".tif,.tiff,.png,.jpg,.jpeg,image/tiff,image/png,image/jpeg" className="sr-only" onChange={(event) => { const file = event.target.files?.[0]; if (file) onFile(file); event.target.value = '' }} />
    <div className="flex h-44 items-center justify-center overflow-hidden rounded-md border border-border bg-surface">
      {showPreview ? <button type="button" className="h-full w-full" onClick={isSar ? onToggleSarPreview : undefined} title={isSar ? 'Show GeoTIFF details' : undefined}><img src={slot.previewUrl!} alt={`${label} preview`} className="h-full w-full object-contain" /></button>
        : slot.file && isSar ? <button type="button" className="h-full w-full px-4 text-center text-sm text-muted hover:bg-bg" onClick={onToggleSarPreview}><span className="block font-medium text-ink">SAR GeoTIFF selected</span><span className="mt-1 block text-xs">Click to reveal its rendered PNG preview</span></button>
          : <p className="px-4 text-center text-xs text-muted">Preview appears here</p>}
    </div>
    <div className="flex items-center justify-between gap-2 text-[11px] text-muted"><span className="truncate">{slot.file?.name ?? 'No file selected'}</span>{slot.metadata ? <span className="shrink-0">{slot.metadata.width} × {slot.metadata.height}</span> : null}</div>
    {isSar && slot.previewUrl ? <Button variant="secondary" className="self-start text-xs" onClick={onToggleSarPreview}>{showSarPreview ? 'Show GeoTIFF details' : 'View rendered SAR PNG'}</Button> : null}
  </div>
}

function FusionRenderer({ optical, sar, overlayUrl, busySlot, busy, showSarPreview, view, onViewChange, onOpticalFile, onSarFile, onToggleSarPreview }: {
  optical: SceneSlot; sar: SceneSlot; overlayUrl: string | null; busySlot: SlotKey | null; busy: boolean; showSarPreview: boolean; view: View
  onViewChange: (view: View) => void; onOpticalFile: (file: File) => void; onSarFile: (file: File) => void; onToggleSarPreview: () => void
}) {
  const imageUrl = view === 'overlay' ? overlayUrl : view === 'sar' ? sar.previewUrl : optical.previewUrl
  const title = view === 'overlay' ? 'Water segmentation mask' : view === 'sar' ? 'Rendered Sentinel-1 preview' : 'Sentinel-2 preview'
  return <div className="flex h-full min-h-0 flex-col bg-surface">
    <header className="flex flex-wrap items-center gap-2 border-b border-border bg-bg px-4 py-3"><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-ink">OPTICAL_SAR // WATER_SEGMENTATION</p><p className="text-[11px] text-muted">Model-first fusion workspace</p></div><div className="flex rounded-md border border-border bg-surface p-0.5 text-xs">{(['optical', 'sar', 'overlay'] as const).map((item) => <button key={item} type="button" onClick={() => onViewChange(item)} className={`rounded px-2 py-1 capitalize ${view === item ? 'bg-accent text-white dark:text-navy' : 'text-muted hover:text-ink'}`}>{item}</button>)}</div></header>
    <div className="min-h-0 flex-1 overflow-y-auto p-4"><div className="grid gap-3 sm:grid-cols-2"><UploadSlot label="Optical image" hint="S2: B02, B03, B04, B08, B11, B12" slot={optical} busy={busy || busySlot === 'optical'} onFile={onOpticalFile} /><UploadSlot label="SAR image" hint="S1: VV and VH GeoTIFF" slot={sar} busy={busy || busySlot === 'sar'} onFile={onSarFile} isSar showSarPreview={showSarPreview} onToggleSarPreview={onToggleSarPreview} /></div>
      <div className="mt-4 overflow-hidden rounded-lg border border-border bg-bg"><div className="flex items-center justify-between border-b border-border px-3 py-2"><div><p className="text-xs font-semibold text-ink">{title}</p><p className="text-[11px] text-muted">Blue: model water · Light blue: near-threshold model probability · Red: secondary built-up cue · Yellow: overlap.</p></div>{view === 'overlay' && overlayUrl ? <a className="text-xs text-accent" href={overlayUrl} download="water-mask.png">Download</a> : null}</div><div className="flex h-72 items-center justify-center bg-black/5 p-3 dark:bg-black/30">{imageUrl ? <img src={imageUrl} alt={title} className="h-full w-full object-contain" /> : <p className="text-sm text-muted">Upload both inputs and send a message to produce a water mask.</p>}</div></div>
    </div>
  </div>
}

function CloudSceneWorkspace() {
  const [optical, setOptical] = useState<SceneSlot>(EMPTY_SLOT)
  const [sar, setSar] = useState<SceneSlot>(EMPTY_SLOT)
  const [messages, setMessages] = useState<ChatMessageData[]>([WELCOME])
  const [draft, setDraft] = useState('Identify water regions using both images.')
  const [mode, setMode] = useState<WorkspaceMode>('split')
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [overlayUrl, setOverlayUrl] = useState<string | null>(null)
  const [activeAttachmentId, setActiveAttachmentId] = useState<string | null>(null)
  const [view, setView] = useState<View>('optical')
  const [busySlot, setBusySlot] = useState<SlotKey | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const locale = useSpokenLocale(setError)
  const [showSarPreview, setShowSarPreview] = useState(false)
  const [fusionContext, setFusionContext] = useState<FusionContext | null>(null)
  const [history, setHistory] = useState<FusionHistory[]>(readHistory)
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  useEffect(() => () => { if (optical.previewUrl) URL.revokeObjectURL(optical.previewUrl); if (sar.previewUrl) URL.revokeObjectURL(sar.previewUrl); if (overlayUrl) URL.revokeObjectURL(overlayUrl) }, [optical.previewUrl, sar.previewUrl, overlayUrl])

  useEffect(() => {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history)) } catch { /* storage is optional */ }
  }, [history])

  useEffect(() => {
    if (!activeHistoryId) return
    setHistory((previous) => previous.map((item) => item.id === activeHistoryId ? {
      ...item,
      title: messages.find((message) => message.role === 'user')?.text.slice(0, 80) || 'Optical + SAR chat',
      messages: withoutAttachments(messages),
      context: fusionContext,
      updatedAt: new Date().toISOString(),
    } : item))
  }, [activeHistoryId, fusionContext, messages])

  function ensureHistory() {
    if (activeHistoryId) return
    const id = crypto.randomUUID()
    setActiveHistoryId(id)
    setHistory((previous) => [{ id, title: 'Optical + SAR chat', messages: [WELCOME], context: null, updatedAt: new Date().toISOString() }, ...previous])
  }

  function newChat() {
    setActiveHistoryId(null)
    setMessages([WELCOME])
    setFusionContext(null)
    setOverlayUrl(null)
    setActiveAttachmentId(null)
    setError(null)
  }

  function selectHistory(id: string) {
    const item = history.find((entry) => entry.id === id)
    if (!item) return
    setActiveHistoryId(item.id)
    setMessages(item.messages.length ? item.messages : [WELCOME])
    setFusionContext(item.context)
    setOverlayUrl(null)
    setActiveAttachmentId(null)
    setView('optical')
  }

  function deleteHistory(id: string) {
    setHistory((previous) => previous.filter((entry) => entry.id !== id))
    if (activeHistoryId === id) newChat()
  }

  async function chooseFile(kind: SlotKey, file: File) {
    setBusySlot(kind); setError(null); setFusionContext(null)
    try {
      const preview = await postPreview(file)
      const nextSlot = { file, previewUrl: previewToObjectUrl(preview.preview_png_base64), metadata: preview.metadata }
      if (kind === 'optical') { setOptical(nextSlot); setView('optical') } else { setSar(nextSlot); setShowSarPreview(false); setView('sar') }
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not preview image') } finally { setBusySlot(null) }
  }

  async function send() {
    const question = draft.trim() || 'Identify water regions using both images.'
    const opticalFile = optical.file
    const sarFile = sar.file
    if (!fusionContext && (!opticalFile || !sarFile)) { setError('Upload both the optical and SAR GeoTIFFs in the renderer first.'); return }
    ensureHistory()
    setMessages((previous) => [...previous.filter((message) => message.id !== 'welcome'), { id: `user-${Date.now()}`, role: 'user', text: question }])
    setDraft(''); setAnalyzing(true); setError(null)
    locale.primeAudio()
    try {
      const questionEn = await locale.toEnglish(question)
      if (fusionContext) {
        const followUp = await postFusionFollowUp(questionEn, fusionContext.summary, fusionContext.evidence)
        const body = await locale.fromEnglish(followUp.text)
        const reply = `**Gemini follow-up**\n\n${body}`
        setMessages((previous) => [...previous, { id: `assistant-${Date.now()}`, role: 'assistant', text: reply, speakLanguage: locale.language }])
        locale.say(reply, locale.language)
        return
      }
      const result = await postFusion(opticalFile!, sarFile!, questionEn)
      if (overlayUrl) URL.revokeObjectURL(overlayUrl)
      const nextOverlayUrl = result.overlay_png_base64 ? previewToObjectUrl(result.overlay_png_base64) : null
      setOverlayUrl(nextOverlayUrl); setView(nextOverlayUrl ? 'overlay' : 'optical')
      const segmentation = result.evidence.water_segmentation as { available?: boolean; confidence?: number } | undefined
      const modelUsed = segmentation?.available === true
      const waterPct = typeof result.evidence.water_pct === 'number' ? result.evidence.water_pct.toFixed(1) : 'unavailable'
      const confidence = typeof segmentation?.confidence === 'number' ? segmentation.confidence.toFixed(2) : result.score?.toFixed(2) ?? 'unavailable'
      const body = await locale.fromEnglish(result.text)
      const reply = modelUsed ? `**OpticalSarFusionSegmenter** (primary water model)\n\n${body}\n\n**Water coverage:** ${waterPct}%  |  **Confidence:** ${confidence}` : `**Optical/SAR heuristic fallback**\n\n${body}\n\n**Water-like coverage:** ${waterPct}%  |  **Confidence:** ${confidence}`
      setFusionContext({ summary: result.text, evidence: result.evidence })
      const attachmentId = nextOverlayUrl ? `water-mask-${Date.now()}` : undefined
      if (attachmentId) setActiveAttachmentId(attachmentId)
      setMessages((previous) => [...previous, { id: `assistant-${Date.now()}`, role: 'assistant', text: reply, speakLanguage: locale.language, confidence: result.score ?? undefined, ...(nextOverlayUrl && attachmentId ? { attachment: { id: attachmentId, url: nextOverlayUrl, filename: 'water-segmentation-mask.png' } } : {}) }])
      locale.say(reply, locale.language)
    } catch (err) { setDraft(question); setError(err instanceof Error ? err.message : 'Fusion failed') } finally { setAnalyzing(false) }
  }

  const historySessions: SessionListItem[] = [...history]
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
    .map((item) => ({ id: item.id, title: item.title, job_type: 'optical_sar', created_at: item.updatedAt, updated_at: item.updatedAt }))

  return <div className="flex h-screen flex-col bg-[#030712] text-slate-100"><Navbar />
    <div className="flex items-center justify-between border-b border-slate-800 bg-[#080E1A] px-4 py-2 text-xs font-mono text-slate-300"><span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-cyan-300">TASK: OPTICAL_SAR_WATER</span><span className="text-slate-400">MODEL: <span className="text-emerald-400">OpticalSarFusionSegmenter</span></span></div>
    {error ? <p className="mx-4 mt-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p> : null}
    <div className="flex min-h-0 flex-1"><SessionSidebar sessions={historySessions} activeSessionId={activeHistoryId} collapsed={sidebarCollapsed} onCollapsedChange={setSidebarCollapsed} onNewChat={newChat} onSelect={selectHistory} onDelete={deleteHistory} busy={analyzing || busySlot !== null} />
      <div className="min-h-0 min-w-0 flex-1"><SplitWorkspace mode={mode} onModeChange={setMode} rightPanelOpen={rightPanelOpen} onRightPanelToggle={() => setRightPanelOpen((open) => !open)}
      chat={<ChatPanel messages={messages} draft={draft} onDraftChange={setDraft} onSend={() => void send()} stagedFile={null} stagedPreviewUrl={null} onStageFile={() => undefined} onClearStaged={() => undefined} activeAttachmentId={activeAttachmentId} onSelectAttachment={(id) => { setActiveAttachmentId((active) => active === id ? null : id); setView('overlay') }} busy={analyzing || busySlot !== null} analysisLoading={analyzing} title="Ask optical + SAR" subtitle={optical.file && sar.file ? 'Both inputs loaded — every message runs the water model' : 'Upload the two GeoTIFFs in the renderer first'} allowAttachments={false} headerExtra={locale.languageButtons} enableVoice voiceLanguage={locale.voiceProps.voiceLanguage} onVoiceText={setDraft} onVoiceError={setError} transcribe={locale.voiceProps.transcribe} onPlay={locale.voiceProps.onPlay} />}
      renderer={<FusionRenderer optical={optical} sar={sar} overlayUrl={overlayUrl} busySlot={busySlot} busy={analyzing} showSarPreview={showSarPreview} view={view} onViewChange={setView} onOpticalFile={(file) => void chooseFile('optical', file)} onSarFile={(file) => void chooseFile('sar', file)} onToggleSarPreview={() => setShowSarPreview((visible) => !visible)} />}
      /></div>
    </div>
  </div>
}

export function CloudScenePage() {
  return <><SignedOut><Navigate to={ROUTES.signIn} replace /></SignedOut><SignedIn><CloudSceneWorkspace /></SignedIn></>
}
