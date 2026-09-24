import { useCallback, useRef, useState, type ReactNode } from 'react'
import {
  ASK_LANGUAGES,
  postStt,
  postTranslate,
  type AskLanguage,
} from './api'

export function useSpokenLocale(onError: (message: string) => void) {
  const [language, setLanguage] = useState<AskLanguage>('en')
  const speakerRef = useRef<HTMLAudioElement | null>(null)

  const primeAudio = useCallback(() => {
    const primed = speakerRef.current ?? new Audio()
    speakerRef.current = primed
    void primed.play().catch(() => undefined)
    primed.pause()
  }, [])

  const toEnglish = useCallback(
    async (text: string) => {
      if (language === 'en') return text
      return postTranslate(text, language, 'to_en')
    },
    [language],
  )

  const fromEnglish = useCallback(
    async (text: string) => {
      if (language === 'en') return text
      return postTranslate(text, language, 'from_en')
    },
    [language],
  )

  const say = useCallback((_text: string, _code: AskLanguage = language) => {
    // Playback is optional. A failed ElevenLabs call must not hide a finished analysis.
  }, [language])

  const languageButtons: ReactNode = (
    <div
      className="mt-2 flex flex-wrap rounded-lg border border-border bg-surface p-0.5"
      role="radiogroup"
      aria-label="Reply language"
    >
      {ASK_LANGUAGES.map((opt) => (
        <button
          key={opt.id}
          type="button"
          role="radio"
          aria-checked={language === opt.id}
          onClick={() => setLanguage(opt.id)}
          className={`rounded-md px-2 py-1 text-[11px] font-medium ${
            language === opt.id
              ? 'bg-navy text-white dark:bg-accent dark:text-navy'
              : 'text-muted hover:text-ink'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )

  return {
    language,
    languageButtons,
    primeAudio,
    toEnglish,
    fromEnglish,
    say,
    voiceProps: {
      enableVoice: true as const,
      voiceLanguage: language,
      transcribe: (audio: Blob, code: string) => postStt(audio, code as AskLanguage),
      onVoiceError: onError,
      onPlay: (text: string, code: AskLanguage) => say(text, code),
    },
  }
}
