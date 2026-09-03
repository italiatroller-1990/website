<script setup lang="ts">
import { computed } from 'vue'
import { data as posts } from '../tags.data.ts'

const props = defineProps<{
  tag: string
}>()

const filteredPosts = computed(() => {
  return posts.filter((p) => p.tags.includes(props.tag))
})

function formatDate(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}
</script>

<template>
  <div class="tag-posts">
    <div class="tag-posts-header">
      <h1 class="tag-posts-title">
        <span class="tag-hash">#</span>{{ props.tag }}
      </h1>
      <p class="tag-posts-count">{{ filteredPosts.length }} {{ filteredPosts.length === 1 ? 'post' : 'posts' }}</p>
    </div>
    <div class="blog-list">
      <div v-if="filteredPosts.length === 0" class="blog-empty">
        <p>No posts with this tag yet.</p>
      </div>
      <a
        v-for="post in filteredPosts"
        :key="post.url"
        :href="post.url"
        class="blog-card"
      >
        <span class="blog-card-section">{{ post.section }}</span>
        <h2 class="blog-card-title">{{ post.title }}</h2>
        <time v-if="post.date" class="blog-card-date">{{ formatDate(post.date) }}</time>
        <p v-if="post.description" class="blog-card-desc">{{ post.description }}</p>
        <div v-if="post.tags.length" class="blog-card-tags">
          <a
            v-for="t in post.tags"
            :key="t"
            :href="`/tags/${encodeURIComponent(t)}/`"
            class="blog-card-tag"
            @click.stop
          >#{{ t }}</a>
        </div>
      </a>
    </div>
  </div>
</template>
