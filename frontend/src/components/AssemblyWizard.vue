<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import type { RoundIn } from '../types'

const emit = defineEmits<{ cancel: []; created: [id: string] }>()

const step = ref(1)
const error = ref('')
const saving = ref(false)

const name = ref('')
const description = ref('')
const language = ref('en')
const expectedParticipants = ref(50)
const tableCount = ref(10)
const rounds = ref<RoundIn[]>([
	{ title: 'Round 1', question: '', duration_minutes: 30 },
])

function addRound(): void {
	rounds.value.push({
		title: `Round ${rounds.value.length + 1}`,
		question: '',
		duration_minutes: 30,
	})
}

function removeRound(index: number): void {
	rounds.value.splice(index, 1)
}

function moveRound(index: number, delta: number): void {
	const target = index + delta
	if (target < 0 || target >= rounds.value.length) return
	const [item] = rounds.value.splice(index, 1)
	rounds.value.splice(target, 0, item)
}

async function submit(): Promise<void> {
	saving.value = true
	error.value = ''
	try {
		const created = await api.createAssembly({
			name: name.value.trim(),
			description: description.value,
			language: language.value,
			expected_participants: expectedParticipants.value,
			default_table_count: tableCount.value,
			rounds: rounds.value,
		})
		emit('created', created.id)
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	} finally {
		saving.value = false
	}
}
</script>

<template>
	<div>
		<h2>Create assembly</h2>
		<p class="cz-muted">Step {{ step }} of 2 — {{ step === 1 ? 'Basics' : 'Rounds' }}</p>
		<div v-if="error" class="cz-error">{{ error }}</div>

		<div v-if="step === 1" class="cz-card">
			<div class="cz-field">
				<label>Name</label>
				<input v-model="name" type="text" placeholder="Bologna Mobility Assembly" />
			</div>
			<div class="cz-field">
				<label>Description</label>
				<textarea v-model="description" rows="2"></textarea>
			</div>
			<div class="cz-row">
				<div class="cz-field">
					<label>Language</label>
					<select v-model="language">
						<option value="en">English</option>
						<option value="it">Italiano</option>
						<option value="de">Deutsch</option>
						<option value="fr">Français</option>
						<option value="es">Español</option>
					</select>
				</div>
				<div class="cz-field">
					<label>Expected participants</label>
					<input v-model.number="expectedParticipants" type="number" min="0" max="10000" />
				</div>
				<div class="cz-field">
					<label>Number of tables</label>
					<input v-model.number="tableCount" type="number" min="0" max="200" />
				</div>
			</div>
			<div class="cz-row">
				<button class="cz-btn" @click="emit('cancel')">Cancel</button>
				<button class="cz-btn cz-primary" :disabled="!name.trim()" @click="step = 2">Continue</button>
			</div>
		</div>

		<div v-else>
			<div v-for="(round, index) in rounds" :key="index" class="cz-card">
				<div class="cz-row cz-spread">
					<strong>Round {{ index + 1 }}</strong>
					<div class="cz-row">
						<button class="cz-btn cz-small" :disabled="index === 0" @click="moveRound(index, -1)">↑</button>
						<button class="cz-btn cz-small" :disabled="index === rounds.length - 1" @click="moveRound(index, 1)">↓</button>
						<button class="cz-btn cz-small cz-danger" :disabled="rounds.length === 1" @click="removeRound(index)">Delete</button>
					</div>
				</div>
				<div class="cz-field">
					<label>Title</label>
					<input v-model="round.title" type="text" />
				</div>
				<div class="cz-field">
					<label>Question / prompt</label>
					<textarea v-model="round.question" rows="2" placeholder="What mobility problems do people experience?"></textarea>
				</div>
				<div class="cz-field" style="max-width: 180px">
					<label>Duration (minutes)</label>
					<input v-model.number="round.duration_minutes" type="number" min="1" max="600" />
				</div>
			</div>
			<div class="cz-row">
				<button class="cz-btn" @click="addRound">+ Add round</button>
			</div>
			<div class="cz-row" style="margin-top: 18px">
				<button class="cz-btn" @click="step = 1">Back</button>
				<button class="cz-btn cz-primary" :disabled="saving" @click="submit">
					{{ saving ? 'Creating…' : 'Create assembly' }}
				</button>
			</div>
		</div>
	</div>
</template>
