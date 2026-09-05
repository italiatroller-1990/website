<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vitepress'
import { languages } from '../languages'

const STORAGE_KEY = 'preferred-language'
const route = useRoute()
const isOpen = ref(false)

const currentLang = computed(() => {
  const parts = route.path.split('/').filter(Boolean)
  const firstPart = parts[0] || 'en'
  return languages.some(l => l.code === firstPart) ? firstPart : 'en'
})

const currentLangObj = computed(() => {
  return languages.find(l => l.code === currentLang.value) || languages[0]
})

function getLocalizedPath(langCode: string): string {
  const parts = route.path.split('/').filter(Boolean)
  
  if (parts[0] === langCode) {
    return route.path
  }
  
  if (langCode === 'en') {
    const rest = parts.slice(1).join('/')
    return rest ? `/${rest}` : '/'
  } else {
    const rest = parts.slice(1).join('/')
    return `/${langCode}${rest ? '/' + rest : ''}`
  }
}

function navigateTo(langCode: string): void {
  // Save preference
  try {
    localStorage.setItem(STORAGE_KEY, langCode)
  } catch {}
  
  const path = getLocalizedPath(langCode)
  if (path !== route.path) {
    window.location.href = path
  }
}

function toggleDropdown(): void {
  isOpen.value = !isOpen.value
}

function closeDropdown(): void {
  isOpen.value = false
}

function handleKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    closeDropdown()
  }
}

function handleClickOutside(e: MouseEvent): void {
  const target = e.target as HTMLElement
  if (!target.closest('.language-float')) {
    closeDropdown()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', handleClickOutside)

  // Auto-redirect to saved language if on English page
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && saved !== 'en' && currentLang.value === 'en') {
      const path = getLocalizedPath(saved)
      if (path !== route.path) {
        window.location.href = path
        return
      }
    }
  } catch {}
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div class="language-float" :class="{ open: isOpen }">
    <button
      type="button"
      class="language-float-button"
      :aria-label="`Change language. Current: ${currentLangObj.nativeName}`"
      :aria-expanded="isOpen"
      @click="toggleDropdown"
    >
      <span class="language-float-current">{{ currentLangObj.abbr }}</span>
      <span class="language-float-arrow">›</span>
    </button>
    <div v-if="isOpen" class="language-float-dropdown">
      <button
        v-for="lang in languages"
        :key="lang.code"
        type="button"
        class="language-float-option"
        :class="{ active: currentLang === lang.code }"
        :aria-label="lang.nativeName"
        :title="lang.nativeName"
        @click="navigateTo(lang.code)"
      >
        <span class="language-float-option-abbr">{{ lang.abbr }}</span>
        <span class="language-float-option-name">{{ lang.nativeName }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.language-float {
  position: fixed;
  bottom: 1rem;
  right: 1rem;
  z-index: 1000;
  font-family: var(--vp-font-family-base);
}

.language-float-button {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
  font-weight: 600;
  line-height: 1;
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  background: var(--vp-c-bg-alt);
  color: var(--vp-c-text-1);
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

.language-float-button:hover {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

.language-float-button:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: 2px;
}

.language-float-current {
  letter-spacing: 0.03em;
}

.language-float-arrow {
  font-size: 1.1rem;
  line-height: 0.8;
  transition: transform 0.2s;
}

.language-float.open .language-float-arrow {
  transform: rotate(90deg);
}

.language-float-dropdown {
  position: absolute;
  bottom: calc(100% + 0.5rem);
  right: 0;
  min-width: 160px;
  background: var(--vp-c-bg-alt);
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  overflow: hidden;
  animation: fadeIn 0.15s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.language-float-option {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.6rem 0.75rem;
  font-size: 0.85rem;
  color: var(--vp-c-text-2);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}

.language-float-option:hover {
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
}

.language-float-option.active {
  background: var(--vp-c-brand-1);
  color: var(--vp-c-white);
}

.language-float-option:focus-visible {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: -2px;
}

.language-float-option-abbr {
  font-weight: 600;
  font-size: 0.8rem;
  letter-spacing: 0.03em;
  opacity: 0.8;
}

.language-float-option.active .language-float-option-abbr {
  opacity: 1;
}

.language-float-option-name {
  font-size: 0.85rem;
}

@media (max-width: 640px) {
  .language-float {
    bottom: 0.75rem;
    right: 0.75rem;
  }

  .language-float-button {
    padding: 0.45rem 0.65rem;
    font-size: 0.8rem;
  }

  .language-float-dropdown {
    min-width: 140px;
  }
}
</style>
