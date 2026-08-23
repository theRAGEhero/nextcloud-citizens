import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Recorder bundle: served on PUBLIC routes at /recorder/static/, no Nextcloud chrome.
export default defineConfig({
	plugins: [vue()],
	build: {
		outDir: '../recorder_static',
		emptyOutDir: true,
		cssCodeSplit: false,
		rollupOptions: {
			input: 'src/recorder/main.ts',
			output: {
				format: 'iife',
				inlineDynamicImports: true,
				entryFileNames: 'citizens-recorder.js',
				assetFileNames: (assetInfo) =>
					assetInfo.names?.some((n) => n.endsWith('.css'))
						? 'citizens-recorder.css'
						: '[name][extname]',
			},
		},
	},
})
