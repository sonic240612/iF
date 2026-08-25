import React, { useEffect, useState } from 'react'
import Home from './Home.jsx'
import CharacterDetail from './CharacterDetail.jsx'
import Chat from './Chat.jsx'
import CreateCharacter from './CreateCharacter.jsx'
import AuthPage from './AuthPage.jsx'
import { getAuth, clearAuth, authHeaders } from './api.js'

export default function App() {
  const [authUser, setAuthUser] = useState(() => getAuth()?.nickname || null)
  const [characters, setCharacters] = useState([])
  const [view, setView] = useState('home') // home | detail | chat | create
  const [selectedId, setSelectedId] = useState(null)

  function refresh() {
    fetch('/api/characters')
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(d => setCharacters(Array.isArray(d) ? d : []))
      .catch(() => {})
  }
  useEffect(refresh, [authUser])

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
    return <AuthPage onAuth={(nickname) => { setAuthUser(nickname); refresh(); setView('home') }} />
  }

  if (view === 'chat' && selected) {
    return <Chat character={selected} user={authUser} onExit={() => setView('detail')} />
  }
  if (view === 'create') {
    return <CreateCharacter onCreated={(card) => { setSelectedId(card.id); refresh(); setView('chat') }} onBack={() => setView('home')} />
  }
  if (view === 'detail' && selected) {
    return (
      <CharacterDetail
        character={selected}
        onBack={() => setView('home')}
        onStart={() => { setView('chat'); window.scrollTo(0, 0) }}
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
