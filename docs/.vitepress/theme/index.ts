// https://vitepress.dev/guide/custom-theme
import { h } from 'vue'
import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import BlogList from './components/BlogList.vue'
import BlogPost from './components/BlogPost.vue'
import GiscusComments from './components/GiscusComments.vue'
import './style.css'

function initDarkModeGTranslate() {
  if (typeof window === 'undefined') return
  const updateGTranslateTheme = () => {
    const isDark = document.documentElement.classList.contains('dark')
    if (typeof window.gtranslateSettings !== 'undefined') {
      window.gtranslateSettings.color_scheme = isDark ? 'dark' : 'light'
    }
  }
  updateGTranslateTheme()
  const observer = new MutationObserver(updateGTranslateTheme)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
}

export default {
  extends: DefaultTheme,
  Layout: () => {
    return h(DefaultTheme.Layout, null, {
      'layout-bottom': () => h('div', { class: 'gtranslate_wrapper' }),
      'doc-after': () => h(GiscusComments),
    })
  },
  enhanceApp({ app }) {
    app.component('BlogList', BlogList)
    app.component('BlogPost', BlogPost)
    app.component('GiscusComments', GiscusComments)
  },
  mounted() {
    initDarkModeGTranslate()
  },
} satisfies Theme
