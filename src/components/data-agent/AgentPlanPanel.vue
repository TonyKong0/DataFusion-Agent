<script setup>
import { routeLabels, stepLabel, toolLabels } from './agentLabels.js'
defineProps({ route: Object, plan: Object })
</script>
<template>
  <section class="v5-card"><h2>系统准备怎么查</h2>
    <p><strong>{{ routeLabels[route?.route] || route?.route }}</strong><template v-if="route?.reason?.length"> · {{ route.reason.join('，') }}</template></p>
    <ol><li v-for="step in plan?.steps || []" :key="step.id"><b>{{ stepLabel(step.id) }} · {{ toolLabels[step.tool] || step.tool }}</b><br>{{ step.instruction }}
      <small v-if="step.depends_on?.length">使用 {{ step.depends_on.map(stepLabel).join('、') }} 的结果</small></li></ol>
  </section>
</template>
