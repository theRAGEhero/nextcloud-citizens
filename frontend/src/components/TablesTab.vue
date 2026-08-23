<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { AssemblyDetail, Table } from '../types'

const props = defineProps<{ assembly: AssemblyDetail }>()

const roundId = ref(props.assembly.rounds[0]?.id ?? '')
const tables = ref<Table[]>([])
const error = ref('')
const busy = ref(false)

async function reload(): Promise<void> {
	if (!roundId.value) return
	tables.value = await api.roundTables(roundId.value)
}

onMounted(reload)
watch(roundId, reload)

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
</script>

<template>
	<div>
		<div v-if="error" class="cz-error">{{ error }}</div>
		<div class="cz-row" style="margin-bottom: 14px">
			<select v-model="roundId">
				<option v-for="round in assembly.rounds" :key="round.id" :value="round.id">
					Round {{ round.position }} — {{ round.title || 'Untitled' }}
				</option>
			</select>
			<button class="cz-btn cz-small cz-primary" :disabled="busy || !roundId" @click="randomize">
				Random assignment
			</button>
			<button class="cz-btn cz-small" :disabled="busy || !roundId" @click="copyPrevious">
				Copy from previous round
			</button>
		</div>

		<p v-if="tables.length === 0" class="cz-muted">No tables in this round.</p>
		<div class="cz-tables-grid">
			<div v-for="table in tables" :key="table.id" class="cz-card" style="margin-bottom: 0">
				<h3>Table {{ table.number }}</h3>
				<p v-if="table.participants.length === 0" class="cz-muted" style="font-size: 13px">Empty</p>
				<div
					v-for="participant in table.participants"
					:key="participant.id"
					class="cz-row cz-spread"
					style="padding: 3px 0">
					<span>
						<strong>{{ participant.label }}</strong>
						<span v-if="participant.name" class="cz-muted"> · {{ participant.name }}</span>
					</span>
					<select
						:value="table.id"
						title="Move to table"
						@change="move(participant.id, ($event.target as HTMLSelectElement).value)">
						<option v-for="target in tables" :key="target.id" :value="target.id">
							T{{ target.number }}
						</option>
					</select>
				</div>
			</div>
		</div>
	</div>
</template>
