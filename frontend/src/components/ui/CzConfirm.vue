<!-- SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
     SPDX-License-Identifier: AGPL-3.0-or-later -->
<script setup lang="ts">
import { mdiAlert } from '@mdi/js'
import CzButton from './CzButton.vue'
import SvgIcon from './SvgIcon.vue'

withDefaults(
	defineProps<{ title: string; message: string; confirmLabel?: string; danger?: boolean }>(),
	{ confirmLabel: 'Delete', danger: true },
)
const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
	<div class="cz-modal-mask" @click.self="emit('cancel')">
		<div class="cz-modal" role="dialog" aria-modal="true">
			<div class="cz-modal__head">
				<SvgIcon :path="mdiAlert" :size="22" :style="{ color: danger ? '#c62828' : 'inherit' }" />
				<h3>{{ title }}</h3>
			</div>
			<p class="cz-modal__message">{{ message }}</p>
			<div class="cz-modal__actions">
				<CzButton variant="tertiary" @click="emit('cancel')">Cancel</CzButton>
				<CzButton :variant="danger ? 'danger' : 'primary'" @click="emit('confirm')">
					{{ confirmLabel }}
				</CzButton>
			</div>
		</div>
	</div>
</template>
