// SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
// SPDX-License-Identifier: AGPL-3.0-or-later
import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

function mount(): void {
	const content = document.getElementById('content') ?? document.body
	const root = document.createElement('div')
	root.id = 'citizens-app'
	content.innerHTML = ''
	content.appendChild(root)
	createApp(App).mount(root)
}

if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', mount)
} else {
	mount()
}
