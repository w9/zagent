import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import '@fontsource-variable/dm-sans'
import '@fontsource/newsreader/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import './design/styles.css'
import { startTheme } from './lib/theme'
import { router } from './router'

startTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
