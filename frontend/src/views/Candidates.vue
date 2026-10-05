<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref<any[]>([])
const papers = ref<any[]>([])
const halls = ref<any[]>([])
const hallId = ref<number>(1)
const bulk = ref('')
const loading = ref(false)
const message = ref<{ ok: boolean; text: string } | null>(null)
const errors = ref<any[]>([])

async function refresh() {
  rows.value = await api('/candidates')
}

onMounted(async () => {
  const [h, p] = await Promise.all([api('/halls'), api('/papers')])
  halls.value = h
  papers.value = p
  if (h.length) hallId.value = h[0].id
  await refresh()
})

async function submit() {
  loading.value = true
  message.value = null
  errors.value = []
  const candidates = bulk.value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, ticket_no, paper_code] = line.split(/[,，]/).map((s) => s.trim())
      return { name, ticket_no, paper_code, hall_id: hallId.value }
    })

  try {
    const res = await api('/candidates/batch', {
      method: 'POST',
      body: JSON.stringify({ candidates }),
    })
    bulk.value = ''
    message.value = {
      ok: true,
      text: `整批写入成功，共 ${res.inserted} 人。旧排座图保持不变，需到「排座图」手动重新排座后新人才会上座。`,
    }
    await refresh()
  } catch (e: any) {
    let detail: any = {}
    try { detail = JSON.parse(e.message || '{}') } catch { /* keep defaults */ }
    message.value = {
      ok: false,
      text: detail.message || '整批非法，已全部驳回，零写入，名单与当前排座不变。',
    }
    errors.value = detail.errors || []
  } finally {
    loading.value = false
  }
}
</script>
<template>
  <h1>考生名册</h1>
  <p class="sub">批量录入：每行「姓名,准考证号,试卷代码」。全部合法才写入，任一行非法整批失败、零写入。</p>

  <div class="card">
    <div style="margin-bottom:0.5rem; font-family:'Segoe UI',sans-serif; font-size:0.85rem">
      <label>考室：
        <select v-model.number="hallId">
          <option v-for="h in halls" :key="h.id" :value="h.id">{{ h.code }} · {{ h.name }}</option>
        </select>
      </label>
      <span class="muted" style="margin-left:0.75rem">
        可用试卷代码：{{ papers.map(p => p.code).join('、') }}
      </span>
    </div>
    <textarea
      v-model="bulk"
      rows="6"
      style="width:100%; font-family:'Segoe UI',sans-serif; font-size:0.85rem; padding:0.5rem"
      placeholder="陈一,T2026010,P-A&#10;李二,T2026011,P-B&#10;张三,T2026012,P-A"
    ></textarea>
    <div style="margin-top:0.5rem">
      <button class="btn" :disabled="loading || !bulk.trim()" @click="submit">
        {{ loading ? '提交中…' : '整批提交' }}
      </button>
      <span class="muted" style="margin-left:0.75rem; font-size:0.78rem">提交后不会自动重排座位</span>
    </div>
    <p v-if="message" :style="{ color: message.ok ? 'var(--hs-ok)' : 'var(--hs-bad)', marginBottom: errors.length ? '0.4rem' : '0' }"
       style="font-family:'Segoe UI',sans-serif; font-size:0.84rem; margin-top:0.6rem">
      {{ message.ok ? '✓ ' : '✗ ' }}{{ message.text }}
    </p>
    <div v-if="errors.length" style="margin-top:0.4rem; font-family:'Segoe UI',sans-serif; font-size:0.8rem; color:var(--hs-bad)">
      <div v-for="(er, i) in errors" :key="i">第 {{ er.index + 1 }} 行<span v-if="er.ticket_no">（{{ er.ticket_no }}）</span>：{{ er.message }}</div>
    </div>
  </div>

  <div class="hs-clipboard" style="max-width:420px">
    <h2>考生名册 · Clipboard（{{ rows.length }} 人）</h2>
    <div v-for="r in rows" :key="r.id ?? JSON.stringify(r)" class="hs-roster-row">
      <div>
        <div>{{ r.name }}</div>
        <div class="hs-ticket">{{ r.ticket_no }}</div>
      </div>
      <div>卷{{ r.paper_id }} · 室{{ r.hall_id }}</div>
    </div>
    <p v-if="!rows.length" class="muted" style="padding:0.6rem 0.75rem">名册为空</p>
  </div>
</template>
