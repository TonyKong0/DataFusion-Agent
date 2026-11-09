import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'Home', component: () => import('../views/HomeView.vue') },
    { path: '/data-agent', name: 'DataAgentDatabase', component: () => import('../views/DataAgentView.vue') },
    { path: '/data-agent/document', name: 'DataAgentDocument', component: () => import('../views/DataAgentView.vue') },
    { path: '/data-agent/unified', name: 'UnifiedAgent', component: () => import('../views/UnifiedAgentView.vue') },
    { path: '/evaluation', name: 'Evaluation', component: () => import('../views/EvaluationView.vue') },
    { path: '/data-agent/multimodal', redirect: '/data-agent/document' },
  ],
})
