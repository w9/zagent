import type { Meta, StoryObj } from '@storybook/react-vite'
import { Specimen } from './specimen'

const meta = {
  title: 'Design system/Tokens',
  component: Specimen,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof Specimen>

export default meta

export const Overview: StoryObj<typeof meta> = {}
