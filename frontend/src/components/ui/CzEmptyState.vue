<!-- SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
     SPDX-License-Identifier: AGPL-3.0-or-later -->
<script setup lang="ts">
import SvgIcon from './SvgIcon.vue'

defineProps<{ icon: string; title: string; hint?: string }>()
</script>

<template>
	<div class="cz-empty">
		<div class="cz-empty__icon"><SvgIcon :path="icon" :size="44" /></div>
		<h3 class="cz-empty__title">{{ title }}</h3>
		<p v-if="hint" class="cz-empty__hint">{{ hint }}</p>
		<div class="cz-empty__action"><slot /></div>
	</div>
</template>
