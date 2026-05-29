import { defineCollection, z } from 'astro:content';

const blog = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    date: z.coerce.date(),
    image: z.string().optional(),
    tags: z.array(z.string()).default([]),
    vk_post_id: z.number().optional(),
    vk_channel: z.enum(['vezemcyp', 'podvorye']).default('vezemcyp'),
    draft: z.boolean().default(false),
  }),
});

export const collections = { blog };
