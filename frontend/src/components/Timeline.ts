import { computed, defineComponent, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { fetchCoverage } from '../api'
import { useFiltersStore } from '../stores/filters'

const DAY_MS = 86400000
const STEPS = 1000
// Minimum gap (in % of the timeline width) between two year labels before they
// start to overlap. Roughly a 4-digit label's width on the narrowest layout
const MIN_LABEL_GAP = 7

// A change point in the in-effect-permit count, with its date already normalized to
// local midnight so it lines up with the slider's day boundaries
interface HistogramPoint {
  date: Date
  count: number
}

interface YearTick {
  year: number
  left: number
  showText: boolean
}

export default defineComponent({
  setup() {
    const { t } = useI18n()
    const filters = useFiltersStore()

    const earliestInEffectDate = ref<Date | null>(null)
    const latestInEffectDate = ref<Date | null>(null)

    const earliestQueried = ref<Date | null>(null)  // before this, past data is partial
    const histogram = ref<HistogramPoint[]>([])  // step function of in-effect permits

    const today = new Date()
    today.setHours(0, 0, 0, 0)

    const sliderPosition = ref(STEPS)

    const maxDaysAgo = computed(() => {
      const earliest = earliestInEffectDate.value
      return earliest ? Math.max(1, Math.round((today.getTime() - earliest.getTime()) / DAY_MS)) : 1
    })
    const maxDaysAhead = computed(() => {
      const latest = latestInEffectDate.value
      return latest ? Math.max(0, Math.round((latest.getTime() - today.getTime()) / DAY_MS)) : 0
    })

    // Split the slider between a logarithmic past half and a logarithmic future half,
    // proportional to each side's log-extent. `todayFrac` is where "today" sits
    const logPast = computed(() => Math.log10(maxDaysAgo.value + 1))
    const logFuture = computed(() => Math.log10(maxDaysAhead.value + 1))
    const todayFrac = computed(() => {
      const total = logPast.value + logFuture.value
      return total === 0 ? 1 : logPast.value / total
    })

    // Logarithmic both ways: fine resolution near today, coarser into past and future
    function positionToDate(pos: number): Date {
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

    function dateToFraction(date: Date): number {
      const days = Math.round((date.getTime() - today.getTime()) / DAY_MS)
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

      const first = points[0]
      if (!first) {
        return ''
      }

      // Start on the baseline under the first change point, then for each point
      // hold the previous height across to its x before stepping to the new height
      let d = `M ${first.x.toFixed(2)} 100`
      let prevY = 100
      for (const point of points) {
        d += ` L ${point.x.toFixed(2)} ${prevY.toFixed(2)} L ${point.x.toFixed(2)} ${point.y.toFixed(2)}`
        prevY = point.y
      }

      // Extend the last height to the right edge and close down to the baseline
      return `${d} L 100 ${prevY.toFixed(2)} L 100 100 Z`
    })

    // Year ticks (Jan 1 of each year in range), placed on the logarithmic axis
    const yearTicks = computed<YearTick[]>(() => {
      const earliest = earliestInEffectDate.value
      const latest = latestInEffectDate.value
      if (!earliest || !latest) {
        return []
      }

      const ticks: YearTick[] = []
      const startYear = earliest.getFullYear()
      const endYear = latest.getFullYear()

      for (let year = startYear; year <= endYear; year++) {
        const date = new Date(year, 0, 1)
        if (date < earliest || date > latest) {
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
      for (const [index, tick] of ticks.entries()) {
        if (tick.left <= 50) {
          leftMid = index
        }
        if (rightMid === -1 && tick.left >= 50) {
          rightMid = index
        }
      }
      const forced = new Set([0, lastIdx, leftMid, rightMid].filter((i) => i >= 0))

      let lastLeft = -Infinity
      for (const [index, tick] of ticks.entries()) {
        if (forced.has(index) || tick.left - lastLeft >= MIN_LABEL_GAP) {
          tick.showText = true
          lastLeft = tick.left
        } else {
          tick.showText = false
        }
      }

      return ticks
    })

    const selected = computed(() => positionToDate(sliderPosition.value))
    const selectedIso = computed(() => selected.value.toISOString().slice(0, 10))

    const isPartial = computed(
      () => !!earliestQueried.value && selected.value < earliestQueried.value,
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

        const earliest = coverage.earliest_time_from
          ? new Date(coverage.earliest_time_from)
          : new Date(today.getTime() - 365 * DAY_MS)
        earliest.setHours(0, 0, 0, 0)
        earliestInEffectDate.value = earliest

        // Compare by calendar day: a query timestamp partway through its own day
        // must not make that whole day count as "before the earliest query"
        const queried = coverage.earliest_queried_at
          ? new Date(coverage.earliest_queried_at)
          : null
        queried?.setHours(0, 0, 0, 0)
        earliestQueried.value = queried

        const latest = coverage.latest_time_to ? new Date(coverage.latest_time_to) : today
        latest.setHours(0, 0, 0, 0)
        latestInEffectDate.value = latest

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
})
