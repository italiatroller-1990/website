<script setup lang="ts">
import { computed } from 'vue'
import { data as posts } from '../tags.data.ts'

const tags = computed(() => {
  const map = new Map<string, { count: number; posts: typeof posts }>()
  for (const post of posts) {
    for (const tag of post.tags) {
      if (!map.has(tag)) {
        map.set(tag, { count: 0, posts: [] })
      }
      const entry = map.get(tag)!
      entry.count++
      entry.posts.push(post)
    }
  }
  return Array.from(map.entries())
    .sort((a, b) => b[1].count - a[1].count)
    .map(([tag, data]) => ({ tag, ...data }))
})
</script>

<template>
  <div class="tags-page">
    <div class="tags-grid">
      <a
        v-for="item in tags"
        :key="item.tag"
        :href="`/tags/${encodeURIComponent(item.tag)}/`"
        class="tag-card"
      >
        <span class="tag-card-name">#{{ item.tag }}</span>
        <span class="tag-card-count">{{ item.count }} {{ item.count === 1 ? 'post' : 'posts' }}</span>
      </a>
    </div>
  </div>
</template>
