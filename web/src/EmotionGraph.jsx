import React from 'react'

const DIMS = [
  { key: 'affection', label: '호감', color: '#ff7eb6' },
  { key: 'obsession', label: '집착', color: '#b060ff' },
  { key: 'enmity',    label: '혐오', color: '#ff4d4d' },
  { key: 'jealousy',  label: '질투', color: '#43e97b' },
]

/** 감정 변화 라인 그래프 (의존성 없는 SVG) */
export default function EmotionGraph({ data }) {
  if (!data || data.length === 0) {
    return <div className="mem-empty">아직 기록된 감정 변화가 없습니다.</div>
  }

  const W = 600, H = 170, P = 20
  const maxTurn = Math.max(...data.map(d => d.turn), 1)
  const x = i => P + (i / Math.max(data.length - 1, 1)) * (W - 2 * P)
  const y = v => H - P - (v / 100) * (H - 2 * P)

  return (
    <div className="egraph">
      <svg viewBox={`0 0 ${W} ${H}`} className="egraph-svg" preserveAspectRatio="xMidYMid meet">
        {[0, 25, 50, 75, 100].map(v => (
          <line key={v} x1={P} x2={W - P} y1={y(v)} y2={y(v)}
            stroke="rgba(255,255,255,.07)" strokeWidth="1" />
        ))}
        {DIMS.map(({ key, color }) => (
          <polyline key={key}
            points={data.map((d, i) => `${x(i).toFixed(1)},${y(d[key] ?? 0).toFixed(1)}`).join(' ')}
            fill="none" stroke={color} strokeWidth="2.5"
            strokeLinejoin="round" strokeLinecap="round" />
        ))}
      </svg>
      <div className="egraph-legend">
        {DIMS.map(({ key, label, color }) => (
          <span key={key}>
            <span className="dot" style={{ background: color }} />{label}
          </span>
        ))}
      </div>
    </div>
  )
}
