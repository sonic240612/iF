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
