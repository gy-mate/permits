<script src="./PermitDetails.js"></script>

<template>
  <section class="details">
    <div class="details-head">
      <h2>{{ permit.reference_number }}</h2>
      <button class="close" @click="$emit('close')">{{ t('close') }}</button>
    </div>

    <img v-if="logoUrl" :src="logoUrl" :alt="permit.client ?? ''" class="logo" />

    <dl>
      <dt>{{ t('usageType') }}</dt>
      <dd>
        <span class="swatch-inline" :style="{ background: usageColor(permit.usage_type) }"></span>
        {{ usageLabelText }}
      </dd>

      <dt>{{ t('client') }}</dt>
      <dd v-if="permit.client_is_natural_person">{{ t('naturalPerson') }}</dd>
      <dd v-else>{{ permit.client ?? '—' }}</dd>

      <dt>{{ t('area') }}</dt>
      <dd>{{ permit.occupied_area_in_square_metres ?? '—' }} {{ t('squareMetres') }}</dd>

      <dt>{{ t('timeFrom') }}</dt>
      <dd>{{ formatDate(permit.time_from) }}</dd>
      <dt>{{ t('timeTo') }}</dt>
      <dd>{{ formatDate(permit.time_to) }}</dd>

      <dt>{{ t('conscriptionNumber') }}</dt>
      <dd>{{ permit.location_conscription_number ?? '—' }}</dd>

      <dt>{{ t('sourceText') }}</dt>
      <dd>{{ permit.location_source_text ?? '—' }}</dd>

      <dt>{{ t('queriedAt') }}</dt>
      <dd>{{ formatDate(permit.queried_at) }}</dd>
    </dl>
  </section>
</template>

<style scoped src="./PermitDetails.css"></style>
