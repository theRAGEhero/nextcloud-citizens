import { createApp } from 'vue'
import RecorderApp from './RecorderApp.vue'
import './style.css'

const root = document.getElementById('recorder-app') ?? document.body
root.innerHTML = ''
createApp(RecorderApp).mount(root)
