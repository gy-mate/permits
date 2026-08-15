import { AttributionControl, Map as MapLibreMap, NavigationControl, setWorkerUrl } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { bbox } from '@turf/bbox'

import { fetchPermits } from '../api'
import { loadStyle } from '../composables/useMapStyle'
import { bboxCenter, bboxContains, bufferBbox, pixelSize } from '../geometry'
import { splitByCoverage } from '../overlaps'
import { useFiltersStore } from '../stores/filters'
import { FILL_OPACITY, stripeAngle, stripePatternId, stripePatternImage } from '../stripePattern'
import { usageColor } from '../usageCategories'
import { usageLabel } from '../usageTypes'

setWorkerUrl(workerUrl)  // MapLibre v6 leaves worker hosting to the bundler

const BUDAPEST_CITY_HALL_COORDINATES = [19.0567, 47.4969]
const BUDAPEST_CITY_HALL_ZOOM = 15
const SMALL_PX = 40  // Below this on-screen size a permit is drawn as a point
const BUFFER_FACTOR = 1  // Fetch a bbox this many viewport-widths larger on each side
const INTERACTIVE_LAYERS = ['permit-fill', 'permit-overlap', 'permit-point', 'permit-cluster']
const VIEW_STORAGE_KEY = 'permits.mapView'  // Persisted center/zoom across reloads
const POLYGON_TYPES = new Set(['Polygon', 'MultiPolygon'])

function emptyFC() {
  return { type: 'FeatureCollection', features: [] }
}

// Restore the last map center/zoom from localStorage, or fall back to City Hall
function loadSavedView() {
  try {
    const saved = JSON.parse(localStorage.getItem(VIEW_STORAGE_KEY))
    if (saved && Array.isArray(saved.center) && typeof saved.zoom === 'number') {
      return saved
    }
  } catch {
    // ignore malformed storage
  }

  return { center: BUDAPEST_CITY_HALL_COORDINATES, zoom: BUDAPEST_CITY_HALL_ZOOM }
}

function saveView(map) {
  const center = map.getCenter()
  localStorage.setItem(
    VIEW_STORAGE_KEY,
    JSON.stringify({ center: [center.lng, center.lat], zoom: map.getZoom() }),
  )
}

// Drop the per-source attributions baked into the style so the only credit line is
// our localized `customAttribution` on the AttributionControl — which lets us swap
// languages by replacing just that control, without reloading the whole style
function stripAttribution(style) {
  for (const source of Object.values(style.sources ?? {})) {
    if ('attribution' in source) {
      source.attribution = ''
    }
  }

  return style
}

