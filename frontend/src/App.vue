<script src="./App.js"></script>

<template>
  <div class="app">
    <MapView @select="onSelect" />

    <ControlsPanel />
    <PermitDetails
      v-if="selectedPermits.length"
      :permits="selectedPermits"
      @close="clearSelection"
    />
    
    <Timeline v-if="filters.timelineOpen" />
  </div>
</template>

<style src="./App.css"></style>
