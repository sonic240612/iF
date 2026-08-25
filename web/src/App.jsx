import React, { useEffect, useState } from 'react'
import Home from './Home.jsx'
import CharacterDetail from './CharacterDetail.jsx'
import Chat from './Chat.jsx'
import CreateCharacter from './CreateCharacter.jsx'
import EditCharacter from './EditCharacter.jsx'
import AuthPage from './AuthPage.jsx'
import { getAuth, clearAuth, authHeaders, notifyAuthExpired, setOnAuthExpired } from './api.js'

export default function App() {
  const [authUser, setAuthUser] = useState(() => getAuth()?.nickname || null)
  const [characters, setCharacters] = useState([])
  const [view, setView] = useState('home') // home | detail | chat | create | edit
  const [selectedId, setSelectedId] = useState(null)
  const [authNotice, setAuthNotice] = useState('')

  function refresh() {
    fetch('/api/characters')
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(d => setCharacters(Array.isArray(d) ? d : []))
      .catch(() => {})
  }
  useEffect(refresh, [authUser])

  // 어디서든 401을 받으면 자동 로그아웃 + 안내와 함께 로그인 화면으로
  useEffect(() => {
    setOnAuthExpired(() => {
      clearAuth()
      setAuthUser(null)
      setSelectedId(null)
      setView('home')
      setAuthNotice('세션이 만료되었습니다. 다시 로그인해 주세요.')
    })
  })

  const selected = characters.find(c => c.id === selectedId) || null

  function pick(id) {
    setSelectedId(id)
    setView('detail')
    window.scrollTo(0, 0)
  }

  function logout() {
    fetch('/api/auth/logout', { method: 'POST', headers: authHeaders() }).catch(() => {})
    clearAuth()
    setAuthUser(null)
    setSelectedId(null)
    setView('home')
  }

  // 렌더 중 크래시로 화면이 통째로 사라지지 않도록 방어
  if (typeof window !== 'undefined') {
    window.addEventListener('error', (e) => {
      console.error('[iF] 런타임 에러:', e.message)
    })
  }

  if (!authUser) {
    return <AuthPage notice={authNotice} onAuth={(nickname) => { setAuthUser(nickname); refresh(); setView('home') }} />
  }

  if (view === 'chat' && selected) {
    return <Chat character={selected} user={authUser} onExit={() => setView('detail')} />
  }
  if (view === 'create') {
    return <CreateCharacter onCreated={(card) => { setSelectedId(card.id); refresh(); setView('chat') }} onBack={() => setView('home')} />
  }
  if (view === 'edit' && selected) {
    return (
      <EditCharacter
        character={selected}
        onSaved={(card) => { refresh(); setSelectedId(card.id); setView('chat') }}
        onBack={() => setView('detail')}
      />
    )
  }
  if (view === 'detail' && selected) {
    return (
      <CharacterDetail
        character={selected}
        user={authUser}
        onBack={() => setView('home')}
        onStart={() => { setView('chat'); window.scrollTo(0, 0) }}
        onEdit={() => { setView('edit'); window.scrollTo(0, 0) }}
      />
    )
  }
  return (
    <Home
      characters={characters}
      user={authUser}
      onLogout={logout}
      onPick={pick}
      onCreate={() => { setView('create'); window.scrollTo(0, 0) }}
    />
  )
}
