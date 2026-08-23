import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Builds a single IIFE bundle into the repo's js/ + css/ folders, which
// nc_py_api serves and the AppAPI embedded page loads.
export default defineConfig({
	plugins: [vue()],
	build: {
		outDir: '..',
		emptyOutDir: false,
		cssCodeSplit: false,
		rollupOptions: {
			input: 'src/main.ts',
			output: {
				format: 'iife',
				inlineDynamicImports: true,
				entryFileNames: 'js/citizens-main.js',
				assetFileNames: (assetInfo) =>
					assetInfo.names?.some((n) => n.endsWith('.css'))
						? 'css/citizens-main.css'
						: 'assets/[name][extname]',
			},
		},
	},
})
