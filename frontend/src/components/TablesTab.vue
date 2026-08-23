<script setup lang="ts">
import { mdiContentCopy, mdiShuffleVariant, mdiTableFurniture } from '@mdi/js'
import { onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { AssemblyDetail, Table } from '../types'
import CzButton from './ui/CzButton.vue'
import CzEmptyState from './ui/CzEmptyState.vue'
import CzSkeleton from './ui/CzSkeleton.vue'

const props = defineProps<{ assembly: AssemblyDetail }>()

const roundId = ref(props.assembly.rounds[0]?.id ?? '')
const tables = ref<Table[]>([])
const loaded = ref(false)
const error = ref('')
const busy = ref(false)

async function reload(): Promise<void> {
	if (!roundId.value) {
		loaded.value = true
		return
	}
	tables.value = await api.roundTables(roundId.value)
	loaded.value = true
}

onMounted(reload)
watch(roundId, () => {
	loaded.value = false
	void reload()
})

async function run(action: () => Promise<Table[]>): Promise<void> {
	busy.value = true
	error.value = ''
	try {
		tables.value = await action()
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	} finally {
		busy.value = false
	}
}

const randomize = () => run(() => api.randomize(roundId.value))
const copyPrevious = () => run(() => api.copyPrevious(roundId.value))
const move = (participantId: string, toTableId: string) =>
	run(() => api.moveParticipant(roundId.value, participantId, toTableId))

const hasAssignments = () => tables.value.some((t) => t.participants.length > 0)
</script>

<template>
	<div>
		<div v-if="error" class="cz-error">{{ error }}</div>

		<div class="cz-row" style="margin-bottom: 16px">
			<select v-model="roundId" style="min-width: 220px">
				<option v-for="round in assembly.rounds" :key="round.id" :value="round.id">
					Round {{ round.position }} — {{ round.title || 'Untitled' }}
				</option>
			</select>
			<CzButton variant="primary" small :icon="mdiShuffleVariant" :disabled="busy || !roundId" @click="randomize">
				Random assignment
			</CzButton>
			<CzButton small :icon="mdiContentCopy" :disabled="busy || !roundId" @click="copyPrevious">
				Copy previous round
			</CzButton>
		</div>

		<CzSkeleton v-if="!loaded" :rows="3" :height="120" />

		<CzEmptyState
			v-else-if="tables.length === 0"
			:icon="mdiTableFurniture"
			title="No tables in this round"
			hint="Tables are created with the assembly. Add a round first if the list is empty." />

		<CzEmptyState
			v-else-if="!hasAssignments()"
			:icon="mdiShuffleVariant"
			title="Nobody is seated yet"
			hint="Randomly assign all participants to tables, or copy the previous round's seating.">
			<CzButton variant="primary" :icon="mdiShuffleVariant" :disabled="busy" @click="randomize">
				Random assignment
			</CzButton>
		</CzEmptyState>

		<div v-else class="cz-tables-grid">
			<div v-for="table in tables" :key="table.id" class="cz-card" style="margin-bottom: 0">
				<div class="cz-row cz-row--spread" style="margin-bottom: 10px">
					<h3>Table {{ table.number }}</h3>
					<span class="cz-pill cz-pill--gray" style="text-transform: none">
						{{ table.participants.length }} seated
					</span>
				</div>
				<p v-if="table.participants.length === 0" class="cz-muted" style="font-size: 13px">Empty</p>
				<div
					v-for="participant in table.participants"
					:key="participant.id"
					class="cz-row cz-row--spread"
					style="padding: 4px 0; flex-wrap: nowrap">
					<span style="min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
						<strong>{{ participant.label }}</strong>
						<span v-if="participant.name" class="cz-muted"> · {{ participant.name }}</span>
					</span>
					<select
						:value="table.id"
						title="Move to table"
						style="padding: 3px 6px; font-size: 13px"
						@change="move(participant.id, ($event.target as HTMLSelectElement).value)">
						<option v-for="target in tables" :key="target.id" :value="target.id">T{{ target.number }}</option>
					</select>
				</div>
			</div>
		</div>
	</div>
</template>
