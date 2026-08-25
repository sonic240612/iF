import React, { useEffect, useState } from 'react'
import Home from './Home.jsx'
import CharacterDetail from './CharacterDetail.jsx'
import Chat from './Chat.jsx'
import CreateCharacter from './CreateCharacter.jsx'

export default function App() {
  const [characters, setCharacters] = useState([])
  const [view, setView] = useState('home') // home | detail | chat | create
  const [selectedId, setSelectedId] = useState(null)

  function refresh() {
    fetch('/api/characters').then(r => r.json()).then(setCharacters).catch(() => {})
  }
  useEffect(refresh, [])

  const selected = characters.find(c => c.id === selectedId) || null

  function pick(id) {
    setSelectedId(id)
    setView('detail')
    window.scrollTo(0, 0)
  }

  if (view === 'chat' && selected) {
    return <Chat character={selected} onExit={() => setView('detail')} />
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
  return <Home characters={characters} onPick={pick} onCreate={() => { setView('create'); window.scrollTo(0, 0) }} />
}
