<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { Participant } from '../types'

const props = defineProps<{ assemblyId: string }>()
const emit = defineEmits<{ changed: [] }>()

const participants = ref<Participant[]>([])
const error = ref('')
const newLabel = ref('')
const newName = ref('')
const csvText = ref('')
const showCsv = ref(false)

async function reload(): Promise<void> {
	participants.value = await api.listParticipants(props.assemblyId)
}

onMounted(reload)

async function run(action: () => Promise<unknown>): Promise<void> {
	error.value = ''
	try {
		await action()
		await reload()
		emit('changed')
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	}
}

const addOne = () =>
	run(async () => {
		await api.addParticipants(props.assemblyId, [{ label: newLabel.value.trim(), name: newName.value.trim() }])
		newLabel.value = ''
		newName.value = ''
	})

const importCsv = () =>
	run(async () => {
		await api.importCsv(props.assemblyId, csvText.value)
		csvText.value = ''
		showCsv.value = false
	})

function generateAnonymous(): void {
	const start = participants.value.length + 1
	csvText.value =
		'label,name,email\n' +
		Array.from({ length: 50 }, (_, i) => `P${String(start + i).padStart(3, '0')},,`).join('\n')
	showCsv.value = true
}

const remove = (id: string) => run(() => api.deleteParticipant(id))
</script>

<template>
	<div>
		<div v-if="error" class="cz-error">{{ error }}</div>

		<div class="cz-card">
			<h3>Add participants</h3>
			<div class="cz-row">
				<input v-model="newLabel" type="text" placeholder="Label (e.g. P001)" style="width: 140px" />
				<input v-model="newName" type="text" placeholder="Name (optional)" />
				<button class="cz-btn cz-small cz-primary" :disabled="!newLabel.trim()" @click="addOne">Add</button>
				<button class="cz-btn cz-small" @click="showCsv = !showCsv">CSV import</button>
				<button class="cz-btn cz-small" @click="generateAnonymous">Prefill 50 anonymous</button>
			</div>
			<div v-if="showCsv" style="margin-top: 12px">
				<p class="cz-muted" style="font-size: 13px">
					Header <code>label,name,email</code> — names and emails are optional.
				</p>
				<textarea v-model="csvText" rows="8" style="width: 100%; font-family: monospace"></textarea>
				<div class="cz-row" style="margin-top: 8px">
					<button class="cz-btn cz-small cz-primary" :disabled="!csvText.trim()" @click="importCsv">Import</button>
				</div>
			</div>
		</div>

		<p class="cz-muted">{{ participants.length }} participants</p>
		<table class="cz-table">
			<thead>
				<tr><th>Label</th><th>Name</th><th>Email</th><th></th></tr>
			</thead>
			<tbody>
				<tr v-for="participant in participants" :key="participant.id">
					<td><strong>{{ participant.label }}</strong></td>
					<td>{{ participant.name || '—' }}</td>
					<td>{{ participant.email || '—' }}</td>
					<td style="text-align: right">
						<button class="cz-btn cz-small cz-danger" @click="remove(participant.id)">Remove</button>
					</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>
