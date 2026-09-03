import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: "Italia Troller's website",
  description: "My personal site for blogs and stuff!",
  head: [
    ['script', {}, `
      window.gtranslateSettings = {
        default_language: "en",
        native_language_names: true,
        detect_browser_language: true,
        wrapper_selector: ".gtranslate_wrapper",
        color_scheme: "light",
        flag_style: "2d",
        flag_size: 24,
        position: "bottom-right",
        float_open_direction: "up",
        wrapper_class: "gtranslate-custom"
      };
    `],
    ['script', { src: 'https://cdn.gtranslate.net/widgets/latest/float.js', defer: '' }],
  ],
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
  }
})
