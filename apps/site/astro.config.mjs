// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  site: 'https://anzelfein.com',
  integrations: [sitemap({ filter: (page) => !page.endsWith('/404/') })],
  vite: {
    plugins: [tailwindcss()],
  },
});
