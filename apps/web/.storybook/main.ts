import type { StorybookConfig } from '@storybook/react-vite'

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.tsx'],
  addons: ['@storybook/addon-a11y', '@storybook/addon-themes'],
  framework: '@storybook/react-vite',
  core: { disableTelemetry: true },
}

export default config
