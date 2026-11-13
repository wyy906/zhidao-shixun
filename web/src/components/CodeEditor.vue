<script setup lang="ts">
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()

const container = ref<HTMLDivElement | null>(null)
let editor: monaco.editor.IStandaloneCodeEditor | null = null
let suppress = false

// V2-04F2：Monaco 接入（python tokenizer 为纯前端实现，无需语言 worker；
// 编辑器 worker 按官方 vite 方式加载）。
;(window as unknown as { MonacoEnvironment: monaco.Environment }).MonacoEnvironment = {
  getWorker: () => new editorWorker(),
}

onMounted(() => {
  if (!container.value) return
  editor = monaco.editor.create(container.value, {
    value: props.modelValue,
    language: 'python',
    theme: 'vs',
    fontSize: 13,
    minimap: { enabled: false },
    automaticLayout: true,
    scrollBeyondLastLine: false,
    tabSize: 4,
  })
  editor.onDidChangeModelContent(() => {
    if (suppress) return
    emit('update:modelValue', editor?.getValue() ?? '')
  })
})

watch(
  () => props.modelValue,
  (value) => {
    if (!editor || editor.getValue() === value) return
    suppress = true
    editor.setValue(value)
    suppress = false
  },
)

onBeforeUnmount(() => editor?.dispose())
</script>

<template>
  <div ref="container" class="editor-host" />
</template>

<style scoped>
.editor-host {
  width: 100%;
  height: 220px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  overflow: hidden;
}
</style>
