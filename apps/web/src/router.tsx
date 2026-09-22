import {
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import App from './App'

const rootRoute = createRootRoute()
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
