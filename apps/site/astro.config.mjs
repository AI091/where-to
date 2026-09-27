// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  site: 'https://anzelfein.com',
  // Draft builds get their own folder so `wrangler deploy` (which ships dist/) can never publish them.
  outDir: process.env.DRAFTS === '1' ? './dist-drafts' : './dist',
  integrations: [sitemap({ filter: (page) => !page.endsWith('/404/') })],
  vite: {
    plugins: [tailwindcss()],
  },
});
