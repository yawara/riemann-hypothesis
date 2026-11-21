// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// GitHub Pages(https://yawara.github.io/riemann-hypothesis/)向けの静的サイト
export default defineConfig({
  site: 'https://yawara.github.io',
  base: '/riemann-hypothesis',
  vite: {
    plugins: [tailwindcss()],
  },
});
