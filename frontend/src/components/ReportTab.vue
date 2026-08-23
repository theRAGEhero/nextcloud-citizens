<script setup lang="ts">
import { mdiCodeJson, mdiDownloadOutline, mdiFileDocumentOutline } from '@mdi/js'
import { onMounted, ref, watch } from 'vue'
import { api, BASE } from '../api'
import type { AssemblyDetail, ReportData } from '../types'
import CzButton from './ui/CzButton.vue'
import CzEmptyState from './ui/CzEmptyState.vue'
import CzSkeleton from './ui/CzSkeleton.vue'

const props = defineProps<{ assembly: AssemblyDetail }>()

const report = ref<ReportData | null>(null)
const error = ref('')
const includeDrafts = ref(false)

const TYPE_LABELS: Record<string, string> = {
	proposal: 'Proposal', agreement: 'Agreement', disagreement: 'Disagreement',
	concern: 'Concern', question: 'Open question', minority_position: 'Minority position',
	new_idea: 'New idea',
}

async function reload(): Promise<void> {
	try {
		report.value = await api.assemblyReport(props.assembly.id, includeDrafts.value)
		error.value = ''
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	}
}

onMounted(reload)
watch(includeDrafts, reload)

function downloadMarkdown(): void {
	window.open(
		`${BASE}/api/v1/assemblies/${props.assembly.id}/report.md?include_drafts=${includeDrafts.value}`,
		'_blank',
	)
}

function downloadJson(): void {
	if (!report.value) return
	const blob = new Blob([JSON.stringify(report.value, null, 2)], { type: 'application/json' })
	const url = URL.createObjectURL(blob)
	const anchor = document.createElement('a')
	anchor.href = url
	anchor.download = `${props.assembly.name.slice(0, 40)}-report.json`
	anchor.click()
	URL.revokeObjectURL(url)
}

const hasContent = () =>
	!!report.value &&
	report.value.rounds.some(
		(r) => r.cross_table.length > 0 || !!r.summary || r.tables.some((t) => t.findings.length > 0 || !!t.summary),
	)
</script>

<template>
	<div>
		<div v-if="error" class="cz-error">{{ error }}</div>

		<div class="cz-row cz-row--spread" style="margin-bottom: 16px">
			<label style="display: flex; align-items: center; gap: 8px; cursor: pointer">
				<input v-model="includeDrafts" type="checkbox" />
				Include unreviewed drafts (clearly marked)
			</label>
			<div class="cz-row">
				<CzButton small :icon="mdiDownloadOutline" @click="downloadMarkdown">Markdown</CzButton>
				<CzButton small :icon="mdiCodeJson" @click="downloadJson">JSON</CzButton>
			</div>
		</div>

		<CzSkeleton v-if="!report && !error" :rows="4" />

		<CzEmptyState
			v-else-if="report && !hasContent()"
			:icon="mdiFileDocumentOutline"
			title="Nothing to report yet"
			:hint="includeDrafts
				? 'No findings exist yet — record tables and run the analysis first.'
				: 'No approved findings yet. Approve findings in the Analysis tab, or include drafts to preview.'" />

		<template v-else-if="report">
			<div class="cz-card">
				<h2 style="font-size: 21px">{{ report.assembly.name }} — Assembly Report</h2>
				<p v-if="report.assembly.description" class="cz-muted" style="margin-top: 6px">
					{{ report.assembly.description }}
				</p>
				<p class="cz-muted" style="font-size: 13.5px; margin: 8px 0 0">
					{{ report.assembly.participants }} participants ·
					{{ report.assembly.tables }} tables ·
					{{ report.assembly.language.toUpperCase() }}
				</p>
				<p style="font-size: 14px; margin-top: 12px">{{ report.method }}</p>
			</div>

			<template v-for="round in report.rounds" :key="round.position">
				<div
					v-if="round.cross_table.length || round.summary || round.tables.some((t) => t.findings.length || t.summary)"
					class="cz-card">
					<h3>Round {{ round.position }} — {{ round.title || 'Untitled' }}</h3>
					<p v-if="round.question" class="cz-muted" style="font-style: italic; margin: 4px 0 14px">
						“{{ round.question }}”
					</p>
					<p v-if="round.summary" style="font-size: 14.5px; font-style: italic; margin-bottom: 14px">
						<span class="cz-muted" style="font-style: normal; font-size: 12px; display: block">AI SUMMARY</span>
						{{ round.summary }}
					</p>

					<template v-if="round.cross_table.length">
						<h4 style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--cz-text-muted); margin: 12px 0 8px">
							Across all tables
						</h4>
						<div v-for="finding in round.cross_table" :key="finding.id" style="margin-bottom: 14px">
							<strong>
								{{ TYPE_LABELS[finding.type] ?? finding.type }}: {{ finding.title }}
								<span v-if="finding.is_draft" class="cz-pill cz-pill--amber" style="text-transform: none">DRAFT — not reviewed</span>
							</strong>
							<p v-if="finding.mentioned_table_count" class="cz-muted" style="font-size: 13px; margin: 2px 0">
								Mentioned at {{ finding.mentioned_table_count }} table(s)
							</p>
							<p style="margin: 4px 0; font-size: 14.5px">{{ finding.summary }}</p>
							<blockquote
								v-for="(evidence, index) in finding.evidence.slice(0, 3)"
								:key="index"
								style="margin: 6px 0; padding: 4px 12px; border-left: 3px solid var(--cz-border); font-size: 13.5px; color: var(--cz-text-muted)">
								[{{ evidence.timestamp }}] {{ evidence.speaker || 'Speaker' }}: “{{ evidence.text }}”
							</blockquote>
						</div>
					</template>

					<template v-for="table in round.tables" :key="table.table_number">
						<template v-if="table.findings.length || table.summary">
							<h4 style="font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--cz-text-muted); margin: 16px 0 8px">
								Table {{ table.table_number }}
							</h4>
							<p v-if="table.summary" style="font-size: 14px; font-style: italic; margin: 0 0 10px">
								<span class="cz-muted" style="font-style: normal; font-size: 12px; display: block">AI SUMMARY</span>
								{{ table.summary }}
							</p>
							<div v-for="finding in table.findings" :key="finding.id" style="margin-bottom: 14px">
								<strong>
									{{ TYPE_LABELS[finding.type] ?? finding.type }}: {{ finding.title }}
									<span v-if="finding.is_draft" class="cz-pill cz-pill--amber" style="text-transform: none">DRAFT — not reviewed</span>
								</strong>
								<p style="margin: 4px 0; font-size: 14.5px">{{ finding.summary }}</p>
								<blockquote
									v-for="(evidence, index) in finding.evidence.slice(0, 3)"
									:key="index"
									style="margin: 6px 0; padding: 4px 12px; border-left: 3px solid var(--cz-border); font-size: 13.5px; color: var(--cz-text-muted)">
									[{{ evidence.timestamp }}] {{ evidence.speaker || 'Speaker' }}: “{{ evidence.text }}”
								</blockquote>
							</div>
						</template>
					</template>
				</div>
			</template>

			<p class="cz-muted" style="font-size: 13px; font-style: italic">
				{{ report.methodology_note }}
			</p>
		</template>
	</div>
</template>
