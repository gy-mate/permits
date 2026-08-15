import { computed, defineComponent, watch, type PropType } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Permit } from '../api'
import { usageColor } from '../usageCategories'
import { usageLabel } from '../usageTypes'
import { logoUrls, loadLogoUrl } from '../wikidata'

export default defineComponent({
  props: { permits: { type: Array as PropType<Permit[]>, required: true } },
  emits: ['close'],
  setup(props) {
    const { t, locale } = useI18n()

    const title = computed(() =>
      props.permits.length === 1
        ? props.permits[0]?.reference_number  // A single permit keeps its reference number as the heading
        : t('overlappingPermits', { count: props.permits.length }),  // Overlapping ones' heading shows a count of those permits
    )

    // Wikidata IDs are optional, and a logo may not have loaded (or may not exist)
    function logoUrl(permit: Permit): string | undefined {
      if (!permit.client_wikidata_id) {
        return undefined
      }

      return logoUrls[permit.client_wikidata_id] ?? undefined
    }

    function usageLabelText(permit: Permit): string {
      return usageLabel(permit.usage_type, locale.value)
    }

    function formatDate(value: string | null): string {
      return value ? new Date(value).toLocaleDateString(locale.value) : '—'
    }

    // Fetch each client's logo (Wikidata P154) whenever the selection changes
    watch(
      () => props.permits.map((permit) => permit.id).join(),
      () => props.permits.forEach((permit) => loadLogoUrl(permit.client_wikidata_id)),
      { immediate: true },
    )

    return { t, title, logoUrl, usageLabelText, usageColor, formatDate }
  },
})
