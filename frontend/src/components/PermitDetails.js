import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { usageColor } from '../usageCategories'
import { usageLabel } from '../usageTypes'
import { logoUrls, loadLogoUrl } from '../wikidata'

export default {
  props: { permits: { type: Array, required: true } },
  emits: ['close'],
  setup(props) {
    const { t, locale } = useI18n()

    const title = computed(() =>
      props.permits.length === 1
        ? props.permits[0].reference_number  // A single permit keeps its reference number as the heading
        : t('overlappingPermits', { count: props.permits.length }),  // Overlapping ones' heading shows a count of those permits
    )

    function usageLabelText(permit) {
      return usageLabel(permit.usage_type, locale.value)
    }

    function formatDate(value) {
      return value ? new Date(value).toLocaleDateString(locale.value) : '—'
    }

    // Fetch each client's logo (Wikidata P154) whenever the selection changes
    watch(
      () => props.permits.map((permit) => permit.id).join(),
      () => props.permits.forEach((permit) => loadLogoUrl(permit.client_wikidata_id)),
      { immediate: true },
    )

    return { t, title, logoUrls, usageLabelText, usageColor, formatDate }
  },
}
