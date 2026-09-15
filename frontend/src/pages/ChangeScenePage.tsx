import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { SignedIn, SignedOut, useAuth } from '@clerk/clerk-react'
import { Navbar } from '../components/Navbar'
import { BeforeAfterRenderer } from '../components/workspace/BeforeAfterRenderer'
import { ChatPanel } from '../components/workspace/ChatPanel'
import type { ChatMessageData } from '../components/workspace/ChatMessage'
import { SessionSidebar } from '../components/workspace/SessionSidebar'
import { SplitWorkspace } from '../components/workspace/SplitWorkspace'
import type { WorkspaceMode } from '../components/workspace/splitState'
import {
  createSession, deleteSession, downloadReport, generateAnalysisReport,
  getMessages, getSession, listSessions, postChange, postPreview,
  previewToObjectUrl, sendSessionMessage, uploadSessionAsset,
  type MessageOut, type SessionListItem,
} from '../lib/api'
import { CHANGE_JOB, filterChangeSessions } from '../lib/sessionJob'
import { ROUTES } from '../routes'

const DEMO_BEFORE = '/landing/change-before.png'
const DEMO_AFTER = '/landing/change-after.png'
const ACTIVE_SESSION_KEY = 'satquery.changeActiveSessionId'
const SIDEBAR_KEY = 'satquery.changeSidebarCollapsed'
const DEFAULT_PROMPT = 'Compare these scenes and describe the major changes.'

const WELCOME: ChatMessageData = {
  id: 'welcome', role: 'assistant',
  text: 'Upload a **Before** and **After** image under the renderer, then ask what changed.',
}

function messageToUi(message: MessageOut): ChatMessageData {
  const result: ChatMessageData = { id: message.id, role: message.role === 'user' ? 'user' : 'assistant', text: message.content }
  if (message.attachment?.preview_png_base64) {
    result.attachment = { id: message.attachment.id, filename: message.attachment.filename, url: previewToObjectUrl(message.attachment.preview_png_base64) }
  }
  return result
}

function readCollapsed(): boolean {
  try { return localStorage.getItem(SIDEBAR_KEY) === '1' } catch { return false }
}

export function ChangeScenePage() {
  return <><SignedOut><Navigate to={ROUTES.signIn} replace /></SignedOut><SignedIn><ChangeSceneWorkspace /></SignedIn></>
}

