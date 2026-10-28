const THEME_KEY = 'keystone-theme'

export type Theme = 'light' | 'dark'

export function getStoredTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function storeTheme(theme: Theme) {
  localStorage.setItem(THEME_KEY, theme)
}

export function applyTheme(theme: Theme) {
  document.documentElement.setAttribute('data-theme', theme)
}

export const ROLE_COLORS: Record<string, string> = {
  executive: '#7c3aed',
  manager: '#2563eb',
  hr_partner: '#16a34a',
  finance_analyst: '#d97706',
  sales_rep: '#0d9488',
  individual_contributor: '#6b7280',
  contractor: '#ea580c',
}
