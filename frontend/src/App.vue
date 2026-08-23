<script setup lang="ts">
import { ref } from 'vue'
import AssemblyDetail from './components/AssemblyDetail.vue'
import AssemblyList from './components/AssemblyList.vue'
import AssemblyWizard from './components/AssemblyWizard.vue'

type View = { name: 'list' } | { name: 'create' } | { name: 'detail'; id: string }

const view = ref<View>({ name: 'list' })
</script>

<template>
	<AssemblyList
		v-if="view.name === 'list'"
		@create="view = { name: 'create' }"
		@open="(id: string) => (view = { name: 'detail', id })" />
	<AssemblyWizard
		v-else-if="view.name === 'create'"
		@cancel="view = { name: 'list' }"
		@created="(id: string) => (view = { name: 'detail', id })" />
	<AssemblyDetail
		v-else
		:assembly-id="view.id"
		@back="view = { name: 'list' }" />
</template>
