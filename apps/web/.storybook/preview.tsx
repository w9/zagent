import { withThemeByDataAttribute } from '@storybook/addon-themes'
import type { Decorator, Preview } from '@storybook/react-vite'
import {
  RouterContextProvider,
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import '@fontsource-variable/dm-sans'
import '@fontsource/newsreader/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '../src/design/styles.css'
import { axeTags, viewports } from '../src/design/matrix'

// Links need a router. It sits at / so no session link is active unless a story says so.
const root = createRootRoute()
const router = createRouter({
  routeTree: root.addChildren([createRoute({ getParentRoute: () => root, path: '/sessions/$sessionId' })]),
  history: createMemoryHistory({ initialEntries: ['/'] }),
})

const withProviders: Decorator = (Story) => (
  <RouterContextProvider router={router}>
    <Story />
  </RouterContextProvider>
)

const preview: Preview = {
  decorators: [
    withProviders,
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
