async function request(path, options = {}) {
  try {
    const response = await fetch(`/api/evaluation${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
      signal: AbortSignal.timeout(15000),
    })
    const payload = await response.json()
    if (!response.ok || payload.success === false) {
      throw new Error(payload.error?.message || '评测工作台请求失败')
    }
    return payload
  } catch (error) {
    if (error.name === 'TimeoutError') throw new Error('本机评测服务响应超时，请稍后重试')
    if (error instanceof TypeError || error instanceof SyntaxError) {
      throw new Error('无法连接后端，请检查本机 FastAPI 服务')
    }
    throw error
  }
}

export const getEvaluationWorkbench = () => request('/workbench', { cache: 'no-store' })
export const startEvaluationJob = (action, options = {}) => request('/workbench/jobs', {
  method: 'POST', body: JSON.stringify({ action, ...options }),
})
export const getEvaluationJob = (jobId) => request(`/workbench/jobs/${encodeURIComponent(jobId)}`)
