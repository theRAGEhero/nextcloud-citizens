<script setup lang="ts">
import { mdiBrain, mdiCheck, mdiClose, mdiMicrophoneOutline } from '@mdi/js'
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { ProvidersSummary } from '../types'
import CzButton from './ui/CzButton.vue'
import CzSkeleton from './ui/CzSkeleton.vue'
import SvgIcon from './ui/SvgIcon.vue'
import { toast } from './ui/toast'

const summary = ref<ProvidersSummary | null>(null)
const error = ref('')
const busy = ref(false)

const sttProvider = ref<'mistral' | 'deepgram'>('mistral')
const liveEnabled = ref(true)
const batchEnabled = ref(true)
const mistralKey = ref('')
const mistralModel = ref('')
const deepgramKey = ref('')
const deepgramModel = ref('')
const analysisBaseUrl = ref('')
const analysisModel = ref('')
const analysisKey = ref('')
const analysisEnabled = ref(true)
const testResults = ref<Record<string, { ok: boolean; message: string }>>({})

async function reload(): Promise<void> {
	summary.value = await api.getProviders()
	sttProvider.value = summary.value.stt.provider
	liveEnabled.value = summary.value.stt.live_enabled
	batchEnabled.value = summary.value.stt.batch_enabled
	mistralModel.value = summary.value.stt.mistral_model
	deepgramModel.value = summary.value.stt.deepgram_model
	analysisBaseUrl.value = summary.value.analysis.base_url
	analysisModel.value = summary.value.analysis.model
	analysisEnabled.value = summary.value.analysis.enabled
}

onMounted(async () => {
	try {
		await reload()
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	}
})

async function save(): Promise<void> {
	busy.value = true
	error.value = ''
	try {
		const payload: Record<string, unknown> = {
			stt_provider: sttProvider.value,
			stt_live_enabled: liveEnabled.value,
			stt_batch_enabled: batchEnabled.value,
			mistral_stt_model: mistralModel.value.trim(),
			deepgram_model: deepgramModel.value.trim(),
			analysis_base_url: analysisBaseUrl.value.trim(),
			analysis_model: analysisModel.value.trim(),
			analysis_enabled: analysisEnabled.value,
		}
		if (mistralKey.value) payload.mistral_api_key = mistralKey.value
		if (deepgramKey.value) payload.deepgram_api_key = deepgramKey.value
		if (analysisKey.value) payload.analysis_api_key = analysisKey.value
		summary.value = await api.updateProviders(payload)
		mistralKey.value = ''
		deepgramKey.value = ''
		analysisKey.value = ''
		toast('Settings saved')
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	} finally {
		busy.value = false
	}
}

async function test(target: 'mistral' | 'deepgram' | 'analysis'): Promise<void> {
	busy.value = true
	try {
		const typed =
			target === 'mistral' ? mistralKey.value : target === 'deepgram' ? deepgramKey.value : analysisKey.value
		const baseUrl = target === 'analysis' ? analysisBaseUrl.value.trim() : undefined
		testResults.value = {
			...testResults.value,
			[target]: await api.testProvider(target, typed.trim() || undefined, baseUrl),
		}
	} catch (err) {
		testResults.value = {
			...testResults.value,
			[target]: { ok: false, message: err instanceof Error ? err.message : String(err) },
		}
	} finally {
		busy.value = false
	}
}

function keyPlaceholder(configured: boolean, hint: string): string {
	return configured ? `configured — ${hint} (type to replace)` : 'Paste API key'
}
</script>