export default {
  emits: ['select'],
  setup(_props, { emit }) {
    const { t, locale } = useI18n()
    const filters = useFiltersStore()

    const container = ref(null)
    const loading = ref(false)

    let map = null
    let permits = []  // Raw permit objects for the current loaded bbox
    let boxes = new Map()  // Permit ID → geometry bbox; see indexPermits()
    let coverage = []  // `permits` cut into disjoint fill cells; see indexPermits()
    let loadedBbox = null
    let abort = null

    function localizedUsage(key) {
      return usageLabel(key, locale.value)
    }

    // Label for large polygons: client name, or the permit type for natural persons
    function featureLabel(permit, px, viewportMin) {
      if (px >= viewportMin * 0.9) {  // Fills (almost) the whole screen
        return ''  // Omit the label
      }

      if (permit.client_is_natural_person) {
        return localizedUsage(permit.usage_type)
      }

      return permit.client ?? ''
    }

    function passesFilters(permit) {
      if (filters.usageTypes.length && !filters.usageTypes.includes(permit.usage_type)) {
        return false
      }

      if (filters.client) {
        const needle = filters.client.toLowerCase()
        if (!(permit.client ?? '').toLowerCase().includes(needle)) {
          return false
        }
      }

      // With the timeline open we fetch all dates, then filter to the selected day
      // client-side so dragging is instant (ISO date strings compare lexically)
      if (filters.timelineOpen && filters.selectedDate) {
        const day = filters.selectedDate
        const from = permit.time_from?.slice(0, 10)
        const to = permit.time_to?.slice(0, 10)

        if (from && from > day) {
          return false
        }

        if (to && to < day) {
          return false
        }
      }

      return true
    }

    // Register the striped pattern for a colour combination the first time it is needed
    // (the style keeps images across rebuilds, but drops them on a setStyle())
    function stripePattern(colors, angle) {
      const id = stripePatternId(colors, angle)

      if (!map.hasImage(id)) {
        const { image, pixelRatio } = stripePatternImage(colors, angle)
        map.addImage(id, image, { pixelRatio })
      }

      return id
    }

    // Everything derived from the permits' geometry rather than from the current view.
    // Cutting the areas into disjoint cells — so an overlap is painted once, striped
    // with the colours of every permit covering it, instead of stacking translucent
    // fills — is by far the most expensive step on the map, and redoing it on every
    // zoom would stall it. Both results hold until the permits are refetched
    function indexPermits() {
      boxes = new Map(
        permits
          .filter((permit) => permit.location)
          .map((permit) => [permit.id, bbox(permit.location)]),
      )
      coverage = splitByCoverage(
        permits
          .filter((permit) => POLYGON_TYPES.has(permit.location?.type))
          .map((permit) => ({ id: permit.id, geometry: permit.location })),
      ).map((cell) => ({ ...cell, angle: stripeAngle(cell.geometry) }))
    }

    // Turn the cells into fill features for the permits currently drawn as areas. Cells
    // are cut for every loaded permit, so the ids of those filtered out — or small
    // enough to be drawn as a point — are dropped here rather than by recutting
    function coverageCells(colorById) {
      const features = []

      for (const { geometry, ids, angle } of coverage) {
        const shown = ids.filter((id) => colorById.has(id))

        if (!shown.length) {
          continue
        }

        const colors = [...new Set(shown.map((id) => colorById.get(id)))]
        const properties = { ids: JSON.stringify(shown), color: colors[0] }

        if (shown.length > 1) {
          properties.pattern = stripePattern(colors, angle)
        }

        features.push({ type: 'Feature', geometry, properties })
      }

      return features
    }

    // Split the loaded permits into large polygons and small/point features
    function buildSources() {
      const polygons = []
      const points = []
      const colorById = new Map()  // Permits drawn as areas, so their cells get filled

      const viewportMin = Math.min(
        container.value.clientWidth,
        container.value.clientHeight,
      )

      for (const permit of permits) {
        if (!permit.location || !passesFilters(permit)) {
          continue
        }

        const color = usageColor(permit.usage_type)
        const bbox_value = boxes.get(permit.id)
        const px = pixelSize(map, bbox_value)
        const isPolygon = POLYGON_TYPES.has(permit.location.type)  // Only true areas can be cut against each other, so anything else falls through to the point branch below

        if (isPolygon && px >= SMALL_PX) {
          colorById.set(permit.id, color)
          polygons.push({
            type: 'Feature',
            geometry: permit.location,
            properties: { id: permit.id, color, label: featureLabel(permit, px, viewportMin) },
          })
        } else {
          points.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: bboxCenter(bbox_value) },
            properties: { id: permit.id, color },
          })
        }
      }

      map.getSource('permit-polygons')?.setData({ type: 'FeatureCollection', features: polygons })
      map.getSource('permit-points')?.setData({ type: 'FeatureCollection', features: points })
      map.getSource('permit-areas')?.setData({
        type: 'FeatureCollection',
        features: coverageCells(colorById),
      })
    }

    // Idempotent: setStyle() (on a dark-mode switch) drops our sources/layers, so this
    // runs again afterwards and must not re-add anything that's still present
    function addLayers() {
      if (map.getLayer('permit-fill')) {
        return
      }

      map.addSource('permit-polygons', { type: 'geojson', data: emptyFC() })
      map.addSource('permit-areas', { type: 'geojson', data: emptyFC() })  // The polygons cut into disjoint cells: the fills, unlike the outlines and labels, have to know which permits cover each patch
      map.addSource('permit-points', {
        type: 'geojson',
        data: emptyFC(),
        cluster: true,
        clusterRadius: 44,
      })

      map.addLayer({
        id: 'permit-fill',
        type: 'fill',
        source: 'permit-areas',
        filter: ['!', ['has', 'pattern']],
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': FILL_OPACITY },
      })
      map.addLayer({
        id: 'permit-overlap',
        type: 'fill',
        source: 'permit-areas',
        filter: ['has', 'pattern'],
        paint: { 'fill-pattern': ['image', ['get', 'pattern']] },  // The tile is already translucent where the stripes are; its separators are meant to stay opaque black
      })
      map.addLayer({
        id: 'permit-outline',
        type: 'line',
        source: 'permit-polygons',
        paint: { 'line-color': ['get', 'color'], 'line-width': 1.5 },
      })
      map.addLayer({
        id: 'permit-label',
        type: 'symbol',
        source: 'permit-polygons',
        filter: ['!=', ['get', 'label'], ''],
        layout: {
          'text-field': ['get', 'label'],
          'text-font': ['noto_sans_regular'],
          'text-size': 12,
          'text-allow-overlap': false,
        },
        paint: { 'text-color': '#111', 'text-halo-color': '#fff', 'text-halo-width': 1.2 },
      })

      // Small permits and Point geometries, clustered into a counter when dense
      map.addLayer({
        id: 'permit-cluster',
        type: 'circle',
        source: 'permit-points',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': '#5b6470',
          'circle-radius': ['step', ['get', 'point_count'], 14, 10, 18, 50, 24],
          'circle-opacity': 0.9,
        },
      })
      map.addLayer({
        id: 'permit-cluster-count',
        type: 'symbol',
        source: 'permit-points',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': ['get', 'point_count_abbreviated'],
          'text-font': ['noto_sans_bold'],
          'text-size': 12,
        },
        paint: { 'text-color': '#fff' },
      })
      map.addLayer({
        id: 'permit-point',
        type: 'circle',
        source: 'permit-points',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': ['get', 'color'],
          'circle-radius': 10,
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1.5,
        },
      })
    }

    // Zoom to the bbox of all currently shown permits, or to City Hall if there are none
    function zoomToPermits() {
      let minX = Infinity
      let minY = Infinity
      let maxX = -Infinity
      let maxY = -Infinity

      for (const permit of permits) {
        if (!permit.location || !passesFilters(permit)) {
          continue
        }

        const [aX, aY, bX, bY] = boxes.get(permit.id)

        if (aX < minX) minX = aX
        if (aY < minY) minY = aY
        if (bX > maxX) maxX = bX
        if (bY > maxY) maxY = bY
      }

      if (minX === Infinity) {
        map.easeTo({ center: BUDAPEST_CITY_HALL_COORDINATES, zoom: BUDAPEST_CITY_HALL_ZOOM })
        return
      }

      map.fitBounds(
        [
          [minX, minY],
          [maxX, maxY],
        ],
        { padding: 60, maxZoom: 17 },
      )
    }

    async function refetch() {
      const bounds = map.getBounds()
      const viewBbox = [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]

      // Skip the round-trip while the view stays within the already-loaded bbox
      if (loadedBbox && bboxContains(loadedBbox, viewBbox)) {
        return
      }

      const queryBbox = bufferBbox(viewBbox, BUFFER_FACTOR)
      abort?.abort()
      abort = new AbortController()
      loading.value = true

      try {
        permits = await fetchPermits(queryBbox, {
          inEffectOn: filters.inEffectOn,
          signal: abort.signal,
        })
        loadedBbox = queryBbox
        indexPermits()
        buildSources()
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error(error)
        }
      } finally {
        loading.value = false
      }
    }

    function onClickFeature(event) {
      const feature = event.features?.[0]

      if (!feature) {
        return
      }

      if (feature.properties.point_count) {
        map.easeTo({ center: feature.geometry.coordinates, zoom: map.getZoom() + 2 })
        return
      }

      // A fill cell carries every permit covering it, so clicking an overlap selects all of them at once; points always stand for a single permit
      const ids = feature.properties.ids
        ? JSON.parse(feature.properties.ids)
        : [feature.properties.id]
      const selected = ids
        .map((id) => permits.find((permit) => permit.id === id))
        .filter(Boolean)

      if (selected.length) {
        emit('select', selected)
      }
    }

    let attributionControl = null

    async function styledMap() {
      return stripAttribution(await loadStyle(filters.darkMode))
    }

    function addAttributionControl() {
      attributionControl = new AttributionControl({
        compact: true,
        customAttribution: t('attribution'),
      })
      map.addControl(attributionControl, 'bottom-right')
    }

    onMounted(async () => {
      const view = loadSavedView()

      map = new MapLibreMap({
        container: container.value,
        style: await styledMap(),
        center: view.center,
        zoom: view.zoom,
        attributionControl: false,
      })
      map.addControl(new NavigationControl(), 'top-left')
      addAttributionControl()

      map.on('load', () => {
        addLayers()
        refetch()
      })
      map.on('moveend', () => {
        saveView(map)
        refetch()
      })
      map.on('zoomend', buildSources) // Reclassify polygon vs point without refetching

      for (const layer of INTERACTIVE_LAYERS) {
        map.on('click', layer, onClickFeature)
        map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
        map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
      }
    })

    // Switching language only changes the credit line — swap the attribution control
    // instead of reloading the whole style (which would flash the basemap)
    watch(locale, () => {
      if (!map) return
      map.removeControl(attributionControl)
      addAttributionControl()
    })

    // Dark mode swaps the basemap style; re-add our layers once the new style loads
    watch(
      () => filters.darkMode,
      async () => {
        if (!map) return
        map.setStyle(await styledMap())
        map.once('styledata', () => {
          addLayers()
          buildSources()
        })
      },
    )

    onBeforeUnmount(() => {
      map?.remove()
    })

    // Re-render on filter changes (client-side); refetch when the queried day changes
    watch(
      () => [filters.usageTypes.slice(), filters.client, filters.selectedDate],
      () => map && buildSources(),
      { deep: true },
    )
    watch(
      () => filters.inEffectOn,
      () => {
        loadedBbox = null
        if (map) refetch()
      },
    )

    return { container, loading, t, zoomToPermits }
  },
}
