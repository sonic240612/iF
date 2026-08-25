import React, { useEffect, useRef, useState } from 'react'
import { authHeaders } from './api.js'

const MOOD_THEMES = {
  cold:         { name: '냉담',   accent: '#7aa2f7' },
  tsundere:     { name: '츤데레', accent: '#ff7eb6' },
  warm:         { name: '다정',   accent: '#ffb347' },
  affectionate: { name: '애정',   accent: '#ff5c8a' },
  playful:      { name: '장난',   accent: '#43e97b' },
  obsessive:    { name: '집착',   accent: '#b060ff' },
  hostile:      { name: '적대',   accent: '#ff4d4d' },
}

const STATE_LABELS = [
  ['affection', '호감'],
  ['obsession', '집착'],
  ['enmity', '혐오'],
  ['jealousy', '질투'],
]


/** 응답 텍스트를 대사/묘사(흐리게)로 구분해 렌더링.
 *  *...* : 행동·생각·묘사 (신규 형식) / (...) : 기존 괄호 묘사 — 모두 흐리게 표시 */
function renderRichText(text) {
  if (!text) return null
  const parts = []
  const re = /(\*[^*]+\*|\([^)]*\))/g
  let last = 0, m, key = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ t: 'plain', v: text.slice(last, m.index) })
    parts.push({ t: 'muted', v: m[0] })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push({ t: 'plain', v: text.slice(last) })
  return parts.map((p, i) =>
    p.t === 'plain'
      ? <React.Fragment key={i}>{p.v}</React.Fragment>
      : <span key={i} className="narration">{p.v}</span>
  )
}

