<script src="./Timeline.js"></script>

<template>
  <div class="timeline" :class="{ partial: isPartial, future: isFuture }">
    <div class="timeline-head">
      <span>{{ t('timeline') }}</span>
      <span class="date">{{ selected.toLocaleDateString() }}</span>
      <span class="actions">
        <button class="today" @click="resetToToday">{{ t('today') }}</button>
        <button class="close" @click="close">{{ t('close') }}</button>
      </span>
    </div>
    <svg
      v-if="popularityPath"
      class="popularity"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path :d="popularityPath" />
    </svg>
    <input type="range" min="0" :max="STEPS" v-model.number="position" @input="onInput" />
    <div class="year-axis">
      <span
        v-for="tick in yearTicks"
        :key="tick.year"
        class="year-tick"
        :style="{ left: tick.left + '%' }"
      >
        <span v-if="tick.showText">{{ tick.year }}</span>
      </span>
    </div>
    <p v-if="isPartial" class="warning">⚠ {{ t('partialDataWarning') }}</p>
    <p v-else-if="isFuture" class="warning">⚠ {{ t('futureDataWarning') }}</p>
  </div>
</template>

<style scoped src="./Timeline.css"></style>
