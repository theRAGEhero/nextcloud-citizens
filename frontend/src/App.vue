<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from './api'
import AssemblyDetail from './components/AssemblyDetail.vue'
import AssemblyList from './components/AssemblyList.vue'
import AssemblyWizard from './components/AssemblyWizard.vue'
import SettingsView from './components/SettingsView.vue'

type View = { name: 'list' } | { name: 'create' } | { name: 'detail'; id: string } | { name: 'settings' }

const view = ref<View>({ name: 'list' })
const isAdmin = ref(false)

onMounted(async () => {
	try {
		await api.adminPing()
		isAdmin.value = true
	} catch {
		isAdmin.value = false
	}
})
</script>

<template>
	<AssemblyList
		v-if="view.name === 'list'"
		:is-admin="isAdmin"
		@create="view = { name: 'create' }"
		@open="(id: string) => (view = { name: 'detail', id })"
		@settings="view = { name: 'settings' }" />
	<AssemblyWizard
		v-else-if="view.name === 'create'"
		@cancel="view = { name: 'list' }"
		@created="(id: string) => (view = { name: 'detail', id })" />
	<SettingsView v-else-if="view.name === 'settings'" @back="view = { name: 'list' }" />
	<AssemblyDetail
		v-else-if="view.name === 'detail'"
		:assembly-id="view.id"
		@back="view = { name: 'list' }" />
</template>
