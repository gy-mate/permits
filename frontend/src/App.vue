<script src="./App.js"></script>

<template>
  <div class="app">
    <MapView @select="onSelect" />

    <ControlsPanel />
    <PermitDetails
      v-if="selectedPermit"
      :permit="selectedPermit"
      @close="clearSelection"
    />
    
    <Timeline v-if="filters.timelineOpen" />
  </div>
</template>

<style src="./App.css"></style>
