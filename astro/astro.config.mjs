// @ts-check
import { defineConfig } from 'astro/config';

// ─────────────────────────────────────────────────────────────────────────────
// 部署網域切換（只改這一處 + 加 CNAME 即可切換）
//
// 現在：GitHub Pages 專案路徑 https://weiqi-kids.github.io/ctf.works/
export const SITE = 'https://weiqi-kids.github.io';
export const BASE = '/ctf.works';
//
// 之後（自訂網域 ctf.works 就緒後）：把上兩行換成
//   export const SITE = 'https://ctf.works';
//   export const BASE = '/';
// ─────────────────────────────────────────────────────────────────────────────

// https://astro.build/config
export default defineConfig({
  site: SITE,
  base: BASE,
  output: 'static',
  trailingSlash: 'always',
});
