import { describe, expect, it } from 'vitest'
import { askAnswerBadge } from './api'

describe('askAnswerBadge', () => {
  it('formats the SatQuery caption', () => {
    expect(
      askAnswerBadge({
        vlm_fact: 'Yes.',
        narrated_answer: 'Yes, water is visible.',
        model_chain: ['satquery-vlm', 'gemini-narrator'],
        latency_sec: 1.24,
        path_used: 'satquery-grounded',
      }),
    ).toBe('SatQuery VLM: Yes. · 1.2s · via satquery-grounded')
  })

  it('labels Gemini-only replies', () => {
    expect(
      askAnswerBadge({
        vlm_fact: '',
        narrated_answer: 'Echo',
        model_chain: ['gemini'],
        latency_sec: 0.3,
        path_used: 'gemini',
      }),
    ).toBe('Answered by Gemini')
  })
})
