<!-- SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
     SPDX-License-Identifier: AGPL-3.0-or-later -->
<script setup lang="ts">
import { mdiAlertCircle, mdiCheckCircle } from '@mdi/js'
import SvgIcon from './SvgIcon.vue'
import { toasts } from './toast'
</script>

<template>
	<div class="cz-toasts">
		<TransitionGroup name="cz-toast">
			<div v-for="item in toasts" :key="item.id" class="cz-toast" :class="`cz-toast--${item.tone}`">
				<SvgIcon :path="item.tone === 'success' ? mdiCheckCircle : mdiAlertCircle" :size="18" />
				{{ item.text }}
			</div>
		</TransitionGroup>
	</div>
</template>
