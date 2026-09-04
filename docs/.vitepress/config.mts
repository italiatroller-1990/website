import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  appearance: false,
  cleanUrls: true,
  hostname: 'https://italiatroller.dpdns.org',
  lang: 'en',
  title: "Italia Troller's website",
  description: "My personal site for blogs and stuff!",
  lastUpdated: true,
  head: [],
  ignoreDeadLinks: [
    '/lifelog/old-blogs-ar/index',
    '/guides/how-to-buy-a-laptop-in-2026/index'
  ],
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    nav: [
      { text: 'Welcome!', link: '/' },
      { text: 'Lifelogs', link: '/lifelogs/' },
      { text: 'Guides', link: '/guides/' },
      { text: 'Tags', link: '/tags/' },
      { text: 'About me', link: '/about' },
      { text: 'Contact me', link: '/contact' }
    ],

    search: {
      provider: 'local'
    },

    sidebar: [],

    socialLinks: [
      { icon: 'youtube', link: 'https://youtube.com/@italiatroller4793' },
      { icon: 'forgejo', link: 'https://git.italiatroller.dpdns.org' },
      { icon: 'github', link: 'https://github.com/italiatroller-1990' },
      { icon: 'x', link: 'https://x.com/Italia_Troller_' },
      { icon: 'bluesky', link: 'https://bsky.app/profile/italiatroller.dpdns.org' }
    ]
  },

  markdown: {
    theme: 'github-dark',
    image: {
      lazyLoading: true
    }
  }
})
