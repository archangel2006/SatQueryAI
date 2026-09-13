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
  createSession,
  deleteSession,
  getMessages,
  getSession,
  listSessions,
  postChange,
  postPreview,
  previewToObjectUrl,
  sendSessionMessage,
  uploadSessionAsset,
  type MessageOut,
  type SessionListItem,
} from '../lib/api'
import { CHANGE_JOB, filterChangeSessions } from '../lib/sessionJob'
import { ROUTES } from '../routes'

const DEMO_BEFORE = '/landing/change-before.png'
const DEMO_AFTER = '/landing/change-after.png'
const JOB_TYPE = CHANGE_JOB
const ACTIVE_SESSION_KEY = 'satquery.changeActiveSessionId'
const SIDEBAR_KEY = 'satquery.changeSidebarCollapsed'

const WELCOME: ChatMessageData = {
  id: 'welcome',
  role: 'assistant',
  text: 'Upload a **Before** and **After** image under the renderer (or use the demo pair), then ask what changed.',
}

function messageToUi(msg: MessageOut): ChatMessageData {
  const data: ChatMessageData = {
    id: msg.id,
    role: msg.role === 'user' ? 'user' : 'assistant',
    text: msg.content,
  }
  if (msg.attachment?.preview_png_base64) {
    data.attachment = {
      id: msg.attachment.id,
      url: previewToObjectUrl(msg.attachment.preview_png_base64),
      filename: msg.attachment.filename,
    }
  }
  return data
}

function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === '1'
  } catch {
    return false
  }
}

function resetDemoPair(
  setBeforeUrl: (v: string) => void,
  setAfterUrl: (v: string) => void,
  setBeforeFilename: (v: string | null) => void,
  setAfterFilename: (v: string | null) => void,
  setBeforeBlob: (v: boolean) => void,
  setAfterBlob: (v: boolean) => void,
  beforeBlob: boolean,
  afterBlob: boolean,
  beforeUrl: string,
  afterUrl: string,
) {
  if (beforeBlob) URL.revokeObjectURL(beforeUrl)
  if (afterBlob) URL.revokeObjectURL(afterUrl)
  setBeforeUrl(DEMO_BEFORE)
  setAfterUrl(DEMO_AFTER)
  setBeforeFilename('change-before.png (demo)')
  setAfterFilename('change-after.png (demo)')
  setBeforeBlob(false)
  setAfterBlob(false)
}

export function ChangeScenePage() {
  return (
    <>
      <SignedOut>
        <Navigate to={ROUTES.signIn} replace />
      </SignedOut>
      <SignedIn>
        <ChangeSceneWorkspace />
      </SignedIn>
    </>
  )
}

