import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const product = z.object({
  name: z.string(),
  url: z.string().url(),
  image: z.string().url(),
  price: z.string().optional(),
});

const blog = defineCollection({
  loader: glob({ base: './src/content/blog', pattern: '**/*.{md,mdx}' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    pubDate: z.coerce.date(),
    updatedDate: z.coerce.date().optional(),
    heroImage: z.string().url().optional(),
    category: z.string().default('Fashion'),
    tags: z.array(z.string()).default([]),
    products: z.array(product).default([]),
  }),
});

export const collections = { blog };
