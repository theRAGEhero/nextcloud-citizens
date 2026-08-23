<script setup lang="ts">
withDefaults(defineProps<{ rows?: number; height?: number }>(), { rows: 3, height: 48 })
</script>

<template>
	<div class="cz-skeleton" aria-busy="true" aria-label="Loading">
		<div
			v-for="row in rows"
			:key="row"
			class="cz-skeleton__row"
			:style="{ height: height + 'px' }"></div>
	</div>
</template>