<template>
	<div class="cz-page">
		<div class="cz-pagehead">
			<div>
				<h2>Speech &amp; AI settings</h2>
				<p class="cz-muted" style="margin: 4px 0 0">
					API keys are stored encrypted in Nextcloud and never reach browsers or table phones.
				</p>
			</div>
			<CzButton variant="primary" :disabled="busy || !summary" @click="save">
				{{ busy ? 'Saving…' : 'Save settings' }}
			</CzButton>
		</div>

		<div v-if="error" class="cz-error">{{ error }}</div>
		<CzSkeleton v-if="!summary && !error" :rows="3" :height="120" />

		<template v-if="summary">
			<div class="cz-card" style="margin-top: 18px">
				<div class="cz-row" style="margin-bottom: 14px">
					<SvgIcon :path="mdiMicrophoneOutline" :size="22" style="color: var(--cz-primary)" />
					<h3>Transcription</h3>
				</div>

				<div class="cz-row" style="margin-bottom: 16px">
					<label class="cz-radiocard" :class="{ 'cz-radiocard--checked': sttProvider === 'mistral' }">
						<input v-model="sttProvider" type="radio" value="mistral" />
						Mistral (Voxtral)
					</label>
					<label class="cz-radiocard" :class="{ 'cz-radiocard--checked': sttProvider === 'deepgram' }">
						<input v-model="sttProvider" type="radio" value="deepgram" />
						Deepgram
					</label>
				</div>

				<div class="cz-fieldgrid">
					<div class="cz-field">
						<label>Mistral API key</label>
						<div class="cz-row" style="flex-wrap: nowrap">
							<input
								v-model="mistralKey"
								type="password"
								autocomplete="off"
								style="flex: 1"
								:placeholder="keyPlaceholder(summary.stt.mistral_configured, summary.stt.mistral_key_hint)" />
							<CzButton small :disabled="busy" @click="test('mistral')">Test</CzButton>
						</div>
						<span v-if="testResults.mistral" class="cz-pill" :class="testResults.mistral.ok ? 'cz-pill--green' : 'cz-pill--orange'" style="text-transform: none; align-self: flex-start">
							<SvgIcon :path="testResults.mistral.ok ? mdiCheck : mdiClose" :size="14" />
							{{ testResults.mistral.message }}
						</span>
					</div>
					<div class="cz-field">
						<label>Mistral transcription model</label>
						<input v-model="mistralModel" type="text" placeholder="voxtral-mini-latest" />
					</div>
					<div class="cz-field">
						<label>Deepgram API key</label>
						<div class="cz-row" style="flex-wrap: nowrap">
							<input
								v-model="deepgramKey"
								type="password"
								autocomplete="off"
								style="flex: 1"
								:placeholder="keyPlaceholder(summary.stt.deepgram_configured, summary.stt.deepgram_key_hint)" />
							<CzButton small :disabled="busy" @click="test('deepgram')">Test</CzButton>
						</div>
						<span v-if="testResults.deepgram" class="cz-pill" :class="testResults.deepgram.ok ? 'cz-pill--green' : 'cz-pill--orange'" style="text-transform: none; align-self: flex-start">
							<SvgIcon :path="testResults.deepgram.ok ? mdiCheck : mdiClose" :size="14" />
							{{ testResults.deepgram.message }}
						</span>
					</div>
					<div class="cz-field">
						<label>Deepgram model</label>
						<input v-model="deepgramModel" type="text" placeholder="nova-3" />
					</div>
				</div>

				<div class="cz-row" style="gap: 24px; margin-top: 4px">
					<label style="display: flex; align-items: center; gap: 8px; cursor: pointer">
						<input v-model="liveEnabled" type="checkbox" /> Live transcription (provisional captions)
					</label>
					<label style="display: flex; align-items: center; gap: 8px; cursor: pointer">
						<input v-model="batchEnabled" type="checkbox" /> Final transcription (canonical)
					</label>
				</div>
			</div>

			<div class="cz-card">
				<div class="cz-row" style="margin-bottom: 4px">
					<SvgIcon :path="mdiBrain" :size="22" style="color: var(--cz-primary)" />
					<h3>AI analysis</h3>
				</div>
				<p class="cz-muted" style="font-size: 13.5px; margin-bottom: 14px">
					Any OpenAI-compatible endpoint works: Mistral (default), Ollama Cloud, a remote Ollama server, vLLM…
				</p>
				<label style="display: flex; align-items: center; gap: 8px; cursor: pointer; margin-bottom: 14px">
					<input v-model="analysisEnabled" type="checkbox" />
					Run analysis automatically after each table is transcribed
				</label>
				<div class="cz-fieldgrid">
					<div class="cz-field" style="grid-column: span 2">
						<label>Base URL</label>
						<input v-model="analysisBaseUrl" type="text" placeholder="https://api.mistral.ai/v1" />
					</div>
					<div class="cz-field">
						<label>Model</label>
						<input v-model="analysisModel" type="text" placeholder="mistral-large-latest" />
					</div>
					<div class="cz-field">
						<label>API key</label>
						<div class="cz-row" style="flex-wrap: nowrap">
							<input
								v-model="analysisKey"
								type="password"
								autocomplete="off"
								style="flex: 1"
								:placeholder="keyPlaceholder(summary.analysis.configured, summary.analysis.key_hint)" />
							<CzButton small :disabled="busy" @click="test('analysis')">Test</CzButton>
						</div>
						<span v-if="testResults.analysis" class="cz-pill" :class="testResults.analysis.ok ? 'cz-pill--green' : 'cz-pill--orange'" style="text-transform: none; align-self: flex-start">
							<SvgIcon :path="testResults.analysis.ok ? mdiCheck : mdiClose" :size="14" />
							{{ testResults.analysis.message }}
						</span>
					</div>
				</div>
			</div>
		</template>
	</div>
</template>
