<!-- SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
     SPDX-License-Identifier: AGPL-3.0-or-later -->
<script setup lang="ts">
withDefaults(defineProps<{ path: string; size?: number }>(), { size: 20 })
</script>

<template>
	<svg
		class="cz-svgicon"
		:width="size"
		:height="size"
		viewBox="0 0 24 24"
		fill="currentColor"
		aria-hidden="true">
		<path :d="path" />
	</svg>
</template>

<style scoped>
.cz-svgicon {
	flex-shrink: 0;
	vertical-align: -0.22em;
}
</style>
