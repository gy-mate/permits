import { defineStore } from 'pinia'

import { prefersDark } from '../composables/useMapStyle'
import type { Locale } from '../i18n'

export type Theme = 'system' | 'light' | 'dark'

export interface FiltersState {
  usageTypes: string[]  // An empty array means 'all types'
  client: string
  locale: Locale
  theme: Theme  // 'light'/'dark' are manual overrides
  systemDark: boolean
  timelineOpen: boolean
  selectedDate: string | null  // Today
}

// Filters + view preferences. Persisted automatically to localStorage so the
// user's selections survive reloads
export const useFiltersStore = defineStore('filters', {
  state: (): FiltersState => ({
    usageTypes: [],
    client: '',
    locale: 'hu',
    theme: 'system',
    systemDark: prefersDark(),
    timelineOpen: false,
    selectedDate: null,
  }),

  getters: {
    darkMode(state): boolean {
      // Follows the OS when theme is 'system', otherwise the manual override
      return state.theme === 'system' ? state.systemDark : state.theme === 'dark'
    },

    // The day to query for, or null to fetch all dates (timeline open)
    inEffectOn(state): string | null {
      if (state.timelineOpen) {
        return null
      }

      return state.selectedDate ?? new Date().toISOString().slice(0, 10)
    },
  },

  actions: {
    toggleUsageType(key: string) {
      const index = this.usageTypes.indexOf(key)

      if (index === -1) {
        this.usageTypes.push(key)
      } else {
        this.usageTypes.splice(index, 1)
      }
    },

    clear() {
      this.usageTypes = []
      this.client = ''
    },

    setTheme(value: Theme) {
      this.theme = value
    },
  },

  persist: {
    // Persist filters + preferences, but not transient timeline state
    pick: ['usageTypes', 'client', 'locale', 'theme'],
  },
})
