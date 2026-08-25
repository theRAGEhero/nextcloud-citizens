<!-- SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
     SPDX-License-Identifier: AGPL-3.0-or-later -->
<script setup lang="ts">
import SvgIcon from './SvgIcon.vue'

withDefaults(
	defineProps<{
		variant?: 'primary' | 'secondary' | 'danger' | 'tertiary'
		icon?: string
		small?: boolean
		disabled?: boolean
		wide?: boolean
	}>(),
	{ variant: 'secondary', icon: '', small: false, disabled: false, wide: false },
)
</script>

<template>
	<button
		class="cz-btn"
		:class="[`cz-btn--${variant}`, { 'cz-btn--small': small, 'cz-btn--wide': wide }]"
		:disabled="disabled"
		type="button">
		<SvgIcon v-if="icon" :path="icon" :size="small ? 16 : 18" />
		<span class="cz-btn__label"><slot /></span>
	</button>
</template>
