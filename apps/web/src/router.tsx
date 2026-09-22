import {
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import App from './App'

const rootRoute = createRootRoute({
  validateSearch: (
    search: Record<string, unknown>,
  ): { view?: string; panel?: 'surface' } => ({
    view: typeof search.view === 'string' ? search.view : undefined,
    panel: search.panel === 'surface' ? 'surface' : undefined,
  }),
})
const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: App,
})
const sessionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/sessions/$sessionId',
  component: App,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute, sessionRoute]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
