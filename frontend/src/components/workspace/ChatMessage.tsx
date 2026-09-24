import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AskLanguage } from '../../lib/api'
import { ImageThumb } from './ImageThumb'

export type ChatRole = 'user' | 'assistant'

export type ChatAttachment = {
  id: string
  url: string
  filename: string
}

export type ChatMessageData = {
  id: string
  role: ChatRole
  text: string
  attachment?: ChatAttachment
  /** Extra thumbs (e.g. before + after on one user turn). */
  attachments?: ChatAttachment[]
  confidence?: number
  /** Small source caption under the bubble (Ask-scene model badge). */
  badge?: string
  /** When set, show a Play button that speaks this bubble in that language. */
  speakLanguage?: AskLanguage
}

type ChatMessageProps = {
  message: ChatMessageData
  activeAttachmentId?: string | null
  onSelectAttachment?: (id: string) => void
  onPlay?: (text: string, language: AskLanguage) => void
}

export function ChatMessage({
  message,
  activeAttachmentId,
  onSelectAttachment,
  onPlay,
}: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] rounded-2xl px-3 py-2 text-sm ${
          isUser
            ? 'bg-navy text-white dark:bg-accent dark:text-navy'
            : 'border border-border bg-surface text-ink'
        }`}
      >
        {message.attachment || (message.attachments && message.attachments.length > 0) ? (
          <div className="mb-2">
            <div className="flex flex-wrap gap-2">
              {message.attachment ? (
                <ImageThumb
                  src={message.attachment.url}
                  label={message.attachment.filename}
                  selected={activeAttachmentId === message.attachment.id}
                  onClick={() => onSelectAttachment?.(message.attachment!.id)}
                />
              ) : null}
              {message.attachments?.map((att) => (
                <ImageThumb
                  key={att.id}
                  src={att.url}
                  label={att.filename}
                  selected={activeAttachmentId === att.id}
                  onClick={() => onSelectAttachment?.(att.id)}
                />
              ))}
            </div>
            <p
              className={`mt-1 text-[11px] ${
                isUser ? 'text-white/80 dark:text-navy/70' : 'text-muted'
              }`}
            >
              Click thumbnail to show in renderer
            </p>
          </div>
        ) : null}
        <div
          className={`chat-md [&_a]:underline [&_code]:rounded [&_code]:bg-black/10 [&_code]:px-1 [&_code]:text-[0.85em] dark:[&_code]:bg-white/10 [&_li]:ml-4 [&_ol]:my-1 [&_ol]:list-decimal [&_p]:my-1 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0 [&_strong]:font-semibold [&_ul]:my-1 [&_ul]:list-disc ${
            isUser
              ? '[&_a]:text-white [&_code]:bg-white/20'
              : '[&_a]:text-accent'
          }`}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
        </div>
        {typeof message.confidence === 'number' ? (
          <p className="mt-2 text-[11px] text-muted">
            Confidence {message.confidence.toFixed(2)}
          </p>
        ) : null}
        {message.badge ? (
          <p className="mt-1.5 text-[10px] leading-4 text-muted">{message.badge}</p>
        ) : null}
        {message.speakLanguage && onPlay && message.role === 'assistant' ? (
          <button
            type="button"
            className="mt-1.5 text-[10px] font-medium text-muted underline-offset-2 hover:underline"
            onClick={() => onPlay(message.text, message.speakLanguage!)}
          >
            Play
          </button>
        ) : null}
      </div>
    </div>
  )
}
