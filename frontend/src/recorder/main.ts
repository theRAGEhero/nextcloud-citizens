// SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
// SPDX-License-Identifier: AGPL-3.0-or-later
import { createApp } from 'vue'
import RecorderApp from './RecorderApp.vue'
import './style.css'

const root = document.getElementById('recorder-app') ?? document.body
root.innerHTML = ''
createApp(RecorderApp).mount(root)
