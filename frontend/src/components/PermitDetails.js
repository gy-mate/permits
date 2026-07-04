import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { usageColor } from '../usageCategories'
import { usageLabel } from '../usageTypes'
import { fetchWikimediaCommonsLogoUrl } from '../wikidata'

export default {
  props: { permit: { type: Object, required: true } },
  emits: ['close'],
  setup(props) {
    const { t, locale } = useI18n()
    const logoUrl = ref(null)

    const usageLabelText = computed(() =>
      usageLabel(props.permit.usage_type, locale.value),
    )

    function formatDate(value) {
      return value ? new Date(value).toLocaleDateString(locale.value) : '—'
    }

    // Fetch the client's logo (Wikidata P154) whenever the selected permit changes
    watch(
      () => props.permit.id,
      async () => {
        logoUrl.value = null
        if (props.permit.client_wikidata_id) {
          logoUrl.value = await fetchWikimediaCommonsLogoUrl(props.permit.client_wikidata_id)
        }
      },
      { immediate: true },
    )

    return { t, logoUrl, usageLabelText, usageColor, formatDate }
  },
}
