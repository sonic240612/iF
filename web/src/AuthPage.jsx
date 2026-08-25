import React, { useState } from 'react'
import { setAuth } from './api.js'

/** 닉네임 + 비밀번호 로그인/가입 화면 */
export default function AuthPage({ notice, onAuth }) {
  const [mode, setMode] = useState('login') // login | register
  const [nickname, setNickname] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (mode === 'register' && password !== password2) {
      setError('비밀번호가 서로 일치하지 않습니다.')
      return
    }
    setBusy(true)
    try {
      const res = await fetch(`/api/auth/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: nickname.trim(), password }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || '요청 실패')
      setAuth(data)
      onAuth(data.nickname)
    } catch (err) {
      setError(String(err.message || err))
    } finally { setBusy(false) }
  }

  return (
    <div className="auth-page">
      {/* 배경 장식 */}
      <div className="auth-bg-orb orb1" />
      <div className="auth-bg-orb orb2" />

      <div className="auth-card">
        {notice && <div className="auth-notice">🔔 {notice}</div>}
        <div className="auth-logo">
          <h1>iF<span>이프</span></h1>
          <p>당신의 이야기를 기억합니다.</p>
        </div>

        <div className="auth-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={mode === 'login'}
            className={mode === 'login' ? 'on' : ''} onClick={() => { setMode('login'); setError('') }}>
            로그인
          </button>
          <button type="button" role="tab" aria-selected={mode === 'register'}
            className={mode === 'register' ? 'on' : ''} onClick={() => { setMode('register'); setError('') }}>
            회원가입
          </button>
          <span className={`tab-glider ${mode}`} />
        </div>

        <form onSubmit={submit} className="auth-form">
          <label className="field">
            <span className="field-label">닉네임</span>
            <div className="input-wrap">
              <span className="input-icon">👤</span>
              <input value={nickname} onChange={e => setNickname(e.target.value)}
                placeholder={mode === 'register' ? 'AI가 불러줄 이름 (2~20자)' : '닉네임'}
                maxLength={20} autoComplete="username" required />
            </div>
          </label>

          <label className="field">
            <span className="field-label">비밀번호</span>
            <div className="input-wrap">
              <span className="input-icon">🔒</span>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                placeholder={mode === 'register' ? '6자 이상' : '비밀번호'}
                maxLength={64} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} required />
            </div>
          </label>

          {mode === 'register' && (
            <label className="field">
              <span className="field-label">비밀번호 확인</span>
              <div className="input-wrap">
                <span className="input-icon">🔒</span>
                <input type="password" value={password2} onChange={e => setPassword2(e.target.value)}
                  placeholder="비밀번호 재입력"
                  maxLength={64} autoComplete="new-password" required />
              </div>
            </label>
          )}

          {error && <p className="auth-error">⚠️ {error}</p>}

          <button type="submit" className={`auth-submit ${mode}`} disabled={busy}>
            {busy ? <><i className="spin" /> 처리 중…</> : mode === 'login' ? '로그인' : '가입하고 시작하기'}
          </button>
        </form>

        <p className="auth-note">
          닉네임과 비밀번호만으로 간단하게 가입할 수 있어요.<br />
          같은 계정이면 어느 기기에서든 대화가 이어집니다.
        </p>
      </div>
    </div>
  )
}
