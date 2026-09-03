<script setup>
import { onMounted, ref } from 'vue'
import { useData } from 'vitepress'

const { page } = useData()
const loaded = ref(false)
const isPost = page.value.relativePath.includes('/posts/')

function loadGiscus() {
  if (loaded.value) return
  loaded.value = true

  const script = document.createElement('script')
  script.src = 'https://giscus.app/client.js'
  script.dataset.repo = 'italiatroller-1990/giscus-comments-xd'
  script.dataset.repoId = 'R_kgDOTl1gow'
  script.dataset.category = 'General'
  script.dataset.categoryId = 'DIC_kwDOTl1go84DCJN5'
  script.dataset.mapping = 'pathname'
  script.dataset.strict = '0'
  script.dataset.reactionsEnabled = '1'
  script.dataset.emitMetadata = '0'
  script.dataset.inputPosition = 'bottom'
  script.dataset.theme = 'https://italiatroller.dpdns.org/assets/css/giscus-style.css'
  script.dataset.lang = 'en'
  script.crossOrigin = 'anonymous'
  script.async = true

  document.getElementById('giscus-container').appendChild(script)
}
</script>

<template>
  <div v-if="isPost" class="giscus-wrapper">
    <h2>Comments</h2>
    <div id="giscus-container">
      <button class="giscus-load-btn" @click="loadGiscus">Load comments</button>
    </div>
  </div>
</template>

<style scoped>
.giscus-wrapper {
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--vp-c-divider);
}

.giscus-load-btn {
  display: inline-block;
  padding: 0.6rem 1.2rem;
  border: 1px solid var(--vp-c-divider);
  border-radius: 20px;
  background: var(--vp-c-bg-soft);
  color: var(--vp-c-text-1);
  font-family: var(--vp-font-family-base);
  font-size: 0.9rem;
  cursor: pointer;
  transition: border-color 0.25s, color 0.25s;
}

.giscus-load-btn:hover {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}
</style>
