import { useSyncExternalStore } from 'react'

// THEME-01. index.html repeats the resolution inline so the first paint already has the right theme.
export type ThemePreference = 'light' | 'dark' | 'system'
export type Theme = 'light' | 'dark'

export const themeStorageKey = 'zagent.theme'
const darkQuery = '(prefers-color-scheme: dark)'
const preferenceListeners = new Set<() => void>()

export function readPreference(): ThemePreference {
  try {
    const saved = localStorage.getItem(themeStorageKey)
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system'
  }
}

function apply(preference = readPreference()) {
  const dark = preference === 'dark' || (preference === 'system' && matchMedia(darkQuery).matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  preferenceListeners.forEach((listener) => listener())
}

export function setPreference(preference: ThemePreference) {
  try {
    if (preference === 'system') localStorage.removeItem(themeStorageKey)
    else localStorage.setItem(themeStorageKey, preference)
  } catch {
    // Storage can be unavailable; the choice still applies to this page.
  }
  apply(preference)
}

/** Applies the saved preference and keeps `system` in step with the OS and other tabs. */
export function startTheme(): () => void {
  apply()
  const media = matchMedia(darkQuery)
  const onChange = () => apply()
  const onStorage = (event: StorageEvent) => {
    if (event.key === themeStorageKey) apply()
  }
  media.addEventListener('change', onChange)
  window.addEventListener('storage', onStorage)
  return () => {
    media.removeEventListener('change', onChange)
    window.removeEventListener('storage', onStorage)
  }
}

function subscribePreference(listener: () => void) {
  preferenceListeners.add(listener)
  return () => preferenceListeners.delete(listener)
}

export function usePreference(): ThemePreference {
  return useSyncExternalStore(subscribePreference, readPreference, () => 'system')
}

function subscribeTheme(listener: () => void) {
  const observer = new MutationObserver(listener)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  return () => observer.disconnect()
}

/** The theme on <html>, whoever set it. For code that reads tokens at runtime (charts, MCP apps). */
export function useTheme(): Theme {
  return useSyncExternalStore(
    subscribeTheme,
    () => (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'),
    () => 'light',
  )
}
