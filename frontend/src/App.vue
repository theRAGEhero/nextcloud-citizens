<!-- SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
     SPDX-License-Identifier: AGPL-3.0-or-later -->
<script setup lang="ts">
import { mdiAccountVoice, mdiCog, mdiMenu, mdiPlus } from '@mdi/js'
import { computed, onMounted, ref } from 'vue'
import { api } from './api'
import AssemblyDetail from './components/AssemblyDetail.vue'
import AssemblyWizard from './components/AssemblyWizard.vue'
import SettingsView from './components/SettingsView.vue'
import CzButton from './components/ui/CzButton.vue'
import CzToasts from './components/ui/CzToasts.vue'
import SvgIcon from './components/ui/SvgIcon.vue'
import type { Assembly, InviteGenerated } from './types'

type View = { name: 'empty' } | { name: 'create' } | { name: 'detail'; id: string } | { name: 'settings' }

const assemblies = ref<Assembly[]>([])
const loaded = ref(false)
const view = ref<View>({ name: 'empty' })
const isAdmin = ref(false)
const sidebarOpen = ref(false)
// QR codes generated at creation: handed to the detail view exactly once
const freshInvites = ref<InviteGenerated[]>([])

const STATUS_TONE: Record<string, string> = {
	DRAFT: 'gray', READY: 'blue', ACTIVE: 'red', PROCESSING: 'amber', REVIEW: 'blue', COMPLETE: 'green',
}

const selectedId = computed(() => (view.value.name === 'detail' ? view.value.id : ''))

async function loadAssemblies(selectFirst = false): Promise<void> {
	try {
		assemblies.value = await api.listAssemblies()
		if (selectFirst && view.value.name === 'empty' && assemblies.value.length > 0) {
			view.value = { name: 'detail', id: assemblies.value[0].id }
		}
	} finally {
		loaded.value = true
	}
}

onMounted(async () => {
	void loadAssemblies(true)
	try {
		await api.adminPing()
		isAdmin.value = true
	} catch {
		isAdmin.value = false
	}
})

function open(id: string): void {
	view.value = { name: 'detail', id }
	sidebarOpen.value = false
}

function openCreate(): void {
	view.value = { name: 'create' }
	sidebarOpen.value = false
}

function openSettings(): void {
	view.value = { name: 'settings' }
	sidebarOpen.value = false
}

async function onCreated(id: string, invites: InviteGenerated[]): Promise<void> {
	freshInvites.value = invites
	await loadAssemblies()
	view.value = { name: 'detail', id }
}

async function onDeleted(): Promise<void> {
	await loadAssemblies()
	view.value = assemblies.value.length
		? { name: 'detail', id: assemblies.value[0].id }
		: { name: 'empty' }
}
</script>

<template>
	<aside class="cz-sidebar" :class="{ 'cz-sidebar--open': sidebarOpen }">
		<div class="cz-sidebar__top">
			<CzButton variant="primary" :icon="mdiPlus" wide @click="openCreate">New assembly</CzButton>
		</div>
		<nav class="cz-sidebar__list">
			<button
				v-for="assembly in assemblies"
				:key="assembly.id"
				class="cz-navitem"
				:class="{ 'cz-navitem--active': assembly.id === selectedId }"
				@click="open(assembly.id)">
				<span class="cz-dot" :class="`cz-dot--${STATUS_TONE[assembly.status] ?? 'gray'}`"></span>
				<span class="cz-navitem__body">
					<span class="cz-navitem__name">{{ assembly.name }}</span>
					<span class="cz-navitem__meta">
						{{ assembly.expected_participants }} participants · {{ assembly.default_table_count }} tables
					</span>
				</span>
			</button>
			<p v-if="loaded && assemblies.length === 0" class="cz-muted" style="padding: 12px; font-size: 13px">
				No assemblies yet.
			</p>
		</nav>
		<div v-if="isAdmin" class="cz-sidebar__bottom">
			<button
				class="cz-navitem"
				:class="{ 'cz-navitem--active': view.name === 'settings' }"
				@click="openSettings">
				<SvgIcon :path="mdiCog" :size="18" />
				<span class="cz-navitem__body"><span class="cz-navitem__name">Settings</span></span>
			</button>
		</div>
	</aside>

	<div v-if="sidebarOpen" class="cz-scrim" @click="sidebarOpen = false"></div>

	<main class="cz-content">
		<div class="cz-mobilebar">
			<CzButton :icon="mdiMenu" small @click="sidebarOpen = true">Assemblies</CzButton>
		</div>

		<div v-if="view.name === 'empty'" class="cz-page">
			<div class="cz-empty" style="padding-top: 12vh">
				<div class="cz-empty__icon"><SvgIcon :path="mdiAccountVoice" :size="44" /></div>
				<h3 class="cz-empty__title">Welcome to Citizens</h3>
				<p class="cz-empty__hint">
					Run in-person citizens' assemblies: one phone per table records the discussion safely,
					even with unstable connectivity, and transcripts arrive automatically.
				</p>
				<div class="cz-empty__action">
					<CzButton variant="primary" :icon="mdiPlus" @click="openCreate">Create your first assembly</CzButton>
				</div>
			</div>
		</div>

		<AssemblyWizard
			v-else-if="view.name === 'create'"
			@cancel="view = assemblies.length ? { name: 'detail', id: assemblies[0].id } : { name: 'empty' }"
			@created="onCreated" />

		<SettingsView v-else-if="view.name === 'settings'" />

		<AssemblyDetail
			v-else-if="view.name === 'detail'"
			:key="view.id"
			:assembly-id="view.id"
			:fresh-invites="freshInvites"
			@changed="loadAssemblies()"
			@invites-consumed="freshInvites = []"
			@deleted="onDeleted" />
	</main>

	<CzToasts />
</template>
