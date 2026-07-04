<script src="./ControlsPanel.js"></script>

<template>
  <aside class="panel" :class="{ collapsed, 'filters-active': filtersActive }">
    <header class="panel-head">
      <h1>{{ t('appTitle') }}</h1>
      <button class="toggle" @click="collapsed = !collapsed">
        {{ collapsed ? '▸' : '▾' }}
      </button>
    </header>

    <div v-show="!collapsed" class="panel-body">
      <label class="client-filter">
        {{ t('filterByClient') }}
        <input v-model="filters.client" :placeholder="t('clientPlaceholder')" />
      </label>

      <button class="open-timeline" @click="openTimeline">{{ t('openTimeline') }}</button>

      <div class="legend-head">
        <strong>{{ t('legend') }} / {{ t('filterByType') }}</strong>
        <button class="clear" @click="filters.clear()">{{ t('clearFilters') }}</button>
      </div>

      <ul class="legend">
        <li v-for="category in categories" :key="category.key" class="category">
          <div class="category-row">
            <label class="category-label">
              <input
                type="checkbox"
                :checked="categoryState(category) === 'all'"
                :indeterminate.prop="categoryState(category) === 'some'"
                @change="toggleCategory(category)"
              />
              <span class="swatch" :style="{ background: category.color }"></span>
              <span>{{ catLabel(category) }}</span>
            </label>
            <button
              v-if="!isLeaf(category)"
              class="expand"
              :aria-expanded="!!expanded[category.key]"
              @click="toggleExpanded(category.key)"
            >
              {{ expanded[category.key] ? '▾' : '▸' }}
            </button>
          </div>

          <ul v-show="!isLeaf(category) && expanded[category.key]" class="subtypes">
            <li v-for="key in category.types" :key="key">
              <label>
                <input
                  type="checkbox"
                  :checked="isChecked(key)"
                  @change="filters.toggleUsageType(key)"
                />
                <span class="swatch" :style="{ background: usageColor(key) }"></span>
                <span class="legend-label">{{ label(key) }}</span>
              </label>
            </li>
          </ul>
        </li>
      </ul>

      <div class="lang">
        <span>{{ t('language') }}:</span>
        <button :class="{ active: filters.locale === 'hu' }" @click="setLocale('hu')">HU</button>
        <button :class="{ active: filters.locale === 'en' }" @click="setLocale('en')">EN</button>
      </div>

      <div class="theme">
        <span>{{ t('theme') }}:</span>
        <button :class="{ active: !filters.darkMode }" @click="filters.setTheme('light')">
          {{ t('lightMode') }}
        </button>
        <button :class="{ active: filters.darkMode }" @click="filters.setTheme('dark')">
          {{ t('darkMode') }}
        </button>
      </div>
    </div>
  </aside>
</template>

<style scoped src="./ControlsPanel.css"></style>
