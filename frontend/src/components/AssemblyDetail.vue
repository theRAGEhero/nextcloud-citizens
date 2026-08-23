<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { AssemblyDetail } from '../types'
import ParticipantsTab from './ParticipantsTab.vue'
import QrTab from './QrTab.vue'
import RoundsTab from './RoundsTab.vue'
import TablesTab from './TablesTab.vue'

const props = defineProps<{ assemblyId: string }>()
const emit = defineEmits<{ back: [] }>()

const assembly = ref<AssemblyDetail | null>(null)
const error = ref('')
const tab = ref<'rounds' | 'participants' | 'tables' | 'qr'>('rounds')

async function reload(): Promise<void> {
	try {
		assembly.value = await api.getAssembly(props.assemblyId)
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	}
}

onMounted(reload)
</script>

<template>
	<div>
		<button class="cz-btn cz-small" @click="emit('back')">← Assemblies</button>
		<div v-if="error" class="cz-error">{{ error }}</div>
		<template v-if="assembly">
			<div class="cz-row cz-spread" style="margin-top: 14px">
				<div>
					<h2>{{ assembly.name }}</h2>
					<p class="cz-muted">
						{{ assembly.participant_count }} / {{ assembly.expected_participants }} participants ·
						{{ assembly.default_table_count }} tables ·
						{{ assembly.rounds.length }} rounds
					</p>
				</div>
				<span class="cz-chip">{{ assembly.status }}</span>
			</div>

			<div class="cz-tabs">
				<button class="cz-tab" :class="{ 'cz-active': tab === 'rounds' }" @click="tab = 'rounds'">Rounds</button>
				<button class="cz-tab" :class="{ 'cz-active': tab === 'participants' }" @click="tab = 'participants'">Participants</button>
				<button class="cz-tab" :class="{ 'cz-active': tab === 'tables' }" @click="tab = 'tables'">Tables</button>
				<button class="cz-tab" :class="{ 'cz-active': tab === 'qr' }" @click="tab = 'qr'">QR codes</button>
			</div>

			<RoundsTab v-if="tab === 'rounds'" :assembly="assembly" @changed="reload" />
			<ParticipantsTab v-else-if="tab === 'participants'" :assembly-id="assembly.id" @changed="reload" />
			<TablesTab v-else-if="tab === 'tables'" :assembly="assembly" />
			<QrTab v-else :assembly-id="assembly.id" />
		</template>
	</div>
</template>