function ChangeSceneWorkspace() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const tokenRef = useRef(getToken)
  tokenRef.current = getToken
  const tokenFn = useCallback(async () => tokenRef.current(), [])

  const [mode, setMode] = useState<WorkspaceMode>('split')
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessageData[]>([WELCOME])
  const [draft, setDraft] = useState('')
  const [zoom, setZoom] = useState(1)
  const [busy, setBusy] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [booting, setBooting] = useState(true)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readCollapsed)

  const [beforeUrl, setBeforeUrl] = useState(DEMO_BEFORE)
  const [afterUrl, setAfterUrl] = useState(DEMO_AFTER)
  const [beforeFilename, setBeforeFilename] = useState<string | null>('change-before.png (demo)')
  const [afterFilename, setAfterFilename] = useState<string | null>('change-after.png (demo)')
  const [beforeBlob, setBeforeBlob] = useState(false)
  const [afterBlob, setAfterBlob] = useState(false)
  const [beforeFile, setBeforeFile] = useState<File | null>(null)
  const [afterFile, setAfterFile] = useState<File | null>(null)
  const [beforeAssetId, setBeforeAssetId] = useState<string | null>(null)
  const [afterAssetId, setAfterAssetId] = useState<string | null>(null)
  const [overlay, setOverlay] = useState<{ id: string; url: string } | null>(null)
  const [activeAttachmentId, setActiveAttachmentId] = useState<string | null>(null)
  const [modelRan, setModelRan] = useState(false)
  const [changeContext, setChangeContext] = useState<string | null>(null)
  const [analysisId, setAnalysisId] = useState<string | null>(null)

  const beforeUrlRef = useRef(beforeUrl)
  const afterUrlRef = useRef(afterUrl)
  const beforeBlobRef = useRef(beforeBlob)
  const afterBlobRef = useRef(afterBlob)
  beforeUrlRef.current = beforeUrl; afterUrlRef.current = afterUrl
  beforeBlobRef.current = beforeBlob; afterBlobRef.current = afterBlob

  const clearOverlay = useCallback(() => {
    setOverlay((current) => { if (current) URL.revokeObjectURL(current.url); return null })
    setActiveAttachmentId(null)
  }, [])

  useEffect(() => () => {
    if (beforeBlobRef.current) URL.revokeObjectURL(beforeUrlRef.current)
    if (afterBlobRef.current) URL.revokeObjectURL(afterUrlRef.current)
  }, [])

  const selectSession = useCallback((id: string) => {
    setSessionId(id)
    try { localStorage.setItem(ACTIVE_SESSION_KEY, id) } catch { /* optional */ }
  }, [])

  const setCollapsed = useCallback((collapsed: boolean) => {
    setSidebarCollapsed(collapsed)
    try { localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0') } catch { /* optional */ }
  }, [])

  const refreshSessions = useCallback(async () => {
    const rows = filterChangeSessions(await listSessions(tokenFn))
    setSessions(rows)
    return rows
  }, [tokenFn])

  const resetDemoPair = useCallback(() => {
    if (beforeBlobRef.current) URL.revokeObjectURL(beforeUrlRef.current)
    if (afterBlobRef.current) URL.revokeObjectURL(afterUrlRef.current)
    setBeforeUrl(DEMO_BEFORE); setAfterUrl(DEMO_AFTER)
    setBeforeFilename('change-before.png (demo)'); setAfterFilename('change-after.png (demo)')
    setBeforeBlob(false); setAfterBlob(false)
  }, [])

  const loadSession = useCallback(async (id: string) => {
    setBusy(true); setError(null); setAnalysisLoading(false)
    try {
      const [detail, thread] = await Promise.all([getSession(tokenFn, id), getMessages(tokenFn, id)])
      selectSession(id)
      setDraft(''); setZoom(1); setBeforeFile(null); setAfterFile(null)
      setBeforeAssetId(null); setAfterAssetId(null); setModelRan(false); setChangeContext(null); setAnalysisId(null); clearOverlay()
      if (beforeBlobRef.current) URL.revokeObjectURL(beforeUrlRef.current)
      if (afterBlobRef.current) URL.revokeObjectURL(afterUrlRef.current)
      const assets = detail.assets.filter((asset) => asset.preview_png_base64)
      if (assets.length >= 2) {
        const [before, after] = assets
        setBeforeUrl(previewToObjectUrl(before.preview_png_base64!)); setAfterUrl(previewToObjectUrl(after.preview_png_base64!))
        setBeforeFilename(before.filename); setAfterFilename(after.filename)
        setBeforeBlob(true); setAfterBlob(true); setBeforeAssetId(before.id); setAfterAssetId(after.id)
      } else {
        resetDemoPair()
      }
      setMessages(thread.length ? thread.map(messageToUi) : [WELCOME])
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed to load chat') } finally { setBusy(false) }
  }, [clearOverlay, resetDemoPair, selectSession, tokenFn])

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    let cancelled = false
    void (async () => {
      try {
        const rows = await refreshSessions()
        if (cancelled) return
        if (!rows.length) {
          const created = await createSession(tokenFn, 'Before vs after', CHANGE_JOB)
          if (!cancelled) { setSessions([created]); selectSession(created.id); setMessages([WELCOME]) }
          return
        }
        let preferred: string | null = null
        try { preferred = localStorage.getItem(ACTIVE_SESSION_KEY) } catch { /* optional */ }
        const chosen = preferred && rows.some((row) => row.id === preferred) ? preferred : rows[0].id
        if (!cancelled) await loadSession(chosen)
      } catch (err) { if (!cancelled) setError(err instanceof Error ? err.message : 'Could not start change detection') } finally { if (!cancelled) setBooting(false) }
    })()
    return () => { cancelled = true }
  }, [isLoaded, isSignedIn, loadSession, refreshSessions, selectSession, tokenFn])

  async function newChat() {
    setBusy(true); setError(null)
    try {
      const created = await createSession(tokenFn, 'Before vs after', CHANGE_JOB)
      setSessions((current) => [created, ...current]); selectSession(created.id)
      setMessages([WELCOME]); setDraft(''); setZoom(1); setBeforeFile(null); setAfterFile(null)
      setBeforeAssetId(null); setAfterAssetId(null); setModelRan(false); setChangeContext(null); setAnalysisId(null); clearOverlay(); resetDemoPair()
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not create chat') } finally { setBusy(false) }
  }

  async function removeChat(id: string) {
    setBusy(true); setError(null)
    try {
      await deleteSession(tokenFn, id)
      const rows = await refreshSessions()
      if (sessionId === id) {
        try { localStorage.removeItem(ACTIVE_SESSION_KEY) } catch { /* optional */ }
        if (rows.length) await loadSession(rows[0].id)
        else await newChat()
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not delete chat') } finally { setBusy(false) }
  }

  async function upload(side: 'before' | 'after', file: File) {
    if (!sessionId) return
    setUploadBusy(true); setError(null); clearOverlay(); setModelRan(false); setChangeContext(null); setAnalysisId(null)
    try {
      const preview = await postPreview(file)
      const url = previewToObjectUrl(preview.preview_png_base64)
      if (side === 'before') {
        if (beforeBlobRef.current) URL.revokeObjectURL(beforeUrlRef.current)
        setBeforeUrl(url); setBeforeFilename(file.name); setBeforeBlob(true); setBeforeFile(file)
      } else {
        if (afterBlobRef.current) URL.revokeObjectURL(afterUrlRef.current)
        setAfterUrl(url); setAfterFilename(file.name); setAfterBlob(true); setAfterFile(file)
      }
      const saved = await uploadSessionAsset(tokenFn, sessionId, file)
      if (side === 'before') setBeforeAssetId(saved.asset.id)
      else setAfterAssetId(saved.asset.id)
      await refreshSessions()
    } catch (err) { setError(err instanceof Error ? err.message : 'Upload failed') } finally { setUploadBusy(false) }
  }

  async function analyze(question: string) {
    if (!sessionId || !beforeFile || !afterFile || busy) return
    setBusy(true); setAnalysisLoading(true); setError(null); setDraft('')
    try {
      setMessages((current) => [...current.filter((message) => message.id !== 'welcome'), { id: `user-${Date.now()}`, role: 'user', text: question }])
      const result = await postChange(tokenFn, beforeFile, afterFile, sessionId, question, beforeAssetId ?? undefined, afterAssetId ?? undefined)
      const evidence = result.evidence as Record<string, unknown>
      const method = typeof evidence.method === 'string' ? evidence.method : undefined
      const fallback = (evidence.metadata as Record<string, unknown> | undefined)?.fallback === true
      const tag = fallback ? '**Pixel-difference fallback**' : '**SiameseChangeDetector**'
      const changePct = result.change_pct == null ? 'unavailable' : `${result.change_pct.toFixed(1)}%`
      const score = result.score == null ? 'unavailable' : result.score.toFixed(3)
      const text = `${tag}\n\n${result.text}\n\n**Changed area:** ${changePct}  |  **Score:** ${score}${method ? `  |  **Method:** ${method}` : ''}`
      const url = result.overlay_png_base64 ? previewToObjectUrl(result.overlay_png_base64) : null
      const id = url ? `change-overlay-${Date.now()}` : undefined
      if (url && id) { clearOverlay(); setOverlay({ id, url }); setActiveAttachmentId(id) }
      setModelRan(true); setChangeContext(result.text); setAnalysisId(result.analysis_id)
      setMessages((current) => [...current, { id: `assistant-${Date.now()}`, role: 'assistant', text, ...(url && id ? { attachment: { id, url, filename: 'change-overlay.png' } } : {}) }])
      await refreshSessions()
    } catch (err) { setDraft(question); setError(err instanceof Error ? err.message : 'Change detection failed') } finally { setAnalysisLoading(false); setBusy(false) }
  }

  async function send() {
    const question = draft.trim()
    if (!question || !sessionId || busy) return
    if (beforeFile && afterFile && !modelRan) { await analyze(question); return }
    setBusy(true); setError(null); setDraft('')
    try {
      const contextualQuestion = changeContext ? `[Change detection result: ${changeContext}]\n\nUser question: ${question}` : question
      const response = await sendSessionMessage(tokenFn, sessionId, contextualQuestion)
      setMessages((current) => [...current.filter((message) => message.id !== 'welcome'), { id: response.user_message.id, role: 'user', text: question }, { id: response.assistant_message.id, role: 'assistant', text: response.assistant_message.content }])
      await refreshSessions()
    } catch (err) { setDraft(question); setError(err instanceof Error ? err.message : 'Send failed') } finally { setBusy(false) }
  }

  async function exportReport() {
    if (!sessionId || !analysisId || exporting) return
    setExporting(true); setError(null)
    try {
      const report = await generateAnalysisReport(tokenFn, sessionId, analysisId)
      const file = await downloadReport(tokenFn, sessionId, report.id)
      const url = URL.createObjectURL(file)
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'satquery-change-report.pdf'; anchor.click(); URL.revokeObjectURL(url)
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not export report') } finally { setExporting(false) }
  }

  const scenesReady = Boolean(beforeFile && afterFile)
  return <div className="flex h-screen flex-col bg-[#030712] text-slate-100"><Navbar />
    <div className="flex items-center justify-between border-b border-slate-800 bg-[#080E1A] px-4 py-2 text-xs font-mono text-slate-300"><span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-400">TASK: CHANGE_DETECTION</span><span className="text-slate-400">TOOL: <span className="text-emerald-400">bi-temporal-change-mask</span></span></div>
    {error ? <p className="mx-4 mt-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p> : null}
    <div className="flex min-h-0 flex-1"><SessionSidebar sessions={sessions} activeSessionId={sessionId} collapsed={sidebarCollapsed} onCollapsedChange={setCollapsed} onNewChat={() => void newChat()} onSelect={(id) => void loadSession(id)} onDelete={(id) => void removeChat(id)} busy={busy || uploadBusy || booting} />
      <div className="min-h-0 min-w-0 flex-1"><SplitWorkspace mode={mode} onModeChange={setMode} rightPanelOpen={rightPanelOpen} onRightPanelToggle={() => setRightPanelOpen((value) => !value)}
        chat={<div className="flex h-full min-h-0 flex-col bg-[#060D1A]"><ChatPanel messages={messages} draft={draft} onDraftChange={setDraft} onSend={() => void send()} stagedFile={null} stagedPreviewUrl={null} onStageFile={() => undefined} onClearStaged={() => undefined} activeAttachmentId={activeAttachmentId} onSelectAttachment={(id) => { if (overlay?.id === id) setActiveAttachmentId((active) => active === id ? null : id) }} busy={busy || booting} analysisLoading={analysisLoading} analysisAction={scenesReady && !modelRan ? <div className="flex items-center justify-between gap-3 rounded-xl border border-accent/20 bg-accent/5 px-3 py-2"><div><p className="text-xs font-medium text-ink">Both scenes ready</p><p className="text-[10px] text-muted">{beforeFilename} → {afterFilename}</p></div><button type="button" disabled={busy} onClick={() => void analyze(DEFAULT_PROMPT)} className="rounded-lg bg-accent px-3 py-1.5 text-[11px] font-semibold text-navy disabled:opacity-50">Analyze changes</button></div> : null} title="Before vs after" subtitle={scenesReady ? (modelRan ? 'Ask Gemini about the detected changes' : 'Both images loaded — analyze the changes') : 'Upload both dates under the renderer, then ask'} allowAttachments={false} />
          {analysisId ? <div className="border-t border-border bg-surface px-4 py-2 text-right"><button type="button" disabled={exporting} onClick={() => void exportReport()} className="rounded-lg border border-accent/30 bg-accent/10 px-3 py-1.5 text-[11px] font-semibold text-accent disabled:opacity-50">{exporting ? 'Exporting report…' : 'Export report'}</button></div> : null}
        </div>}
        renderer={<BeforeAfterRenderer beforeUrl={beforeUrl} afterUrl={afterUrl} changeOverlayUrl={overlay?.url ?? null} beforeFilename={beforeFilename} afterFilename={afterFilename} title="SCENE_DELTA // T1 vs T2" subtitle="Dual-slot co-registered frame analysis" legendLabel={overlay ? 'Detected changes' : null} zoom={zoom} onZoomChange={setZoom} onExpand={() => setMode('renderer')} onCloseToSplit={() => setMode('split')} expanded={mode === 'renderer'} onUploadBefore={(file) => void upload('before', file)} onUploadAfter={(file) => void upload('after', file)} uploadBusy={uploadBusy || booting} />}
      /></div>
    </div>
  </div>
}
