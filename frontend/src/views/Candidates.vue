<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

interface Row { name: string; ticket_no: string; paper_id: number; hall_id: number }

const rows = ref<any[]>([])
const halls = ref<any[]>([])
const papers = ref<any[]>([])
const batch = ref<Row[]>([{ name: '', ticket_no: '', paper_id: 1, hall_id: 1 }])
const okMsg = ref('')
const errors = ref<string[]>([])
const busy = ref(false)

async function reload() { rows.value = await api('/candidates') }

onMounted(async () => {
  const [c, h, p] = await Promise.all([api('/candidates'), api('/halls'), api('/papers')])
  rows.value = c
  halls.value = h
  papers.value = p
  if (h.length) batch.value[0].hall_id = h[0].id
  if (p.length) batch.value[0].paper_id = p[0].id
})

function addRow() {
  batch.value.push({
    name: '', ticket_no: '',
    paper_id: papers.value[0]?.id ?? 1,
    hall_id: halls.value[0]?.id ?? 1,
  })
}
function removeRow(i: number) { batch.value.splice(i, 1) }

async function submitBatch() {
  okMsg.value = ''
  errors.value = []
  busy.value = true
  try {
    // 整批一次提交：后端全部合法才写入，任一非法则整批零写入；
    // 成功也只写名册，不回刷座位方案 —— 需到排座页重新排座才生效。
    const created = await api<any[]>('/candidates/batch', {
      method: 'POST',
      body: JSON.stringify({ candidates: batch.value }),
    })
    okMsg.value = `已写入 ${created.length} 人；当前座位方案保持不变，重新排座后新考生才会入座。`
    batch.value = [{ name: '', ticket_no: '', paper_id: papers.value[0]?.id ?? 1, hall_id: halls.value[0]?.id ?? 1 }]
    await reload()
  } catch (e: any) {
    try {
      const detail = JSON.parse(e.message)?.detail
      errors.value = Array.isArray(detail) ? detail.map(String) : [String(detail ?? e.message)]
    } catch { errors.value = [String(e.message ?? e)] }
  } finally { busy.value = false }
}
</script>

<template>
  <h1>考生名册</h1>
  <p class="sub">夹板名册样式 · 支持一批多名考生整批提交（全合法才写入）</p>
  <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:flex-start">
    <div class="hs-clipboard" style="max-width:420px">
      <h2>考生名册 · Clipboard</h2>
      <div v-for="r in rows" :key="r.id ?? JSON.stringify(r)" class="hs-roster-row">
        <div>
          <div>{{ r.name }}</div>
          <div class="hs-ticket">{{ r.ticket_no }}</div>
        </div>
        <div>卷{{ r.paper_id }} · 室{{ r.hall_id }}</div>
      </div>
    </div>
    <div class="card" style="min-width:340px;flex:1;max-width:560px">
      <h2 style="margin-top:0">整批录入</h2>
      <p class="muted" style="font-size:0.8rem">
        一批多名一次提交：任一名非法则整批失败、零写入；批成功不回刷旧座位，需重新排座。
      </p>
      <div v-for="(r, i) in batch" :key="i" style="display:flex;gap:0.4rem;margin-bottom:0.4rem;align-items:center">
        <input v-model="r.name" placeholder="姓名" style="width:7rem" />
        <input v-model="r.ticket_no" placeholder="准考证号" style="width:9rem" />
        <select v-model="r.paper_id">
          <option v-for="p in papers" :key="p.id" :value="p.id">{{ p.code }}</option>
        </select>
        <select v-model="r.hall_id">
          <option v-for="h in halls" :key="h.id" :value="h.id">{{ h.name }}</option>
        </select>
        <button class="btn" style="padding:0.2rem 0.5rem" @click="removeRow(i)" :disabled="batch.length <= 1">−</button>
      </div>
      <div style="display:flex;gap:0.5rem;margin-top:0.6rem">
        <button class="btn" @click="addRow">添加一行</button>
        <button class="btn" :disabled="busy" @click="submitBatch">提交整批</button>
      </div>
      <p v-if="okMsg" class="badge badge-ok" style="margin-top:0.6rem;display:inline-block">{{ okMsg }}</p>
      <ul v-if="errors.length" style="margin-top:0.6rem;color:var(--hs-bad);font-size:0.8rem;padding-left:1.1rem">
        <li v-for="(e, i) in errors" :key="i">{{ e }}</li>
      </ul>
    </div>
  </div>
</template>
