<template>
  <div>
    <h2 style="margin-bottom: 16px;">版本对比</h2>

    <el-card style="margin-bottom: 20px;">
      <div style="display: flex; gap: 16px; align-items: center;">
        <el-select v-model="batchA" placeholder="选择批次A" style="width: 250px;">
          <el-option v-for="b in batchList" :key="b.id" :label="`${b.name} (${b.model_version})`" :value="b.id" />
        </el-select>
        <span style="font-size: 18px; font-weight: 600;">VS</span>
        <el-select v-model="batchB" placeholder="选择批次B" style="width: 250px;">
          <el-option v-for="b in batchList" :key="b.id" :label="`${b.name} (${b.model_version})`" :value="b.id" />
        </el-select>
        <el-button type="primary" @click="doCompare" :disabled="!batchA || !batchB || batchA === batchB" :loading="loading">
          对比
        </el-button>
      </div>
    </el-card>

    <el-card v-if="comparison">
      <template #header>
        <span style="font-weight: 600;">
          {{ comparison.batch_a.model }} vs {{ comparison.batch_b.model }} — 能力得分变化
        </span>
      </template>
      <el-table :data="comparison.comparison" stripe :row-class-name="deltaRowClass">
        <el-table-column prop="ability_id" label="ID" width="60" />
        <el-table-column prop="ability_name" label="能力" min-width="180" />
        <el-table-column label="A得分" width="80">
          <template #default="{ row }">{{ row.score_a }}</template>
        </el-table-column>
        <el-table-column label="B得分" width="80">
          <template #default="{ row }">{{ row.score_b }}</template>
        </el-table-column>
        <el-table-column label="Δ" width="80" sortable :sort-by="'delta'">
          <template #default="{ row }">
            <span :style="{ color: row.delta > 0 ? '#67c23a' : row.delta < 0 ? '#e6393e' : '#999', fontWeight: 600 }">
              {{ row.delta > 0 ? '+' : '' }}{{ row.delta }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变化" width="60">
          <template #default="{ row }">
            <span v-if="row.delta > 2" style="color: #67c23a;">↑</span>
            <span v-else-if="row.delta < -2" style="color: #e6393e;">↓</span>
            <span v-else style="color: #999;">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="n_a" label="nA" width="50" />
        <el-table-column prop="n_b" label="nB" width="50" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../api.js'

const props = defineProps(['batches'])

const batchA = ref(null)
const batchB = ref(null)
const comparison = ref(null)
const loading = ref(false)
const batchList = ref([])

onMounted(async () => {
  const { data } = await api.get('/batches/')
  batchList.value = data
})

function deltaRowClass({ row }) {
  if (row.delta > 5) return 'good-row'
  if (row.delta < -5) return 'bad-row'
  return ''
}

async function doCompare() {
  loading.value = true
  try {
    const { data } = await api.get('/batches/compare', { params: { batch_a: batchA.value, batch_b: batchB.value } })
    comparison.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '对比失败')
  } finally { loading.value = false }
}
</script>

<style scoped>
:deep(.good-row) { background-color: #f0f9eb !important; }
:deep(.bad-row) { background-color: #fef0f0 !important; }
</style>