export default function Chat({ character, onExit }) {
  // 세션 키는 서버에서 '유저닉네임:캐릭터ID'로 결정 → 어느 기기에서 접속해도 대화 이어짐
  const sessKey = character.id
  const [messages, setMessages] = useState([{ role: 'assistant', content: character.first_message }])
  const [state, setState] = useState(null)
  const [cards, setCards] = useState([])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState('')
  const [memoryNote, setMemoryNote] = useState('')
  const [truncNote, setTruncNote] = useState(false)
  const [showPatch, setShowPatch] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [patchText, setPatchText] = useState('')
  const [patchSavedAt, setPatchSavedAt] = useState(null)
  const [busy, setBusy] = useState(false)
  const bottomRef = useRef(null)

  const mood = state?.mood ?? character.greeting_mood ?? 'neutral'
  const theme = MOOD_THEMES[mood] ?? MOOD_THEMES.playful

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, typing])

  // 재접속 시 서버에서 이전 대화 복원
  useEffect(() => {
    fetch(`/api/sessions/${sessKey}/history`, { headers: authHeaders() })
      .then(r => r.json())
      .then(data => {
        if (data.messages?.length) {
          setMessages(data.messages)
          if (data.state) setState({ ...data.state, mood: data.state.mood?.() || inferMood(data.state) })
        }
        if (data.user_patch) setPatchText(data.user_patch)
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function inferMood(s) {
    if (s.enmity >= 60) return 'hostile'
    if (s.jealousy >= 50 || s.obsession >= 60) return 'obsessive'
    if (s.affection >= 70) return 'affectionate'
    if (s.affection >= 45) return 'warm'
    if (s.affection >= 25) return 'tsundere'
    return 'cold'
  }

  async function savePatch() {
    try {
      const res = await fetch(`/api/sessions/${sessKey}/user-patch`, {
        method: 'PUT',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ patch: patchText }),
      })
      if (!res.ok) throw new Error()
      setPatchSavedAt(new Date().toLocaleTimeString())
    } catch { setPatchSavedAt(null) }
  }

  async function resetChat() {
    await fetch(`/api/sessions/${sessKey}`, { method: 'DELETE', headers: authHeaders() }).catch(() => {})
    setMessages([{ role: 'assistant', content: character.first_message }])
    setState(null)
    setCards([])
    setMemoryNote('')
    setPatchText('')
    setConfirmReset(false)
  }

  // SSE 스트리밍으로 응답을 실시간 수신. action이 있으면 '선택한 행동'으로 전송
  async function send(textOverride, actionOverride) {
    const isAction = !!actionOverride
    const text = ((actionOverride ?? textOverride) ?? input).trim()
    if (!text || busy || !character.id) return
    setInput('')
    setCards([])
    setMessages(m => [...m, { role: 'user', content: text }])
    setBusy(true)
    let live = ''
    try {
      const res = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(
          isAction
            ? { character_id: character.id, action: text }
            : { character_id: character.id, message: text }
        ),
      })
      if (!res.ok || !res.body) throw new Error('stream unavailable')

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop()
        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data:')) continue
          const evt = JSON.parse(line.slice(5))
          if (evt.type === 'state') {
            setState({ ...evt.state, mood: evt.mood })
          } else if (evt.type === 'delta') {
            live += evt.text
            setTyping(live)   // 실제 생성 토큰을 그대로 흘려보낸다
          } else if (evt.type === 'done') {
            setTyping('')
            setMessages(m => [...m, { role: 'user', content: isAction ? `[${text}]` : undefined, ...(isAction ? {} : {}) }.role ? m : m, ...[]].length ? [...(prev => prev)(m), { role: 'assistant', content: evt.reply }] : m)
            setCards(evt.choice_cards || [])
            if (evt.memory_saved) {
              setMemoryNote(`🧠 새로운 기억 저장됨 (총 ${evt.total_memories}개)`)
              setTimeout(() => setMemoryNote(''), 4000)
            }
            if (evt.truncated) {
              setTruncNote(true)
              setTimeout(() => setTruncNote(false), 6000)
            }
          } else if (evt.type === 'error') {
            throw new Error(evt.detail || 'stream error')
          }
        }
      }
      // 스트림 종료 후 남은 버퍼 처리 (마지막 done 이벤트 누락 방지)
      buffer += decoder.decode()
      if (buffer.trim().startsWith('data:')) {
        try {
          const evt = JSON.parse(buffer.trim().slice(5))
          if (evt.type === 'done') {
            setTyping('')
            setMessages(m => [...m, { role: 'assistant', content: evt.reply }])
            setCards(evt.choice_cards || [])
          }
        } catch {}
      }
    } catch (e) {
      setTyping('')
      if (live) setMessages(m => [...m, { role: 'assistant', content: live }])
      else setMessages(m => [...m, { role: 'assistant', content: '(연결에 문제가 발생했습니다. 다시 시도해 주세요)' }])
    } finally {
      setBusy(false)
    }
  }

  function chooseCard(card) {
    // 선택지는 문장 그대로 보내지 않고 '행동'으로 전송 → AI가 장면을 이어서 생성
    send(null, card.text)
  }

  return (
    <div className="chat-page" style={{ '--accent': theme.accent }}>
      <header className="chat-header">
        <button className="back-btn" onClick={onExit}>←</button>
        <span className="chat-emoji">{character.emoji}</span>
        <div className="chat-title">
          <strong>{character.name}</strong>
          <span className="mood-badge" style={{ color: theme.accent }}>
            ● {theme.name}{state?.turn > 0 ? ` · ${state.turn}턴` : ''}
          </span>
        </div>
        <button className={`patch-btn ${showPatch ? 'on' : ''}`} title="AI가 항상 기억할 정보를 지정합니다" onClick={() => setShowPatch(v => !v)}>
          📝 <span className="patch-label">유저 패치</span>
        </button>
        <button className="reset-btn" title="대화 기록과 감정·기억을 초기화합니다" onClick={() => setConfirmReset(true)}>
          🗑 <span className="btn-label">초기화</span>
        </button>
        {state?.turn > 0 && (
          <div className="state-chips">
            {STATE_LABELS.map(([key, label]) => (
              <span key={key} className={`chip ${state[key] >= 60 ? 'hot' : ''}`}>
                {label} {Math.round(state[key])}
              </span>
            ))}
          </div>
        )}
      </header>

      <main className="chat-scroll">
        <div className="chat-inner">
          {memoryNote && <div className="memory-note">{memoryNote}</div>}
          {truncNote && <div className="memory-note trunc">⚠️ 응답이 길어 일부 잘렸습니다</div>}
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {renderRichText(m.content)}
            </div>
          ))}
          {typing && <div className="bubble assistant">{renderRichText(typing)}<span className="caret" /></div>}
          {busy && !typing && (
            <div className="bubble assistant thinking">
              <i /><i /><i />
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </main>

      {cards.length > 0 && !busy && (
        <div className="choice-strip">
          <span className="choice-label">갈래길</span>
          {cards.map((c, i) => (
            <button key={i} onClick={() => chooseCard(c)}>{c.text}</button>
          ))}
        </div>
      )}

      {showPatch && (
        <div className="patch-panel">
          <div className="patch-head">
            <strong>📝 유저 패치</strong>
            <span>AI가 항상 기억할 정보 · 묘사·전개 방식 지정 (최대 1,000자)</span>
          </div>
          <textarea
            maxLength={1000}
            rows={4}
            value={patchText}
            onChange={e => setPatchText(e.target.value)}
            placeholder={"예: 진행된 서사 요약, 캐릭터 감정선, '묘사는 짧고 문학적으로', '전투 장면은 박진감 있게' 등"}
          />
          <div className="patch-actions">
            <small>{patchText.length}/1000{patchSavedAt ? ` · 저장됨 ${patchSavedAt}` : ''}</small>
            <button onClick={savePatch}>저장</button>
          </div>
        </div>
      )}

      {confirmReset && (
        <div className="modal-overlay" onClick={() => setConfirmReset(false)}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <h3>⚠️ 정말 초기화 하시겠습니까?</h3>
            <p>
              {character.name}과(와)의 모든 대화, 감정 상태, 장기기억이 삭제되며<br />
              되돌릴 수 없습니다.
            </p>
            <div className="modal-actions">
              <button className="btn-cancel" onClick={() => setConfirmReset(false)}>취소</button>
              <button className="btn-danger" onClick={resetChat}>초기화</button>
            </div>
          </div>
        </div>
      )}

      <footer className="composer">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder={`${character.name}에게 말 걸기…`}
          disabled={busy}
        />
        <button onClick={() => send()} disabled={busy || !input.trim()} aria-label="전송">➤</button>
      </footer>
    </div>
  )
}
