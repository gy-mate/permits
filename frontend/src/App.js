import { onUnmounted, ref, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'

import ControlsPanel from './components/ControlsPanel.vue'
import MapView from './components/MapView.vue'
import PermitDetails from './components/PermitDetails.vue'
import Timeline from './components/Timeline.vue'
import { useFiltersStore } from './stores/filters'

export default {
  components: { MapView, ControlsPanel, PermitDetails, Timeline },
  setup() {
    const filters = useFiltersStore()
    const { t } = useI18n()
    const selectedPermit = ref(null)

    // Keep the document title localized
    watchEffect(() => {
      document.title = t('appTitle')
    })

    // Keep the OS color-scheme preference in sync so that the 'system' theme
    // follows the system setting live, without a reload
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const onSystemChange = (event) => {
      filters.systemDark = event.matches
    }

    media?.addEventListener('change', onSystemChange)
    onUnmounted(() => media?.removeEventListener('change', onSystemChange))

    // Reflect the resolved dark-mode preference on <html> so the global CSS can theme the UI
    watchEffect(() => {
      document.documentElement.classList.toggle('dark', filters.darkMode)
    })

    function onSelect(permit) {
      selectedPermit.value = permit
    }

    function clearSelection() {
      selectedPermit.value = null
    }

    return { filters, selectedPermit, onSelect, clearSelection }
  },
}
