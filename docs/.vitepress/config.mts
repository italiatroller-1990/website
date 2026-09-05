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
  ignoreDeadLinks: true,

  locales: {
    root: {
      label: 'English',
      lang: 'en',
      themeConfig: {
        nav: [
          { text: 'Welcome!', link: '/' },
          { text: 'Lifelogs', link: '/lifelogs/' },
          { text: 'Guides', link: '/guides/' },
          { text: 'Tags', link: '/tags/' },
          { text: 'About me', link: '/about' },
          { text: 'Contact me', link: '/contact' }
        ]
      }
    },
    vi: {
      label: 'Tiếng Việt',
      lang: 'vi',
      themeConfig: {
        nav: [
          { text: 'Chào mừng!', link: '/vi/' },
          { text: 'Nhật ký', link: '/vi/lifelogs/' },
          { text: 'Hướng dẫn', link: '/vi/guides/' },
          { text: 'Thẻ', link: '/vi/tags/' },
          { text: 'Về tôi', link: '/vi/about' },
          { text: 'Liên hệ', link: '/vi/contact' }
        ]
      }
    },
    'es-US': {
      label: 'Español',
      lang: 'es-US',
      themeConfig: {
        nav: [
          { text: '¡Bienvenido!', link: '/es-US/' },
          { text: 'Bitácoras', link: '/es-US/lifelogs/' },
          { text: 'Guías', link: '/es-US/guides/' },
          { text: 'Etiquetas', link: '/es-US/tags/' },
          { text: 'Sobre mí', link: '/es-US/about' },
          { text: 'Contacto', link: '/es-US/contact' }
        ]
      }
    },
    fr: {
      label: 'Français',
      lang: 'fr',
      themeConfig: {
        nav: [
          { text: 'Bienvenue !', link: '/fr/' },
          { text: 'Journal', link: '/fr/lifelogs/' },
          { text: 'Guides', link: '/fr/guides/' },
          { text: 'Tags', link: '/fr/tags/' },
          { text: 'À propos', link: '/fr/about' },
          { text: 'Contact', link: '/fr/contact' }
        ]
      }
    },
    de: {
      label: 'Deutsch',
      lang: 'de',
      themeConfig: {
        nav: [
          { text: 'Willkommen!', link: '/de/' },
          { text: 'Tagebuch', link: '/de/lifelogs/' },
          { text: 'Anleitungen', link: '/de/guides/' },
          { text: 'Tags', link: '/de/tags/' },
          { text: 'Über mich', link: '/de/about' },
          { text: 'Kontakt', link: '/de/contact' }
        ]
      }
    },
    ja: {
      label: '日本語',
      lang: 'ja',
      themeConfig: {
        nav: [
          { text: 'ようこそ！', link: '/ja/' },
          { text: '日記', link: '/ja/lifelogs/' },
          { text: 'ガイド', link: '/ja/guides/' },
          { text: 'タグ', link: '/ja/tags/' },
          { text: '自己紹介', link: '/ja/about' },
          { text: 'お問い合わせ', link: '/ja/contact' }
        ]
      }
    },
    ko: {
      label: '한국어',
      lang: 'ko',
      themeConfig: {
        nav: [
          { text: '환영합니다!', link: '/ko/' },
          { text: '일지', link: '/ko/lifelogs/' },
          { text: '가이드', link: '/ko/guides/' },
          { text: '태그', link: '/ko/tags/' },
          { text: '소개', link: '/ko/about' },
          { text: '연락처', link: '/ko/contact' }
        ]
      }
    }
  },

  themeConfig: {
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
      lazyLoad: true
    }
  }
})
