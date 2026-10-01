import { withThemeByDataAttribute } from '@storybook/addon-themes'
import type { Preview } from '@storybook/react-vite'
import '@fontsource-variable/dm-sans'
import '@fontsource/newsreader/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '../src/design/styles.css'
import { axeTags, viewports } from '../src/design/matrix'

const preview: Preview = {
  decorators: [
    withThemeByDataAttribute({ themes: { light: 'light', dark: 'dark' }, defaultTheme: 'light', attributeName: 'data-theme' }),
  ],
  parameters: {
    layout: 'padded',
    backgrounds: { disable: true },
    viewport: {
      options: Object.fromEntries(
        viewports.map(({ name, width, height }) => [
          name,
          { name, styles: { width: `${width}px`, height: `${height}px` }, type: width < 1280 ? 'mobile' : 'desktop' },
        ]),
      ),
    },
    a11y: { options: { runOnly: { type: 'tag', values: axeTags } } },
  },
}

export default preview
