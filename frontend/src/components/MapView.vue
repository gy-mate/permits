<script src="./MapView.js"></script>

<template>
  <div class="map-root">
    <div ref="container" class="map-canvas"></div>
    <div v-if="loading" class="map-loading">{{ t('loading') }}</div>
    <button class="zoom-to-permits" :title="t('zoomToPermits')" @click="zoomToPermits">
      {{ t('zoomToPermits') }}
    </button>
  </div>
</template>

<style scoped src="./MapView.css"></style>
