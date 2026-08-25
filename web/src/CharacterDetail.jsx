import React, { useEffect, useRef, useState } from 'react'

export default function CharacterDetail({ character, onBack, onStart }) {
  return (
    <div className="detail">
      <button className="back-btn" onClick={onBack}>← 목록</button>

      <div className="detail-hero" style={{ background: character.gradient }}>
        <span className="hero-emoji">{character.emoji}</span>
        <div>
          <h1>{character.name}</h1>
          <div className="hero-tags">
            <span className="pill genre">{character.genre}</span>
            {character.tags.map(t => <span key={t} className="pill">{t}</span>)}
          </div>
        </div>
      </div>

      <section className="detail-section">
        <h2>📖 줄거리</h2>
        <p className="intro-text">{character.intro || character.system_prompt}</p>
      </section>

      {character.worldview && (
        <section className="detail-section">
          <h2>🌍 세계관</h2>
          <p className="intro-text">{character.worldview}</p>
        </section>
      )}

      {character.example_dialogs?.length > 0 && (
        <section className="detail-section">
          <h2>💬 예시 대화</h2>
          {character.example_dialogs.map((d, i) => (
            <div key={i} className="example-block">
              <div className="bubble user">{d.user}</div>
              <div className="bubble assistant">{d.character}</div>
            </div>
          ))}
          <p className="example-note">※ 실제 대화는 감정 상태(호감·집착·질투)에 따라 매번 달라집니다.</p>
        </section>
      )}

      <div className="detail-cta-wrap">
        <button className="cta" onClick={onStart}>
          대화 시작하기 ✨
        </button>
      </div>
    </div>
  )
}
