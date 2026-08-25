import React, { useState } from 'react'
import { authHeaders } from './api.js'

const GRADIENTS = [
  'linear-gradient(135deg, #7aa2f7, #b060ff)',
  'linear-gradient(135deg, #ff7eb6, #ff9a9e)',
  'linear-gradient(135deg, #43e97b, #38f9d7)',
  'linear-gradient(135deg, #f6d365, #fda085)',
  'linear-gradient(135deg, #8e2de2, #4a00e0)',
  'linear-gradient(135deg, #0f2027, #2c5364)',
]
const MOODS = ['neutral', 'cold', 'warm', 'playful']
const MOOD_NAMES = { neutral: '기본', cold: '차가움', warm: '다정함', playful: '장난기' }

/** 커스텀 캐릭터 수정 화면 — 제작자 본인만 진입 */
export default function EditCharacter({ character, onSaved, onBack }) {
  const [name, setName] = useState(character.name)
  const [systemPrompt, setSystemPrompt] = useState(character.system_prompt)
  const [firstMessage, setFirstMessage] = useState(character.first_message)
  const [genre, setGenre] = useState(character.genre || '')
  const [tags, setTags] = useState((character.tags || []).filter(t => t !== '커스텀').join(', '))
  const [intro, setIntro] = useState(character.intro || '')
  const [worldview, setWorldview] = useState(character.worldview || '')
  const [initialSetup, setInitialSetup] = useState(character.initial_setup || '')
  const [greetingMood, setGreetingMood] = useState(character.greeting_mood || 'neutral')
  const [gradient, setGradient] = useState(character.gradient || GRADIENTS[0])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function save() {
    if (name.trim().length < 1 || systemPrompt.trim().length < 10 || firstMessage.trim().length < 1) {
      setError('이름 / 시스템 프롬프트 / 첫 메시지는 필수입니다.')
      return
    }
    setBusy(true); setError('')
    try {
      const res = await fetch(`/api/characters/${character.id}`, {
        method: 'PUT',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          name: name.trim(),
          system_prompt: systemPrompt.trim(),
          first_message: firstMessage.trim(),
          tags: tags.split(',').map(t => t.trim()).filter(Boolean).slice(0, 6),
          genre: genre.trim(),
          greeting_mood: greetingMood,
          gradient,
          intro: intro.trim(),
          worldview: worldview.trim(),
          initial_setup: initialSetup.trim(),
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '수정 실패')
      onSaved(data)
    } catch (e) {
      setError(String(e.message || e))
    } finally { setBusy(false) }
  }

  return (
    <div className="create">
      <button className="back-btn" onClick={onBack}>← 돌아가기</button>
      <h1>✏️ 캐릭터 수정</h1>

      <div className="form">
        <label>이름 *
          <input value={name} onChange={e => setName(e.target.value)} /></label>

        <label>시스템 프롬프트 * (AI의 성격·행동 결정)
          <textarea rows={6} value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)} /></label>

        <label>첫 메시지 *
          <textarea rows={3} value={firstMessage} onChange={e => setFirstMessage(e.target.value)} /></label>

        <label>줄거리 * (카드 상세에 표시)
          <textarea rows={4} value={intro} onChange={e => setIntro(e.target.value)} /></label>

        <label>세계관
          <textarea rows={3} value={worldview} onChange={e => setWorldview(e.target.value)} /></label>

        <div className="row">
          <label>장르
            <input value={genre} onChange={e => setGenre(e.target.value)} /></label>
          <label>태그 (쉼표 구분)
            <input value={tags} onChange={e => setTags(e.target.value)} /></label>
        </div>

        <label>첫인상 톤
          <select value={greetingMood} onChange={e => setGreetingMood(e.target.value)}>
            {MOODS.map(m => <option key={m} value={m}>{MOOD_NAMES[m]}</option>)}
          </select></label>

        <label>카드 색상
          <div className="swatches">
            {GRADIENTS.map(g => (
              <button key={g} type="button" className={`swatch ${g === gradient ? 'on' : ''}`}
                style={{ background: g }} onClick={() => setGradient(g)} />
            ))}
          </div></label>

        {error && <p className="err">{error}</p>}
        <button className="cta" disabled={busy} onClick={save}>
          {busy ? '저장 중…' : '💾 변경 사항 저장'}
        </button>
      </div>
    </div>
  )
}
