import { defineConfig } from '@playwright/test'

const port = Number(process.env.ZAGENT_STORYBOOK_TEST_PORT ?? 6107)

// Serves the static Storybook built by `npm run build:storybook`.
export default defineConfig({
  testDir: './scripts/design',
  testMatch: 'visual.spec.ts',
  snapshotPathTemplate: '.design-baselines/{arg}{ext}',
  outputDir: 'test-results/design',
  fullyParallel: true,
  reporter: 'list',
  // Any changed pixel fails; the per-pixel colour threshold absorbs anti-aliasing noise.
  expect: { toHaveScreenshot: { maxDiffPixels: 0 } },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    browserName: 'chromium',
    reducedMotion: 'reduce',
    deviceScaleFactor: 1,
  },
  webServer: {
    command: `npx vite preview --outDir storybook-static --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}/index.json`,
    reuseExistingServer: false,
  },
})
