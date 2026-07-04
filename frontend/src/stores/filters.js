import { defineStore } from 'pinia'

import { prefersDark } from '../composables/useMapStyle'

// Filters + view preferences. Persisted automatically to localStorage so the
// user's selections survive reloads
export const useFiltersStore = defineStore('filters', {
  state: () => ({
    usageTypes: [],  // An empty array means 'all types'
    client: '',
    locale: 'hu',
    theme: 'system',  // 'light'/'dark' are manual overrides
    systemDark: prefersDark(),
    timelineOpen: false,
    selectedDate: null,  // Today
  }),

  getters: {
    darkMode(state) {
      // Follows the OS when theme is 'system', otherwise the manual override
      return state.theme === 'system' ? state.systemDark : state.theme === 'dark'
    },

    // The day to query for, or null to fetch all dates (timeline open)
    inEffectOn(state) {
      if (state.timelineOpen) {
        return null
      }

      return state.selectedDate ?? new Date().toISOString().slice(0, 10)
    },
  },

  actions: {
    toggleUsageType(key) {
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

    setTheme(value) {
      this.theme = value
    },
  },

  persist: {
    // Persist filters + preferences, but not transient timeline state
    pick: ['usageTypes', 'client', 'locale', 'theme'],
  },
})
