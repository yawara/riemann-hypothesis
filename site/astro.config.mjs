// @ts-check
import { defineConfig, fontProviders } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

// GitHub Pages(https://yawara.github.io/riemann-hypothesis/)向けの静的サイト
export default defineConfig({
  site: 'https://yawara.github.io',
  base: '/riemann-hypothesis',
  fonts: [
    {
      // 見出し用の明朝。npm に入れた @fontsource/shippori-mincho から自前配信する
      provider: fontProviders.npm(),
      name: 'Shippori Mincho',
      cssVariable: '--font-shippori',
      weights: [700],
      styles: ['normal'],
      subsets: ['japanese', 'latin'],
      fallbacks: ['Hiragino Mincho ProN', 'Yu Mincho', 'Noto Serif CJK JP', 'serif'],
    },
  ],
  vite: {
    plugins: [tailwindcss()],
  },
});
