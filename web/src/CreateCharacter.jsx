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

export default function CreateCharacter({ onCreated, onBack }) {
  const [mode, setMode] = useState(null) // null | 'manual' | 'ai'
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // 공통
  const [name, setName] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  // AI 어시스트 전용
  const [assistPreview, setAssistPreview] = useState(null)
  // 직접 만들기 전용
  const [firstMessage, setFirstMessage] = useState('')
  const [genre, setGenre] = useState('')
  const [tags, setTags] = useState('')
  const [intro, setIntro] = useState('')
  const [greetingMood, setGreetingMood] = useState('neutral')
  const [gradient, setGradient] = useState(GRADIENTS[0])
  const [initialSetup, setInitialSetup] = useState('')
  const [worldviewText, setWorldviewText] = useState('')

  async function createManual() {
    if (name.trim().length < 1 || systemPrompt.trim().length < 10 || firstMessage.trim().length < 1 || intro.trim().length < 5) {
      setError('이름 / 시스템 프롬프트(10자+) / 첫 메시지 / 줄거리는 필수입니다.')
      return
    }
    setBusy(true); setError('')
    try {
      const res = await fetch('/api/characters', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          id: `char_custom_${Date.now() % 10000000}`,
          name: name.trim(),
          system_prompt: systemPrompt.trim(),
          first_message: firstMessage.trim(),
          tags: tags.split(',').map(t => t.trim()).filter(Boolean).slice(0, 5) || ['오리지널'],
          genre: genre.trim() || '일상',
          greeting_mood: greetingMood,
          gradient,
          intro: intro.trim(),
          worldview: worldviewText.trim(),
          initial_setup: initialSetup,
          emoji: '🎨',
        }),
      })
      if (!res.ok) throw new Error((await res.json()).detail)
      onCreated(await res.json())
    } catch (e) {
      setError(String(e.message || e))
    } finally { setBusy(false) }
  }

  async function createWithAI() {
    if (systemPrompt.trim().length < 10) {
      setError('시스템 프롬프트를 10자 이상 적어주세요.')
      return
    }
    setBusy(true); setError(''); setAssistPreview(null)
    try {
      const res = await fetch('/api/characters/assist', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ system_prompt: systemPrompt.trim(), name: name.trim() }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'AI 생성 실패')
      setAssistPreview(data)
    } catch (e) {
      setError(String(e.message || e))
    } finally { setBusy(false) }
  }

  return (
    <div className="create">
      <button className="back-btn" onClick={onBack}>← 목록</button>
      <h1>캐릭터 만들기</h1>

      {mode === null && (
        <div className="create-cards">
          <button className="create-card" onClick={() => setMode('manual')}>
            <span className="cc-emoji">🎨</span>
            <strong>직접 만들기</strong>
            <p>시스템 프롬프트, 첫 메시지, 태그, 장르를 내 마음대로 세팅</p>
            <span className="cc-note">자유도 최고 · 상세 설정</span>
          </button>
          <button className="create-card" onClick={() => setMode('ai')}>
            <span className="cc-emoji">✨</span>
            <strong>AI 어시스트</strong>
            <p>시스템 프롬프트만 적으면 첫 메시지·태그·장르를 AI가 자동 완성</p>
            <span className="cc-note">30초 완성 · 추천</span>
          </button>
        </div>
      )}

      {mode === 'manual' && (
        <div className="form">
          <label>이름 *<input value={name} onChange={e => setName(e.target.value)} placeholder="예: 하루" /></label>
          <label>시스템 프롬프트 *(캐릭터의 성격/말투/설정)
            <textarea rows={5} value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)}
              placeholder="당신은 밝고 활발한 소꿉친구이다. 반말로 말하며…" /></label>
          <label>첫 메시지 *
            <textarea rows={3} value={firstMessage} onChange={e => setFirstMessage(e.target.value)}
              placeholder="야! 드디어 왔네. 뭐 하면서 이렇게 늦었어?" /></label>
          <label>줄거리 * (카드 상세에 표시됩니다 — 시스템 프롬프트는 공개되지 않아요)
            <textarea rows={4} value={intro} onChange={e => setIntro(e.target.value)}
              placeholder="캐릭터의 성격, 배경, 유저와의 관계 등을 소개하듯 적어주세요." /></label>
          <label>세계관 (선택)
            <textarea rows={3} value={worldviewText} onChange={e => setWorldviewText(e.target.value)}
              placeholder="이야기가 펼쳐지는 세계·배경을 적어주세요." /></label>
          <div className="row">
            <label>장르<input value={genre} onChange={e => setGenre(e.target.value)} placeholder="로맨스" /></label>
            <label>태그 (쉼표 구분)<input value={tags} onChange={e => setTags(e.target.value)} placeholder="츤데레, 연애, 학교" /></label>
          </div>
          <label>초기 설정 (선택 · 최대 1,000자) — 도입부 휘발성 지시
            <textarea rows={4} maxLength={1000} value={initialSetup} onChange={e => setInitialSetup(e.target.value)}
              placeholder="세션 시작 시에만 읽히는 설정입니다. 약 20턴이 지나면 자연스럽게 잊혀져 유저의 자유도를 해치지 않으면서 도입부 분위기를 제어할 수 있어요." />
            <small>{initialSetup.length}/1000</small>
          </label>
          <label>첫인상 톤
            <select value={greetingMood} onChange={e => setGreetingMood(e.target.value)}>
              {MOODS.map(m => <option key={m} value={m}>{MOOD_NAMES[m]}</option>)}
            </select></label>
          <label>카드 색상
            <div className="swatches">
              {GRADIENTS.map(g => (
                <button key={g} className={`swatch ${g === gradient ? 'on' : ''}`}
                  style={{ background: g }} onClick={() => setGradient(g)} />
              ))}
            </div></label>
          {error && <p className="err">{error}</p>}
          <button className="cta" disabled={busy} onClick={createManual}>{busy ? '생성 중…' : '캐릭터 등록'}</button>
        </div>
      )}

      {mode === 'ai' && (
        <div className="form">
          {!assistPreview ? (
            <>
              <label>이름 (선택 — 비우면 미정)<input value={name} onChange={e => setName(e.target.value)} placeholder="비워두면 나중에 정해도 돼요" /></label>
              <label>시스템 프롬프트 * — 여기만 쓰세요!
                <textarea rows={7} value={systemPrompt} onChange={e => setSystemPrompt(e.target.value)}
                  placeholder={'예: 당신은 심해에서 발견된 수수께끼의 인어. 차분하고 신비로운 말투로 말하며, 육지의 모든 것에 호기심이 많다.'} /></label>
              {error && <p className="err">{error}</p>}
              <button className="cta ai" disabled={busy} onClick={createWithAI}>
                {busy ? '✨ AI가 캐릭터를 설계하는 중… (10~20초)' : '✨ AI에게 나머지 맡기기'}
              </button>
            </>
          ) : (
            <>
              <div className="preview-badge">✨ AI 생성 완료 & 저장됨!</div>
              <div className="detail-hero" style={{ background: assistPreview.gradient }}>
                <span className="hero-emoji">{assistPreview.emoji}</span>
                <div>
                  <h1>{assistPreview.name}</h1>
                  <div className="hero-tags">
                    <span className="pill genre">{assistPreview.genre}</span>
                    {assistPreview.tags.map(t => <span key={t} className="pill">{t}</span>)}
                  </div>
                </div>
              </div>
              <section className="detail-section"><h2>📖 AI가 쓴 소개</h2><p className="intro-text">{assistPreview.intro}</p></section>
              <section className="detail-section"><h2>💬 첫 메시지</h2><p className="intro-text">{assistPreview.first_message}</p></section>
              <button className="cta" onClick={() => onCreated(assistPreview)}>바로 대화 시작하기 →</button>
              <button className="ghost-btn" onClick={() => { setAssistPreview(null); setSystemPrompt('') }}>다른 캐릭터 더 만들기</button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