function ChangeSceneWorkspace() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const getTokenRef = useRef(getToken)
  getTokenRef.current = getToken
  const tokenFn = useCallback(async () => getTokenRef.current(), [])

  const [mode, setMode] = useState<WorkspaceMode>('split')
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessageData[]>([WELCOME])
  const [draft, setDraft] = useState('')
  const [zoom, setZoom] = useState(1)
  const [busy, setBusy] = useState(false)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [booting, setBooting] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarCollapsed)

  const [beforeUrl, setBeforeUrl] = useState(DEMO_BEFORE)
  const [afterUrl, setAfterUrl] = useState(DEMO_AFTER)
  const [beforeFilename, setBeforeFilename] = useState<string | null>(
    'change-before.png (demo)',
  )
  const [afterFilename, setAfterFilename] = useState<string | null>(
    'change-after.png (demo)',
  )
  const [beforeBlob, setBeforeBlob] = useState(false)
  const [afterBlob, setAfterBlob] = useState(false)

  // Raw File objects kept so we can POST them to /change
  const [beforeFile, setBeforeFile] = useState<File | null>(null)
  const [afterFile, setAfterFile] = useState<File | null>(null)

  // Overlay attachment: { id, url } when model result is shown in renderer
  const [overlayAttachment, setOverlayAttachment] = useState<{ id: string; url: string } | null>(null)
  const [activeAttachmentId, setActiveAttachmentId] = useState<string | null>(null)

  const beforeUrlRef = useRef(beforeUrl)
  const afterUrlRef = useRef(afterUrl)
  beforeUrlRef.current = beforeUrl
  afterUrlRef.current = afterUrl

  useEffect(() => {
    return () => {
      if (beforeBlob) URL.revokeObjectURL(beforeUrlRef.current)
      if (afterBlob) URL.revokeObjectURL(afterUrlRef.current)
    }
  }, [beforeBlob, afterBlob])

  const selectSessionId = useCallback((id: string) => {
    setSessionId(id)
    try {
      localStorage.setItem(ACTIVE_SESSION_KEY, id)
    } catch {
      /* ignore */
    }
  }, [])

  const setCollapsed = useCallback((collapsed: boolean) => {
    setSidebarCollapsed(collapsed)
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0')
    } catch {
      /* ignore */
    }
  }, [])

  const refreshSessions = useCallback(async () => {
    const rows = filterChangeSessions(await listSessions(tokenFn))
    setSessions(rows)
    return rows
  }, [tokenFn])

  const applyDemoPair = useCallback(() => {
    resetDemoPair(
      setBeforeUrl,
      setAfterUrl,
      setBeforeFilename,
      setAfterFilename,
      setBeforeBlob,
      setAfterBlob,
      beforeBlob,
      afterBlob,
      beforeUrl,
      afterUrl,
    )
  }, [afterBlob, afterUrl, beforeBlob, beforeUrl])

  const loadSession = useCallback(
    async (id: string) => {
      setBusy(true)
      setError(null)
      try {
        const [detail, thread] = await Promise.all([
          getSession(tokenFn, id),
          getMessages(tokenFn, id),
        ])
        selectSessionId(id)
        setDraft('')
        setZoom(1)

        const withPreview = detail.assets.filter((a) => a.preview_png_base64)
        if (beforeBlob) URL.revokeObjectURL(beforeUrlRef.current)
        if (afterBlob) URL.revokeObjectURL(afterUrlRef.current)

        if (withPreview.length >= 2) {
          const b = withPreview[0]
          const a = withPreview[1]
          setBeforeUrl(previewToObjectUrl(b.preview_png_base64!))
          setAfterUrl(previewToObjectUrl(a.preview_png_base64!))
          setBeforeFilename(b.filename)
          setAfterFilename(a.filename)
          setBeforeBlob(true)
          setAfterBlob(true)
        } else if (withPreview.length === 1) {
          const only = withPreview[0]
          const url = previewToObjectUrl(only.preview_png_base64!)
          setBeforeUrl(url)
          setBeforeFilename(only.filename)
          setBeforeBlob(true)
          setAfterUrl(DEMO_AFTER)
          setAfterFilename('change-after.png (demo)')
          setAfterBlob(false)
        } else {
          setBeforeUrl(DEMO_BEFORE)
          setAfterUrl(DEMO_AFTER)
          setBeforeFilename('change-before.png (demo)')
          setAfterFilename('change-after.png (demo)')
          setBeforeBlob(false)
          setAfterBlob(false)
        }

        setMessages(
          thread.length === 0 ? [WELCOME] : thread.map((m) => messageToUi(m)),
        )
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load chat')
      } finally {
        setBusy(false)
      }
    },
    [afterBlob, beforeBlob, selectSessionId, tokenFn],
  )

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    let cancelled = false
    ;(async () => {
      try {
        const rows = filterChangeSessions(await listSessions(tokenFn))
        if (cancelled) return
        setSessions(rows)
        if (rows.length === 0) {
          const created = await createSession(
            tokenFn,
            'Before vs after',
            JOB_TYPE,
          )
          if (cancelled) return
          setSessions([created])
          selectSessionId(created.id)
          setMessages([WELCOME])
          return
        }
        let preferred: string | null = null
        try {
          preferred = localStorage.getItem(ACTIVE_SESSION_KEY)
        } catch {
          preferred = null
        }
        const match = preferred && rows.some((r) => r.id === preferred)
        const id = match && preferred ? preferred : rows[0].id
        if (cancelled) return
        await loadSession(id)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Could not start chat')
        }
      } finally {
        if (!cancelled) setBooting(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot boot
  }, [isLoaded, isSignedIn])

  async function handleNewChat() {
    setBusy(true)
    setError(null)
    try {
      const created = await createSession(tokenFn, 'Before vs after', JOB_TYPE)
      setSessions((prev) => [created, ...prev])
      selectSessionId(created.id)
      setMessages([WELCOME])
      setDraft('')
      setZoom(1)
      setBeforeFile(null)
      setAfterFile(null)
      setOverlayAttachment(null)
      setActiveAttachmentId(null)
      applyDemoPair()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create chat')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(id: string) {
    setBusy(true)
    setError(null)
    try {
      await deleteSession(tokenFn, id)
      if (sessionId === id) {
        try {
          localStorage.removeItem(ACTIVE_SESSION_KEY)
        } catch {
          /* ignore */
        }
      }
      const rows = await refreshSessions()
      if (sessionId === id) {
        if (rows.length === 0) {
          await handleNewChat()
        } else {
          await loadSession(rows[0].id)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete chat')
    } finally {
      setBusy(false)
    }
  }

  async function handleUpload(side: 'before' | 'after', file: File) {
    if (!sessionId) return
    setUploadBusy(true)
    setError(null)
    try {
      const preview = await postPreview(file)
      const url = previewToObjectUrl(preview.preview_png_base64)
      if (side === 'before') {
        if (beforeBlob) URL.revokeObjectURL(beforeUrl)
        setBeforeUrl(url)
        setBeforeFilename(file.name)
        setBeforeBlob(true)
        setBeforeFile(file)
      } else {
        if (afterBlob) URL.revokeObjectURL(afterUrl)
        setAfterUrl(url)
        setAfterFilename(file.name)
        setAfterBlob(true)
        setAfterFile(file)
      }

      const uploaded = await uploadSessionAsset(
        tokenFn,
        sessionId,
        file,
        `${side === 'before' ? 'Before' : 'After'} date uploaded: ${file.name}`,
      )
      const attUrl =
        uploaded.asset.preview_png_base64 != null
          ? previewToObjectUrl(uploaded.asset.preview_png_base64)
          : url
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== 'welcome'),
        {
          id: uploaded.user_message.id,
          role: 'user',
          text: uploaded.user_message.content,
          attachment: {
            id: uploaded.asset.id,
            url: attUrl,
            filename: uploaded.asset.filename,
          },
        },
        {
          id: uploaded.assistant_message.id,
          role: 'assistant',
          text: uploaded.assistant_message.content,
        },
      ])
      await refreshSessions()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploadBusy(false)
    }
  }

  async function handleSend() {
    const text = draft.trim()
    if (!text || !sessionId || busy) return
    setBusy(true)
    setError(null)
    setDraft('')

    // If both real images are uploaded, run the change detection model.
    if (beforeFile && afterFile) {
      try {
        const userMsgId = `user-${Date.now()}`
        setMessages((prev) => [
          ...prev.filter((m) => m.id !== 'welcome'),
          { id: userMsgId, role: 'user', text },
        ])

        const result = await postChange(beforeFile, afterFile, text)

        // Build the assistant reply text
        const method = (result.evidence as Record<string, unknown>)?.method as string | undefined
        const fallback = ((result.evidence as Record<string, unknown>)?.metadata as Record<string, unknown>)?.fallback as boolean | undefined
        const modelTag = fallback === false ? '🤖 **SiameseChangeDetector**' : '📐 **Pixel-difference fallback**'
        const changePct = result.change_pct != null ? result.change_pct.toFixed(1) : '—'
        const score = result.score != null ? result.score.toFixed(3) : '—'

        let replyText = `${modelTag}\n\n${result.text}\n\n**Changed area:** ${changePct}%  |  **Score:** ${score}`
        if (method) replyText += `  |  **Method:** ${method}`

        // If the model returned an overlay, show it as an image attachment
        let overlayUrl: string | undefined
        if (result.overlay_png_base64) {
          overlayUrl = previewToObjectUrl(result.overlay_png_base64)
        }

        const overlayId = overlayUrl ? `overlay-${Date.now()}` : undefined
        if (overlayUrl && overlayId) {
          setOverlayAttachment({ id: overlayId, url: overlayUrl })
        }
        setMessages((prev) => [
          ...prev,
          {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            text: replyText,
            ...(overlayUrl && overlayId
              ? { attachment: { id: overlayId, url: overlayUrl, filename: 'change-overlay.png' } }
              : {}),
          },
        ])

      } catch (err) {
        setDraft(text)
        setError(err instanceof Error ? err.message : 'Change detection failed')
      } finally {
        setBusy(false)
      }
      return
    }

    // No real images uploaded yet — fall back to Gemini chat
    try {
      const res = await sendSessionMessage(tokenFn, sessionId, text)
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== 'welcome'),
        {
          id: res.user_message.id,
          role: 'user',
          text: res.user_message.content,
        },
        {
          id: res.assistant_message.id,
          role: 'assistant',
          text: res.assistant_message.content,
        },
      ])
      await refreshSessions()
    } catch (err) {
      setDraft(text)
      setError(err instanceof Error ? err.message : 'Send failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-screen flex-col bg-bg text-ink">
      <Navbar />
      {error ? (
        <div className="border-b border-change/40 bg-change/10 px-4 py-2 text-xs text-ink">
          {error}
        </div>
      ) : null}
      <div className="flex min-h-0 flex-1">
        <SessionSidebar
          sessions={sessions}
          activeSessionId={sessionId}
          collapsed={sidebarCollapsed}
          onCollapsedChange={setCollapsed}
          onNewChat={() => void handleNewChat()}
          onSelect={(id) => void loadSession(id)}
          onDelete={(id) => void handleDelete(id)}
          busy={busy || booting || uploadBusy}
        />
        <div className="min-h-0 min-w-0 flex-1">
          <SplitWorkspace
            mode={mode}
            onModeChange={setMode}
            chat={
              <div className="flex h-full min-h-0 flex-col">
                <ChatPanel
                  messages={messages}
                  draft={draft}
                  onDraftChange={setDraft}
                  onSend={() => void handleSend()}
                  stagedFile={null}
                  stagedPreviewUrl={null}
                  onStageFile={() => undefined}
                  onClearStaged={() => undefined}
                  activeAttachmentId={activeAttachmentId}
                  onSelectAttachment={(id) => {
                    if (activeAttachmentId === id) {
                      // deselect — restore original after image
                      setActiveAttachmentId(null)
                      if (afterFile) {
                        const url = URL.createObjectURL(afterFile)
                        if (afterBlob) URL.revokeObjectURL(afterUrl)
                        setAfterUrl(url)
                        setAfterFilename(afterFile.name)
                        setAfterBlob(true)
                      }
                    } else if (overlayAttachment && id === overlayAttachment.id) {
                      setActiveAttachmentId(id)
                      if (afterBlob) URL.revokeObjectURL(afterUrl)
                      setAfterUrl(overlayAttachment.url)
                      setAfterFilename('change-overlay.png')
                      setAfterBlob(false)
                    }
                  }}
                  onExpandChat={() => setMode('chat')}
                  busy={busy || booting}
                  title="Before vs after"
                  subtitle={beforeFile && afterFile
                    ? 'Both images loaded — send a query to run the model'
                    : 'Upload both dates under the renderer, then ask'
                  }
                />
                <div className="flex gap-3 border-t border-border bg-surface px-4 py-2 text-[11px] text-muted">
                  <span>
                    Task{' '}
                    <span className="font-medium text-ink">change-VQA</span>
                  </span>
                  <span>
                    Tools{' '}
                    <span className="font-medium text-ink">change-mask</span>
                  </span>
                </div>
              </div>
            }
            renderer={
              <BeforeAfterRenderer
                beforeUrl={beforeUrl}
                afterUrl={afterUrl}
                beforeFilename={beforeFilename}
                afterFilename={afterFilename}
                title="scene1 · Before-After"
                subtitle="Upload replaces left / right"
                legendLabel={null}
                zoom={zoom}
                onZoomChange={setZoom}
                onExpand={() => setMode('renderer')}
                onCloseToSplit={() => setMode('split')}
                expanded={mode === 'renderer'}
                onUploadBefore={(file) => void handleUpload('before', file)}
                onUploadAfter={(file) => void handleUpload('after', file)}
                uploadBusy={uploadBusy || busy || booting}
              />
            }
          />
        </div>
      </div>
    </div>
  )
}
