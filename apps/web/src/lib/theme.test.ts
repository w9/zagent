import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import indexHtml from '../../index.html?raw'
import { readPreference, setPreference, startTheme, themeStorageKey } from './theme'

let osDark = false
const listeners = new Set<() => void>()

function setOs(dark: boolean) {
  osDark = dark
  listeners.forEach((listener) => listener())
}

beforeEach(() => {
  osDark = false
  listeners.clear()
  localStorage.clear()
  delete document.documentElement.dataset.theme
  vi.stubGlobal('matchMedia', () => ({
    get matches() { return osDark },
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  }))
})
afterEach(() => vi.unstubAllGlobals())

const theme = () => document.documentElement.dataset.theme

describe('THEME-01', () => {
  it('defaults to system and follows the OS live', () => {
    const stop = startTheme()
    expect(readPreference()).toBe('system')
    expect(theme()).toBe('light')
    setOs(true)
    expect(theme()).toBe('dark')
    stop()
  })

  it('saves an explicit choice, which overrides the OS until system is chosen again', () => {
    const stop = startTheme()
    setPreference('dark')
    expect(localStorage.getItem(themeStorageKey)).toBe('dark')
    expect(theme()).toBe('dark')
    setOs(false)
    expect(theme()).toBe('dark')
    setPreference('system')
    expect(localStorage.getItem(themeStorageKey)).toBeNull()
    expect(theme()).toBe('light')
    stop()
  })

  it('applies a choice made in another tab', () => {
    const stop = startTheme()
    localStorage.setItem(themeStorageKey, 'dark')
    window.dispatchEvent(new StorageEvent('storage', { key: themeStorageKey }))
    expect(theme()).toBe('dark')
    stop()
  })

  it.each([
    [null, false], [null, true], ['light', true], ['dark', false], ['bogus', true],
  ])('the pre-paint script in index.html agrees with the module (saved %s, OS dark %s)', (saved, dark) => {
    const script = indexHtml.match(/<script>([\s\S]*?)<\/script>/)![1]
    if (saved) localStorage.setItem(themeStorageKey, saved)
    osDark = dark
    new Function(script)()
    const painted = theme()
    startTheme()()
    expect(painted).toBe(theme())
  })
})
