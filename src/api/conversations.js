const CLIENT_KEY = 'datafusion.clientId.v1'
const CONTEXT_LIMIT_KEY = 'datafusion.contextLimitTokens.v1'

function clientId() {
  let id = localStorage.getItem(CLIENT_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(CLIENT_KEY, id)
  }
  return id
}

async function request(path, options = {}) {
  try {
    const signal = options.signal
      ? AbortSignal.any([options.signal, AbortSignal.timeout(200000)])
      : AbortSignal.timeout(200000)
    const response = await fetch(`/api/conversations${path}`, {
      ...options,
      headers: { 'X-Client-ID': clientId(), 'Content-Type': 'application/json', ...options.headers },
      signal,
    })
    const data = await response.json()
    if (!response.ok || data.success === false) throw new Error(data.error?.message || '会话请求失败')
    return data
  } catch (error) {
    if (error.name === 'TimeoutError') throw new Error('会话请求超时，请稍后重试')
    if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('无法连接会话服务，请检查后端')
    throw error
  }
}

export const listConversations = () => request('')
export const getContextBudgetConfig = () => request('/context-budget', { cache: 'no-store' })
export function getSavedContextLimit() {
  try {
    const value = Number(localStorage.getItem(CONTEXT_LIMIT_KEY))
    return Number.isInteger(value) && value >= 1000 && value <= 50000 ? value : null
  } catch { return null }
}
export function saveContextLimit(value) {
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < 1000 || parsed > 50000) return false
  try { localStorage.setItem(CONTEXT_LIMIT_KEY, String(parsed)); return true }
  catch { return false }
}
export const getConversation = (id) => request(`/${encodeURIComponent(id)}`)
export const createConversation = (mode, documentId = null) => request('', {
  method: 'POST', body: JSON.stringify({ mode, document_id: documentId }),
})
export const importConversation = (session) => request('/import', {
  method: 'POST', body: JSON.stringify({
    legacy_id: session.id,
    mode: session.mode,
    document_id: session.documentId,
    document_name: session.documentName,
    messages: session.messages,
    last_result: session.result,
  }),
})
export const deleteConversation = (id) => request(`/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const queryConversation = (id, question, formulaId = null, documentIds = undefined,
                                  contextLimitTokens = undefined, options = {}) => {
  const body = { question, formula_id: formulaId }
  if (documentIds !== undefined) body.document_ids = documentIds
  if (contextLimitTokens !== undefined) body.context_limit_tokens = contextLimitTokens
  if (options.operationId) body.operation_id = options.operationId
  return request(`/${encodeURIComponent(id)}/query`, {
    method: 'POST', body: JSON.stringify(body),
    signal: options.signal,
  })
}
export const clarifyConversation = (id, answer, contextLimitTokens = undefined, options = {}) => request(`/${encodeURIComponent(id)}/clarify`, {
  method: 'POST', body: JSON.stringify({ answer, ...(contextLimitTokens === undefined ? {} : { context_limit_tokens: contextLimitTokens }),
    ...(options.operationId ? { operation_id: options.operationId } : {}) }),
  signal: options.signal,
})
export const cancelConversation = (id, operationId) => request(`/${encodeURIComponent(id)}/cancel`, {
  method: 'POST', body: JSON.stringify({ operation_id: operationId }),
})
