import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const lifelogs = defineCollection({
	loader: glob({ base: './src/content/lifelogs', pattern: '**/*.md' }),
	schema: ({ image }) =>
		z.object({
			title: z.string(),
			description: z.string(),
			pubDate: z.coerce.date(),
			tags: z.array(z.string()).optional(),
			heroImage: z.optional(image()),
		}),
});

const guides = defineCollection({
	loader: glob({ base: './src/content/guides', pattern: '**/*.md' }),
	schema: ({ image }) =>
		z.object({
			title: z.string(),
			description: z.string(),
			pubDate: z.coerce.date(),
			tags: z.array(z.string()).optional(),
			heroImage: z.optional(image()),
		}),
});

export const collections = { lifelogs, guides };
