<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { Assembly } from '../types'

const emit = defineEmits<{ create: []; open: [id: string] }>()

const assemblies = ref<Assembly[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
	try {
		assemblies.value = await api.listAssemblies()
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	} finally {
		loading.value = false
	}
})
</script>

<template>
	<div>
		<div class="cz-row cz-spread">
			<div>
				<h2>Nextcloud Citizens</h2>
				<p class="cz-muted">Citizens' assemblies: offline-first table recording, transcription and reviewed analysis.</p>
			</div>
			<button class="cz-btn cz-primary" @click="emit('create')">+ New assembly</button>
		</div>

		<div v-if="error" class="cz-error">{{ error }}</div>
		<p v-else-if="loading" class="cz-muted">Loading…</p>
		<p v-else-if="assemblies.length === 0" class="cz-muted" style="margin-top: 30px">
			No assemblies yet. Create the first one to get started.
		</p>

		<div
			v-for="assembly in assemblies"
			:key="assembly.id"
			class="cz-card cz-clickable"
			@click="emit('open', assembly.id)">
			<div class="cz-row cz-spread">
				<div>
					<strong>{{ assembly.name }}</strong>
					<div class="cz-muted" style="font-size: 13px">
						{{ assembly.expected_participants }} participants ·
						{{ assembly.default_table_count }} tables ·
						{{ assembly.language }}
					</div>
				</div>
				<span class="cz-chip">{{ assembly.status }}</span>
			</div>
		</div>
	</div>
</template>
