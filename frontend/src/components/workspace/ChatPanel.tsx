import { useEffect, useRef, type ReactNode } from 'react'
import { ChatComposer } from './ChatComposer'
import { ChatMessage, type ChatMessageData } from './ChatMessage'
import { AnalysisLoading } from './AnalysisLoading'

type ChatPanelProps = {
  messages: ChatMessageData[]
  draft: string
  onDraftChange: (value: string) => void
  onSend: () => void
  stagedFile: File | null
  stagedPreviewUrl: string | null
  onStageFile: (file: File) => void
  onClearStaged: () => void
  activeAttachmentId?: string | null
  onSelectAttachment?: (id: string) => void
  busy?: boolean
  analysisLoading?: boolean
  analysisAction?: ReactNode
  headerExtra?: ReactNode
  title?: string
  subtitle?: string
  allowAttachments?: boolean
}

export function ChatPanel({
  messages,
  draft,
  onDraftChange,
  onSend,
  stagedFile,
  stagedPreviewUrl,
  onStageFile,
  onClearStaged,
  activeAttachmentId,
  onSelectAttachment,
  busy,
  analysisLoading = false,
  analysisAction,
  headerExtra,
  title = 'Ask this scene',
  subtitle = 'Attach a scene, ask a question, then Send',
  allowAttachments = true,
}: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, analysisLoading])

  return (
    <div className="flex h-full min-h-0 flex-col border-r border-border bg-bg">

      {/* Header */}
      <div className="shrink-0 border-b border-border px-4 py-2.5">
        <h2 className="text-sm font-semibold leading-5 text-ink">
          {title}
        </h2>

        <p className="mt-0.5 text-[11px] leading-4 text-muted">
          {subtitle}
        </p>
        {headerExtra ? <div className="mt-2">{headerExtra}</div> : null}
      </div>

      {/* Messages */}
      <div className="chat-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-5">

        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            message={message}
            activeAttachmentId={activeAttachmentId}
            onSelectAttachment={onSelectAttachment}
          />
        ))}

        {analysisLoading && <AnalysisLoading />}

        <div ref={endRef} />
      </div>

      {/* Analyze action */}
      {analysisAction ? (
        <div className="shrink-0 border-t border-border bg-bg px-3 pt-2">
          {analysisAction}
        </div>
      ) : null}

      {/* Composer */}
      <ChatComposer
        value={draft}
        onChange={onDraftChange}
        onSend={onSend}
        stagedFile={stagedFile}
        stagedPreviewUrl={stagedPreviewUrl}
        onStageFile={onStageFile}
        onClearStaged={onClearStaged}
        allowAttachments={allowAttachments}
        busy={busy}
      />
    </div>
  )
}
