/** API 호출 헬퍼 — 토큰 자동 첨부 */

export function getAuth() {
  try {
    return JSON.parse(localStorage.getItem('if_auth') || 'null')
  } catch { return null }
}

export function setAuth({ token, nickname }) {
  localStorage.setItem('if_auth', JSON.stringify({ token, nickname }))
}

export function clearAuth() {
  localStorage.removeItem('if_auth')
}

export function authHeaders(extra = {}) {
  const a = getAuth()
  return a?.token
    ? { ...extra, Authorization: `Bearer ${a.token}` }
    : { ...extra }
}

/** JSON 요청 + 에러 처리 통합 */
export async function apiJson(url, method = 'GET', body) {
  const res = await fetch(url, {
    method,
    headers: authHeaders(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  checkAuthExpired(res)
  let data = null
  try { data = await res.json() } catch {}
  if (!res.ok) {
    const detail = data?.detail
      ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
      : `${res.status} ${res.statusText}`
    throw Object.assign(new Error(detail), { status: res.status })
  }
  return data
}

/* ── 세션(토큰) 만료 알림 ──
   어디서든 401을 받으면 이 콜백이 호출되고, 앱이 로그인 화면으로 되돌린다. */
let _onAuthExpired = null

export function setOnAuthExpired(fn) {
  _onAuthExpired = fn
}

export function notifyAuthExpired() {
  clearAuth()
  _onAuthExpired?.()
}
