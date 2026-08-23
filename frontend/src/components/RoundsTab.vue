<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import type { AssemblyDetail } from '../types'

const props = defineProps<{ assembly: AssemblyDetail }>()
const emit = defineEmits<{ changed: [] }>()

const error = ref('')
const editingId = ref('')
const editTitle = ref('')
const editQuestion = ref('')
const editDuration = ref(30)

function startEdit(roundId: string): void {
	const round = props.assembly.rounds.find((r) => r.id === roundId)
	if (!round) return
	editingId.value = roundId
	editTitle.value = round.title
	editQuestion.value = round.question
	editDuration.value = round.duration_minutes
}

async function run(action: () => Promise<unknown>): Promise<void> {
	error.value = ''
	try {
		await action()
		emit('changed')
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	}
}

const saveEdit = () =>
	run(async () => {
		await api.updateRound(editingId.value, {
			title: editTitle.value,
			question: editQuestion.value,
			duration_minutes: editDuration.value,
		})
		editingId.value = ''
	})

const move = (roundId: string, position: number) => run(() => api.updateRound(roundId, { position }))
const remove = (roundId: string) => run(() => api.deleteRound(roundId))
const add = () =>
	run(() =>
		api.addRound(props.assembly.id, {
			title: `Round ${props.assembly.rounds.length + 1}`,
			question: '',
			duration_minutes: 30,
		}),
	)
</script>

<template>
	<div>
		<div v-if="error" class="cz-error">{{ error }}</div>
		<div v-for="round in assembly.rounds" :key="round.id" class="cz-card">
			<template v-if="editingId === round.id">
				<div class="cz-field"><label>Title</label><input v-model="editTitle" type="text" /></div>
				<div class="cz-field"><label>Question</label><textarea v-model="editQuestion" rows="2"></textarea></div>
				<div class="cz-field" style="max-width: 160px">
					<label>Duration (min)</label><input v-model.number="editDuration" type="number" min="1" />
				</div>
				<div class="cz-row">
					<button class="cz-btn cz-small" @click="editingId = ''">Cancel</button>
					<button class="cz-btn cz-small cz-primary" @click="saveEdit">Save</button>
				</div>
			</template>
			<template v-else>
				<div class="cz-row cz-spread">
					<div>
						<strong>Round {{ round.position }} — {{ round.title || 'Untitled' }}</strong>
						<span class="cz-chip" style="margin-left: 8px">{{ round.duration_minutes }} min</span>
						<span class="cz-chip" style="margin-left: 4px">{{ round.status }}</span>
						<p class="cz-muted" style="margin: 6px 0 0">{{ round.question || 'No question set.' }}</p>
					</div>
					<div class="cz-row">
						<button class="cz-btn cz-small" :disabled="round.position === 1" @click="move(round.id, round.position - 1)">↑</button>
						<button class="cz-btn cz-small" :disabled="round.position === assembly.rounds.length" @click="move(round.id, round.position + 1)">↓</button>
						<button class="cz-btn cz-small" @click="startEdit(round.id)">Edit</button>
						<button class="cz-btn cz-small cz-danger" @click="remove(round.id)">Delete</button>
					</div>
				</div>
			</template>
		</div>
		<button class="cz-btn" @click="add">+ Add round</button>
	</div>
</template>
