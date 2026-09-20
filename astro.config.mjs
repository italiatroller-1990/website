// @ts-check

import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import { defineConfig, fontProviders } from 'astro/config';

// https://astro.build/config
export default defineConfig({
	site: 'https://italiatroller.dpdns.org',
	integrations: [mdx(), sitemap()],
	build: {
		// Inline all CSS (site is small) to eliminate render-blocking
		// stylesheet requests flagged by PageSpeed Insights.
		inlineStylesheets: 'always',
	},
	fonts: [
		{
			provider: fontProviders.local(),
			name: 'inter',
			cssVariable: '--font-inter',
			fallbacks: ['sans-serif'],
			options: {
				variants: [
					{
						src: ['./src/assets/fonts/inter-variable.ttf'],
						weight: 400,
						style: 'normal',
						display: 'swap',
					},
				],
			},
		},
	],
});
