import React, { useEffect, useRef, useState } from 'react'
import { authHeaders, notifyAuthExpired, apiJson } from './api.js'
import EmotionGraph from './EmotionGraph.jsx'

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
  const [showMem, setShowMem] = useState(false)
  const [memList, setMemList] = useState([])
  const [showModelSel, setShowModelSel] = useState(false)
  // 선택한 모델을 localStorage에 저장 → 모든 캐릭터에서 유지
  const [selectedModel, setSelectedModel] = useState(() => {
    try { return JSON.parse(localStorage.getItem('if_model') || 'null') || { key: 'gemma4', label: 'Gemma 4' } }
    catch { return { key: 'gemma4', label: 'Gemma 4' } }
  })
  const [showGraph, setShowGraph] = useState(false)
  const [emoData, setEmoData] = useState(null)
  const [confirmExport, setConfirmExport] = useState(false)
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
      .then(r => {
        if (r.status === 401) { notifyAuthExpired(); throw new Error('expired') }
        return r.json()
      })
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
      if (!res.ok) {
        if (res.status === 401) notifyAuthExpired()
        throw new Error()
      }
      setPatchSavedAt(new Date().toLocaleTimeString())
    } catch { setPatchSavedAt(null) }
  }



  async function loadEmotions() {
    try {
      const data = await apiJson(`/api/sessions/${sessKey}/emotions`)
      setEmoData(data.history || [])
    } catch { setEmoData([]) }
  }


  // 사용 가능한 모델 목록 (최초 1회)
  const [models, setModels] = useState([])
  useEffect(() => {
    fetch('/api/models').then(r => r.json()).then(setModels).catch(() => {})
  }, [])

  async function loadMemories() {
    try {
      const data = await apiJson(`/api/sessions/${sessKey}/memories`)
      setMemList(data.memories || [])
    } catch {}
  }

  async function delMemory(mid) {
    try {
      await apiJson(`/api/sessions/${sessKey}/memories/${mid}`, 'DELETE')
      setMemList(l => l.filter(m => m.id !== mid))
    } catch {}
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


  // 모달 확인 후 실제 다운로드 수행
  function doExport() {
    setConfirmExport(false)
    exportChat()
  }

  // 대화를 보기 좋은 텍스트 파일로 내려받기
  function exportChat() {
    const lines = []
    lines.push(`iF 대화 기록 — ${character.name}`)
    lines.push(`내보낸 날짜: ${new Date().toLocaleString('ko-KR')}`)
    if (state?.turn > 0) lines.push(`대화 턴 수: ${state.turn} · 감정: 호감 ${Math.round(state.affection)} / 집착 ${Math.round(state.obsession)} / 질투 ${Math.round(state.jealousy)}`)
    lines.push('─'.repeat(40))
    for (const m of messages) {
      const who = m.role === 'user' ? `나` : `${character.name}`
      lines.push('')
      lines.push(`[${who}]`)
      lines.push(m.content)
    }
    const blob = new Blob([lines.join('\\n\\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `iF_${character.name}_대화기록.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  // SSE 스트리밍으로 응답을 실시간 수신. action이 있으면 '선택한 행동'으로 전송
  // ── 모바일(iOS Safari) 키보드 대응 ──
  // 자판이 올라오면 시각적 뷰포트가 줄어든다. 그 높이에 맞춰 채팅 화면을 재조정하고
  // 최신 메시지가 입력창 바로 위에 오도록 스크롤을 유지한다.
  useEffect(() => {
    const vv = window.visualViewport
    if (!vv) return
    function handleViewport() {
      const shrink = Math.max(0, window.innerHeight - vv.height)
      document.documentElement.style.setProperty('--kb-adjust', `${shrink}px`)
      requestAnimationFrame(() => {
        bottomRef.current?.scrollIntoView({ block: 'end' })
      })
    }
    vv.addEventListener('resize', handleViewport)
    vv.addEventListener('scroll', handleViewport)
    window.addEventListener('focusin', () => setTimeout(handleViewport, 350))
    return () => {
      vv.removeEventListener('resize', handleViewport)
      vv.removeEventListener('scroll', handleViewport)
    }
  }, [])

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
            ? { character_id: character.id, model: selectedModel.key || undefined, action: text }
            : { character_id: character.id, model: selectedModel.key || undefined, message: text }
        ),
      })
      if (!res.ok || !res.body) {
        if (res.status === 401) notifyAuthExpired()
        throw new Error('stream unavailable')
      }

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
        <button className={`hbtn ${showPatch ? 'on' : ''}`} title="AI가 항상 기억할 정보를 지정합니다" onClick={() => setShowPatch(v => !v)}>
          📝 <span className="btn-label">유저 패치</span>
        </button>
        <button className={`hbtn ${showGraph ? 'on' : ''}`} title="감정 변화 그래프" onClick={() => { setShowGraph(v => { if (!v) loadEmotions(); return !v }) }}>
          📊 <span className="btn-label">감정</span>
        </button>
        <button className={`hbtn ${showMem ? 'on' : ''}`} title="장기기억 관리" onClick={() => { setShowMem(v => { if (!v) loadMemories(); return !v }) }}>
          🧠 <span className="btn-label">기억</span>
        </button>
        <button className={`hbtn export`} title="대화를 텍스트 파일로 저장합니다" onClick={() => setConfirmExport(true)}>
          📄 <span className="btn-label">내보내기</span>
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

      {showGraph && (
        <div className="patch-panel">
          <div className="patch-head">
            <strong>📊 감정 변화</strong>
            <span>대화가 진행되며 캐릭터의 감정이 어떻게 변했는지 보여줍니다.</span>
          </div>
          {(emoData?.length > 0)
            ? <EmotionGraph data={emoData} />
            : <div className="mem-empty">아직 기록된 감정 변화가 없습니다. 대화를 시작해 보세요!</div>}
        </div>
      )}

      {showMem && (
        <div className="patch-panel">
          <div className="patch-head">
            <strong>🧠 장기기억 관리</strong>
            <span>AI가 요약해 저장한 기억들입니다. 삭제하면 더 이상 참조하지 않아요.</span>
          </div>
          {memList.length === 0 && (
            <div className="mem-empty">아직 저장된 기억이 없습니다. (10턴마다 자동 생성)</div>
          )}
          {memList.map(m => (
            <div key={m.id} className="mem-item">
              <span className="mem-text">{m.text}</span>
              <button className="mem-del" title="기억 삭제" onClick={() => delMemory(m.id)}>✕</button>
            </div>
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

      {confirmExport && (
        <div className="modal-overlay" onClick={() => setConfirmExport(false)}>
          <div className="modal-box" onClick={e => e.stopPropagation()}>
            <h3>📄 대화를 내보낼까요?</h3>
            <p>지금까지의 대화를 텍스트 파일(.txt)로 다운로드합니다.</p>
            <div className="modal-actions">
              <button className="btn-cancel" onClick={() => setConfirmExport(false)}>취소</button>
              <button className="btn-danger" style={{ background: '#43e97b' }} onClick={doExport}>내보내기</button>
            </div>
          </div>
        </div>
      )}

      <footer className="composer">
        <div style={{ position: 'relative' }}>
          <button onClick={() => {
            try { setSelectedModel(JSON.parse(localStorage.getItem('if_model') || 'null') || { key: 'gemma4', label: 'Gemma 4' }) } catch {}
            setShowModelSel(v => !v)
          }} style={{
            width: 44, height: 48, borderRadius: 12,
            border: '1px solid #3d4557', background: '#1e2330',
            color: '#c6cad6', fontSize: 22, cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>+</button>
          {showModelSel && (
            <div style={{
              position: 'absolute', bottom: 56, left: 0, zIndex: 100,
              width: 280, background: '#1a1f2b',
              border: '1px solid #3d4557', borderRadius: 14,
              boxShadow: '0 16px 40px rgba(0,0,0,.6)',
              padding: 8,
            }}>
              <div style={{ padding: '8px 10px 4px', fontSize: 11, fontWeight: 700, color: '#6b7186', letterSpacing: 1 }}>
                모델 선택
              </div>
              {(models.length > 0 ? models : [{key:'gemma4', label:'Gemma 4'}]).map(m => {
                const sel = selectedModel.key === m.key
                return (
                  <button key={m.key} onClick={() => {
                    setSelectedModel({ key: m.key, label: m.label })
                    setShowModelSel(false)
                  }} style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '11px 12px', marginBottom: 2,
                    border: 'none', borderRadius: 9,
                    background: sel ? '#2a3040' : 'transparent',
                    color: sel ? '#fff' : '#aab0bd',
                    fontSize: 15, fontWeight: sel ? 700 : 400,
                    cursor: 'pointer',
                  }}>
                    {sel && <span style={{ marginRight: 6 }}>✓</span>}
                    {m.label}
                  </button>
                )
              })}
              <p style={{ margin: '6px 10px 2px', fontSize: 11, color: '#565c6e' }}>
                모델말투·속도가 달라집니다.
              </p>
            </div>
          )}
        </div>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          onFocus={() => setTimeout(() => {
            // 모바일: 자판이 올라온 뒤 최신 대화가 보이도록 스크롤
            bottomRef.current?.scrollIntoView({ block: 'end' })
          }, 350)}
          placeholder={`${character.name}에게 말 걸기…`}
          disabled={busy}
        />
        <button onClick={() => send()} disabled={busy || !input.trim()} aria-label="전송">➤</button>
      </footer>
    </div>
  )
}
