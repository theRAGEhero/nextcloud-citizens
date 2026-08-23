<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { Invite, InviteGenerated } from '../types'

const props = defineProps<{ assemblyId: string }>()

const invites = ref<Invite[]>([])
const generated = ref<InviteGenerated[]>([])
const error = ref('')
const busy = ref(false)

async function reload(): Promise<void> {
	invites.value = await api.listInvites(props.assemblyId)
}

onMounted(reload)

async function generate(): Promise<void> {
	busy.value = true
	error.value = ''
	try {
		generated.value = await api.generateInvites(props.assemblyId)
		await reload()
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	} finally {
		busy.value = false
	}
}

async function revoke(): Promise<void> {
	busy.value = true
	error.value = ''
	try {
		await api.revokeInvites(props.assemblyId)
		generated.value = []
		await reload()
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	} finally {
		busy.value = false
	}
}

function printSheet(): void {
	window.print()
}

async function copyUrl(url: string): Promise<void> {
	try {
		await navigator.clipboard.writeText(url)
	} catch {
		/* clipboard unavailable (permissions); the URL stays visible as text */
	}
}
</script>

<template>
	<div>
		<div v-if="error" class="cz-error">{{ error }}</div>

		<div class="cz-card">
			<h3>Table recorder QR codes</h3>
			<p class="cz-muted" style="font-size: 13px">
				One QR code per physical table. The link is shown <strong>only once</strong> after
				generating — print the sheet right away. Regenerating revokes all previous codes.
			</p>
			<div class="cz-row">
				<button class="cz-btn cz-primary" :disabled="busy" @click="generate">
					{{ invites.some((i) => i.active) ? 'Regenerate all codes' : 'Generate codes' }}
				</button>
				<button v-if="generated.length" class="cz-btn" @click="printSheet">Print sheet</button>
				<button
					v-if="invites.some((i) => i.active)"
					class="cz-btn cz-danger"
					:disabled="busy"
					@click="revoke">
					Revoke all
				</button>
			</div>
			<p v-if="invites.length && !generated.length" class="cz-muted" style="font-size: 13px; margin-top: 10px">
				{{ invites.filter((i) => i.active).length }} of {{ invites.length }} table codes active.
				Links are not retrievable after generation — regenerate to get new QR codes.
			</p>
		</div>

		<div v-if="generated.length" class="cz-qr-grid">
			<div v-for="invite in generated" :key="invite.table_number" class="cz-qr-item">
				<h3>TABLE {{ invite.table_number }}</h3>
				<div v-html="invite.qr_svg"></div>
				<p style="font-size: 13px; margin: 4px 0">Scan with the table recording phone</p>
				<div class="cz-qr-url">{{ invite.url }}</div>
				<button class="cz-btn cz-small" style="margin-top: 6px" @click="copyUrl(invite.url)">Copy link</button>
			</div>
		</div>
	</div>
</template>
