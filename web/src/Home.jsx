import React, { useState } from 'react'

export default function Home({ characters, onPick, onCreate }) {
  const [genre, setGenre] = useState('전체')
  const safeList = Array.isArray(characters) ? characters : []

  // 장르 필터: 전체 / 커스텀(유저 제작) / 캐릭터들이 실제 사용하는 장르 동적 수집
  const genres = ['전체', '커스텀']
  for (const c of safeList) {
    if (c.genre && !genres.includes(c.genre)) genres.push(c.genre)
  }

  let list
  if (genre === '전체') list = safeList
  else if (genre === '커스텀') list = safeList.filter(c => (c.tags || []).includes('커스텀'))
  else list = safeList.filter(c => c.genre === genre)

  return (
    <div className="home">
      <header className="hero">
        <h1>iF<span>이프</span></h1>
        <p>차원의 틈 너머, 당신이 서사의 주체가 되는 곳.<br />
          캐릭터를 선택하고 이야기를 시작하세요.</p>
      </header>

      <nav className="genre-nav">
        {genres.map(g => (
          <button
            key={g}
            className={g === genre ? 'active' : ''}
            onClick={() => setGenre(g)}
          >{g}</button>
        ))}
      </nav>

      <main className="card-grid">
        <button className="char-card create-card-mini" onClick={onCreate}>
          <span className="cc-plus">＋</span>
          <strong>캐릭터 만들기</strong>
          <p>직접 설계하거나 AI 어시스트로 30초 완성</p>
        </button>
        {list.length === 0 && <p className="empty">해당 장르의 캐릭터가 없습니다.</p>}
        {list.map(c => (
          <button
            key={c.id}
            className="char-card"
            onClick={() => onPick(c.id)}
            style={{ '--card-gradient': c.gradient || 'linear-gradient(135deg, #7aa2f7, #b060ff)' }}
          >
            <div className="card-top">
              <span className="card-emoji">{c.emoji || '💬'}</span>
              <span className="pill genre">{c.genre}</span>
            </div>
            <strong className="card-name">{c.name}</strong>
            <p className="card-intro">{(c.intro || '소개글이 없습니다.').slice(0, 72)}…</p>
            <div className="card-tags">
              {c.tags.map(t => <span key={t} className="tag">#{t}</span>)}
            </div>
            <span className="card-cta">이야기 보기 →</span>
          </button>
        ))}
      </main>

      <footer className="home-footer">
        <span>Powered by Gemma · FSM Emotion Engine</span>
      </footer>
    </div>
  )
}
