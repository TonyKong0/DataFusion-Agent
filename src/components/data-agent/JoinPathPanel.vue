<script setup>
defineProps({ plan: { type: Object, required: true } })
</script>

<template>
  <section class="card detail-panel" aria-label="JOIN Path">
    <h2>JOIN Path</h2>
    <p class="muted">所有关联条件均来自 Chinook 的真实外键。</p>
    <div class="join-chain">
      <span v-for="(table, index) in plan.join_tables" :key="`${table}-${index}`" class="join-node">
        <b>{{ table }}</b><small v-if="index < plan.join_tables.length - 1">→</small>
      </span>
    </div>
    <ol class="join-edges">
      <li v-for="(edge, index) in plan.join_path" :key="index">
        {{ edge.left_table }}.{{ edge.left_column }} = {{ edge.right_table }}.{{ edge.right_column }}
      </li>
    </ol>
  </section>
</template>
