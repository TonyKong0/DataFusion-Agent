async function request(path, options = {}, timeout = 200000) {
  try {
    const response = await fetch(`/api${path}`, { ...options, signal: AbortSignal.timeout(timeout) })
    const data = await response.json()
    if (!response.ok || data.success === false) {
      const error = new Error(data.error?.message || '请求失败')
      error.trace = data.trace || []
      throw error
    }
    return data
  } catch (error) {
    if (error.name === 'TimeoutError') throw new Error('请求超时，请稍后重试')
    if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('无法连接后端，请确认服务已启动')
    throw error
  }
}

export const getHealth = () => request('/health', {}, 10000)
export const getDatabaseStatus = () => request('/database/status', {}, 10000)
export const queryDatabase = (question) => request('/nl2sql/query', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }),
})
export const linkSchema = (question, elements = []) => request('/schema/link', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question, elements }),
}, 15000)
export const clarifyDatabase = (sessionId, answer) => request('/semantic/clarify', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id: sessionId, answer }),
})
export const getDocuments = () => request('/documents')
export const getDocumentIndexStatus = (id) => request(`/documents/${encodeURIComponent(id)}/index-status`)
export const getDocumentAnalysis = (id) => request(`/documents/${encodeURIComponent(id)}/analysis`, {}, 60000)
export const uploadDocuments = (files) => {
  const form = new FormData()
  for (const file of (Array.isArray(files) ? files : [files])) form.append('files', file)
  return request('/documents/upload?background=true', { method: 'POST', body: form }, 300000)
}
export const uploadDocument = (file) => uploadDocuments([file]).then(response =>
  response.documents?.[0] ? { ...response.documents[0], errors: response.errors || [] } : response)
export const deleteDocument = (id) => request(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
export const indexDocument = (id) => request(`/documents/${encodeURIComponent(id)}/index?background=true`, { method: 'POST' }, 300000)
export const queryDocument = (documentId, question, documentIds = undefined) => request('/rag/query', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(documentIds === undefined
    ? { document_id: documentId, question, top_k: 5 }
    : { document_ids: documentIds, question, top_k: 5 }),
}, 300000)
export const queryAgent = (question, documentId = null, formulaId = null) => request('/agent/query', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question, document_id: documentId, formula_id: formulaId }),
}, 180000)
export const clarifyAgent = (sessionId, answer, documentId = null, formulaId = null) => request('/agent/clarify', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ session_id: sessionId, answer, document_id: documentId, formula_id: formulaId }),
}, 180000)
