import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchCoverage } from '../api'
import { useFiltersStore } from '../stores/filters'

const DAY_MS = 86400000
const STEPS = 1000
// Minimum gap (in % of the timeline width) between two year labels before they
// start to overlap. Roughly a 4-digit label's width on the narrowest layout
const MIN_LABEL_GAP = 7

export default {
  setup() {
    const { t } = useI18n()
    const filters = useFiltersStore()

    const earliestInEffectDate = ref(null)
    const latestInEffectDate = ref(null)

    const earliestQueried = ref(null)  // before this, past data is partial
    const histogram = ref([])  // [{ date: Date, count }] step function of in-effect permits

    const today = new Date()
    today.setHours(0, 0, 0, 0)

    const sliderPosition = ref(STEPS)

    const maxDaysAgo = computed(() =>
      earliestInEffectDate.value ? Math.max(1, Math.round((today - earliestInEffectDate.value) / DAY_MS)) : 1,
    )
    const maxDaysAhead = computed(() =>
      latestInEffectDate.value ? Math.max(0, Math.round((latestInEffectDate.value - today) / DAY_MS)) : 0,
    )

    // Split the slider between a logarithmic past half and a logarithmic future half,
    // proportional to each side's log-extent. `todayFrac` is where "today" sits
    const logPast = computed(() => Math.log10(maxDaysAgo.value + 1))
    const logFuture = computed(() => Math.log10(maxDaysAhead.value + 1))
    const todayFrac = computed(() => {
      const total = logPast.value + logFuture.value
      return total === 0 ? 1 : logPast.value / total
    })

    // Logarithmic both ways: fine resolution near today, coarser into past and future
    function positionToDate(pos) {
      const frac = pos / STEPS
      if (frac <= todayFrac.value) {
        const p = todayFrac.value === 0 ? 0 : (todayFrac.value - frac) / todayFrac.value
        const daysAgo = Math.round(10 ** (p * logPast.value) - 1)
        return new Date(today.getTime() - daysAgo * DAY_MS)
      }

      const p = (frac - todayFrac.value) / (1 - todayFrac.value)
      const daysAhead = Math.round(10 ** (p * logFuture.value) - 1)

      return new Date(today.getTime() + daysAhead * DAY_MS)
    }

    function dateToFraction(date) {
      const days = Math.round((date - today) / DAY_MS)
      if (days <= 0) {
        const p = Math.log10(-days + 1) / logPast.value
        return todayFrac.value * (1 - p)
      }
      const p = Math.log10(days + 1) / logFuture.value
      return todayFrac.value + (1 - todayFrac.value) * p
    }

    // Popularity graph: a stepped area whose height is the in-effect-permit count,
    // with each change point placed on the same logarithmic axis as the slider.
    // Drawn in a 0..100 viewBox (preserveAspectRatio="none" stretches it to width)
    const popularityPath = computed(() => {
      if (!earliestInEffectDate.value || !latestInEffectDate.value || histogram.value.length === 0) {
        return ''
      }

      const peak = histogram.value.reduce((max, p) => Math.max(max, p.count), 0)
      if (peak === 0) {
        return ''
      }

      const points = histogram.value.map((p) => ({
        x: Math.min(100, Math.max(0, dateToFraction(p.date) * 100)),
        y: 100 - (p.count / peak) * 100,
      }))

      // Start on the baseline under the first change point, then for each point
      // hold the previous height across to its x before stepping to the new height
      let d = `M ${points[0].x.toFixed(2)} 100`
      let prevY = 100
      for (const point of points) {
        d += ` L ${point.x.toFixed(2)} ${prevY.toFixed(2)} L ${point.x.toFixed(2)} ${point.y.toFixed(2)}`
        prevY = point.y
      }

      // Extend the last height to the right edge and close down to the baseline
      return `${d} L 100 ${prevY.toFixed(2)} L 100 100 Z`
    })

    // Year ticks (Jan 1 of each year in range), placed on the logarithmic axis
    const yearTicks = computed(() => {
      if (!earliestInEffectDate.value || !latestInEffectDate.value) {
        return []
      }

      const ticks = []
      const startYear = earliestInEffectDate.value.getFullYear()
      const endYear = latestInEffectDate.value.getFullYear()

      for (let year = startYear; year <= endYear; year++) {
        const date = new Date(year, 0, 1)
        if (date < earliestInEffectDate.value || date > latestInEffectDate.value) {
          continue
        }
        const left = dateToFraction(date) * 100
        if (left >= 0 && left <= 100) {
          ticks.push({ year, left, showText: true })
        }
      }
      if (ticks.length === 0) {
        return ticks
      }

      // The tick marks always render; only their text is thinned out when labels
      // would overlap. Anchors that always keep their text: the two ends and the
      // pair straddling the middle of the timeline. The rest are kept greedily,
      // left to right, as long as they clear MIN_LABEL_GAP from the last kept label
      const lastIdx = ticks.length - 1
      let leftMid = -1
      let rightMid = -1
      for (let i = 0; i < ticks.length; i++) {
        if (ticks[i].left <= 50) {
          leftMid = i
        }
        if (rightMid === -1 && ticks[i].left >= 50) {
          rightMid = i
        }
      }
      const forced = new Set([0, lastIdx, leftMid, rightMid].filter((i) => i >= 0))

      let lastLeft = -Infinity
      for (let i = 0; i < ticks.length; i++) {
        if (forced.has(i) || ticks[i].left - lastLeft >= MIN_LABEL_GAP) {
          ticks[i].showText = true
          lastLeft = ticks[i].left
        } else {
          ticks[i].showText = false
        }
      }

      return ticks
    })

    const selected = computed(() => positionToDate(sliderPosition.value))
    const selectedIso = computed(() => selected.value.toISOString().slice(0, 10))

    const isPartial = computed(
      () => earliestQueried.value && selected.value < earliestQueried.value,
    )
    const isFuture = computed(() => selected.value > today)

    function onInput() {
      filters.selectedDate = selectedIso.value
    }

    function resetToToday() {
      sliderPosition.value = Math.round(todayFrac.value * STEPS)
      filters.selectedDate = today.toISOString().slice(0, 10)
    }

    function close() {
      filters.timelineOpen = false
      filters.selectedDate = null
    }

    onMounted(async () => {
      filters.timelineOpen = true  // Opening the timeline queries all dates
      filters.selectedDate = today.toISOString().slice(0, 10)
      try {
        const coverage = await fetchCoverage()

        earliestInEffectDate.value = coverage.earliest_time_from
          ? new Date(coverage.earliest_time_from)
          : new Date(today.getTime() - 365 * DAY_MS)
        earliestInEffectDate.value.setHours(0, 0, 0, 0)

        earliestQueried.value = coverage.earliest_queried_at
          ? new Date(coverage.earliest_queried_at)
          : null

        // Compare by calendar day: a query timestamp partway through its own day
        // must not make that whole day count as "before the earliest query"
        if (earliestQueried.value) {
          earliestQueried.value.setHours(0, 0, 0, 0)
        }

        latestInEffectDate.value = coverage.latest_time_to ? new Date(coverage.latest_time_to) : today
        latestInEffectDate.value.setHours(0, 0, 0, 0)

        histogram.value = (coverage.histogram ?? []).map((point) => {
          const date = new Date(point.date)
          date.setHours(0, 0, 0, 0)
          return { date, count: point.count }
        })

        // Start the thumb at today now that the axis can extend into the future
        sliderPosition.value = Math.round(todayFrac.value * STEPS)
      } catch (error) {
        console.error(error)
      }
    })

    return {
      t,
      STEPS,
      position: sliderPosition,
      selected,
      isPartial,
      isFuture,
      yearTicks,
      popularityPath,
      onInput,
      resetToToday,
      close,
    }
  },
}
