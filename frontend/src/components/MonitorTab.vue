<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import type { AssemblyDetail, RoundMonitor } from '../types'

const props = defineProps<{ assembly: AssemblyDetail }>()
const emit = defineEmits<{ changed: [] }>()

const roundId = ref(
	props.assembly.rounds.find((r) => r.status === 'ACTIVE')?.id ?? props.assembly.rounds[0]?.id ?? '',
)
const monitor = ref<RoundMonitor | null>(null)
const error = ref('')
const busy = ref(false)
const now = ref(Date.now())
const openTable = ref<number | null>(null)
const deviceLog = ref<string[]>([])

let pollTimer = 0
let clockTimer = 0

async function poll(): Promise<void> {
	if (!roundId.value) return
	try {
		monitor.value = await api.roundMonitor(roundId.value)
		error.value = ''
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	}
}

onMounted(() => {
	void poll()
	pollTimer = window.setInterval(() => void poll(), 4000)
	clockTimer = window.setInterval(() => (now.value = Date.now()), 1000)
})

onBeforeUnmount(() => {
	window.clearInterval(pollTimer)
	window.clearInterval(clockTimer)
})

watch(roundId, () => {
	monitor.value = null
	void poll()
})

const remaining = computed(() => {
	if (!monitor.value || monitor.value.status !== 'ACTIVE' || !monitor.value.started_at) return ''
	const endAt =
		new Date(monitor.value.started_at).getTime() + monitor.value.duration_minutes * 60_000
	const seconds = Math.max(0, Math.floor((endAt - now.value) / 1000))
	const minutes = Math.floor(seconds / 60)
	return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
})

async function run(action: () => Promise<unknown>): Promise<void> {
	busy.value = true
	error.value = ''
	try {
		await action()
		await poll()
		emit('changed')
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	} finally {
		busy.value = false
	}
}

const startRound = () => run(() => api.startRound(roundId.value))
const endRound = () => run(() => api.endRound(roundId.value))

async function showDevice(tableNumber: number): Promise<void> {
	openTable.value = openTable.value === tableNumber ? null : tableNumber
	deviceLog.value = []
	if (openTable.value !== null) {
		try {
			const logs = await api.deviceLogs(props.assembly.id, tableNumber, 50)
			deviceLog.value = logs.lines
		} catch {
			deviceLog.value = []
		}
	}
}
</script>

<template>
	<div>
		<div v-if="error" class="cz-error">{{ error }}</div>

		<div class="cz-row cz-spread" style="margin-bottom: 14px">
			<div class="cz-row">
				<select v-model="roundId">
					<option v-for="round in assembly.rounds" :key="round.id" :value="round.id">
						Round {{ round.position }} — {{ round.title || 'Untitled' }} ({{ round.status }})
					</option>
				</select>
				<template v-if="monitor">
					<button
						v-if="monitor.status === 'NOT_STARTED' || monitor.status === 'ENDED'"
						class="cz-btn cz-small cz-primary"
						:disabled="busy"
						@click="startRound">
						▶ Start round
					</button>
					<button
						v-else-if="monitor.status === 'ACTIVE'"
						class="cz-btn cz-small cz-danger"
						:disabled="busy"
						@click="endRound">
						■ End round
					</button>
				</template>
			</div>
			<strong v-if="remaining" style="font-size: 20px; font-variant-numeric: tabular-nums">
				{{ remaining }} remaining
			</strong>
		</div>

		<p v-if="!monitor" class="cz-muted">Loading…</p>
		<template v-else>
			<table class="cz-table">
				<thead>
					<tr>
						<th>Table</th><th>Device</th><th>Recording</th><th>Upload</th><th>Local audio</th><th></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="table in monitor.tables" :key="table.table_id">
						<td><strong>{{ String(table.number).padStart(2, '0') }}</strong></td>
						<td>
							<span v-if="table.device.connected" style="color: var(--color-success, #2d7b41)">● connected</span>
							<span v-else-if="table.device.seconds_since_contact !== null" style="color: var(--color-warning, #b07d00)">
								⚠ {{ table.device.seconds_since_contact }}s ago
							</span>
							<span v-else class="cz-muted">—</span>
						</td>
						<td>
							<span v-if="table.recording">{{ table.recording.state }}</span>
							<span v-else class="cz-muted">—</span>
						</td>
						<td>
							<template v-if="table.device.status.local_chunks !== undefined">
								{{ table.device.status.acked_chunks }}/{{ table.device.status.local_chunks }}
								<span
									v-if="(table.device.status.local_chunks ?? 0) - (table.device.status.acked_chunks ?? 0) > 3"
									style="color: var(--color-warning, #b07d00)">
									({{ (table.device.status.local_chunks ?? 0) - (table.device.status.acked_chunks ?? 0) }} pending)
								</span>
							</template>
							<span v-else-if="table.recording">{{ table.recording.received_chunks }} received</span>
							<span v-else class="cz-muted">—</span>
						</td>
						<td>
							<span v-if="table.local_recording_safe" style="color: var(--color-success, #2d7b41)">✓ SAFE</span>
							<span v-else-if="table.device.status.storage_ok === false" style="color: var(--color-error, #b3261e)">✕ STORAGE</span>
							<span v-else class="cz-muted">unknown</span>
						</td>
						<td>
							<button class="cz-btn cz-small" @click="showDevice(table.number)">
								{{ openTable === table.number ? 'Hide' : 'Details' }}
							</button>
						</td>
					</tr>
				</tbody>
			</table>

			<div v-if="openTable !== null" class="cz-card" style="margin-top: 14px">
				<h3>Table {{ openTable }} — device log (latest 50)</h3>
				<p v-if="deviceLog.length === 0" class="cz-muted">No device log received yet.</p>
				<pre
					v-else
					style="max-height: 300px; overflow: auto; font-size: 12px; background: var(--color-background-dark, #f2f2f2); padding: 10px; border-radius: 8px"
					>{{ deviceLog.join('\n') }}</pre>
			</div>
		</template>
	</div>
</template>
