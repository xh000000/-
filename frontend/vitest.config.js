import {defineConfig} from 'vitest/config';
import vue from '@vitejs/plugin-vue';
export default defineConfig({plugins:[vue()],test:{environment:'jsdom',include:['tests/**/*.component.test.js'],pool:'forks',maxWorkers:1,minWorkers:1,testTimeout:10000}});
