import { computed, defineComponent, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Locale } from '../i18n'
import { useFiltersStore } from '../stores/filters'
import { categoryLabel, usageColor, USAGE_CATEGORIES, type UsageCategory } from '../usageCategories'
import { usageLabel } from '../usageTypes'

// How many of a category's types are selected
type CategoryState = 'all' | 'some' | 'none'

export default defineComponent({
  setup() {
    const { t, locale } = useI18n()

    const filters = useFiltersStore()
    const collapsed = ref(false)
    const expanded = reactive<Record<string, boolean>>({})  // Which category rows are expanded to reveal their subcategories

    locale.value = filters.locale  // Keep the i18n locale in sync with the persisted store value

    function setLocale(value: Locale) {
      filters.locale = value
      locale.value = value
    }

    function label(key: string): string {
      return usageLabel(key, locale.value)
    }

    function catLabel(category: UsageCategory): string {
      return categoryLabel(category, locale.value)
    }

    const categories = computed<UsageCategory[]>(() =>
      [...USAGE_CATEGORIES]
        .map((category) => ({
          ...category,
          types: [...category.types].sort((a, b) => label(a).localeCompare(label(b))),
        }))
        .sort((a, b) => {
          // Keep "Other" pinned to the end; sort the rest by localized label
          if (a.key === 'other') return 1
          if (b.key === 'other') return -1
          return catLabel(a).localeCompare(catLabel(b))
        }),
    )

    // A category with a single subcategory is shown as a plain (non-expandable) row
    function isLeaf(category: UsageCategory): boolean {
      return category.types.length === 1
    }

    function isChecked(key: string): boolean {
      return filters.usageTypes.includes(key)
    }

    function toggleExpanded(key: string) {
      expanded[key] = !expanded[key]
    }

    function categoryState(category: UsageCategory): CategoryState {
      const selected = category.types.filter((key) => isChecked(key)).length
      if (selected === 0) {
        return 'none'
      }
      return selected === category.types.length ? 'all' : 'some'
    }

    // Selecting a category selects all its subcategories; toggling off clears them
    function toggleCategory(category: UsageCategory) {
      if (categoryState(category) === 'all') {
        for (const key of category.types) {
          if (isChecked(key)) filters.toggleUsageType(key)
        }
      } else {
        for (const key of category.types) {
          if (!isChecked(key)) filters.toggleUsageType(key)
        }
      }
    }

    const filtersActive = computed(
      () => filters.usageTypes.length > 0 || filters.client.trim() !== '',
    )

    function openTimeline() {
      filters.timelineOpen = true
    }

    return {
      t,
      filters,
      collapsed,
      expanded,
      categories,
      usageColor,
      label,
      catLabel,
      isChecked,
      isLeaf,
      toggleExpanded,
      categoryState,
      toggleCategory,
      filtersActive,
      setLocale,
      openTimeline,
    }
  },
})
