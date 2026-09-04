// https://vitepress.dev/guide/custom-theme
import { h } from 'vue'
import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import BlogList from './components/BlogList.vue'
import BlogPost from './components/BlogPost.vue'
import GiscusComments from './components/GiscusComments.vue'
import LanguageSelector from './components/LanguageSelector.vue'
import './style.css'

export default {
  extends: DefaultTheme,
  Layout: () => {
    return h(DefaultTheme.Layout, null, {
      'layout-bottom': () => h('div', { class: 'language-float-wrapper' }, [h(LanguageSelector)]),
      'doc-after': () => h(GiscusComments),
    })
  },
  enhanceApp({ app }) {
    app.component('BlogList', BlogList)
    app.component('BlogPost', BlogPost)
    app.component('GiscusComments', GiscusComments)
    app.component('LanguageSelector', LanguageSelector)
  },
} satisfies Theme
