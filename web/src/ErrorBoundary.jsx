import React from 'react'

/** 렌더 중 크래시 시 빈 화면 대신 에러 내용을 화면에 표시 */
export default class ErrorBoundary extends React.Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('[iF] 크래시:', error, info?.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          minHeight: '100vh',
          padding: 32,
          background: '#141824',
          color: '#eef0f6',
          fontFamily: 'monospace',
          fontSize: 14,
        }}>
          <h2 style={{ color: '#ff6b6b' }}>⚠️ 화면을 그리는 중 오류가 발생했습니다</h2>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', marginTop: 16 }}>
            {String(this.state.error?.stack || this.state.error)}
          </pre>
          <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
            <button onClick={() => location.reload()} style={btn}>새로고침</button>
            <button onClick={() => { Object.keys(localStorage).filter(k => k.startsWith('if_')).forEach(k => localStorage.removeItem(k)); location.href = '/' }} style={btn}>
              세션 초기화 후 새로고침
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

const btn = {
  padding: '10px 18px',
  borderRadius: 10,
  border: 'none',
  background: '#7aa2f7',
  color: '#10131c',
  fontWeight: 700,
  cursor: 'pointer',
}
