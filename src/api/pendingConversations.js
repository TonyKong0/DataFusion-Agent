import { reactive } from 'vue'
import { cancelConversation } from './conversations.js'

// Shared across views so a request can finish while another workspace is open.
export const pendingConversations = reactive(new Map())

export function isConversationPending(id) {
  return Boolean(id && pendingConversations.has(id))
}

export async function runConversationOperation(id, execute) {
  if (pendingConversations.has(id)) throw new Error('这段对话正在回答，请等待或先停止生成。')
  const controller = new AbortController()
  const operationId = crypto.randomUUID()
  const operation = { controller, operationId, stopping: false }
  pendingConversations.set(id, operation)
  try {
    return await execute({ signal: controller.signal, operationId })
  } finally {
    if (pendingConversations.get(id)?.operationId === operationId) pendingConversations.delete(id)
  }
}

export async function stopConversationOperation(id) {
  const operation = pendingConversations.get(id)
  if (!operation || operation.stopping) return
  operation.stopping = true
  try { await cancelConversation(id, operation.operationId) }
  finally { operation.controller.abort() }
}
