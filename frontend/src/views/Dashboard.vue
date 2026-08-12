<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <el-page-header title="结果看板" :icon="null" />
      <el-select v-model="selectedBatch" placeholder="选择批次" clearable size="default" style="width: 280px;" @change="onBatchChange">
        <el-option label="全部批次（汇总）" :value="null" />
        <el-option v-for="b in batches" :key="b.id" :label="b.name + (b.model_version ? ' (' + b.model_version + ')' : '')" :value="b.id" />
      </el-select>
    </div>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="6">
        <el-statistic title="已比对检查点" :value="quality.total_checkpoints_compared || 0" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="A/B一致率(检查点)" :value="quality.agreement_rate || 0" suffix="%" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="需第三人(检查点)" :value="quality.third_needed || 0" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="待专家仲裁(检查点)" :value="quality.pending_expert || 0" />
      </el-col>
    </el-row>

    <el-card style="margin-top: 20px;">
      <template #header>
        <span style="font-weight: 600;">30项核心能力排名（得分从低到高）</span>
      </template>
      <el-table :data="abilities" stripe style="width: 100%;" max-height="500">
        <el-table-column prop="ability_id" label="ID" width="60" fixed />
        <el-table-column prop="ability_name" label="能力名称" min-width="180" fixed />
        <template v-if="selectedBatch">
          <el-table-column prop="score" label="得分" width="80" sortable>
            <template #default="{ row }">
              <span :style="{ color: row.score < 50 ? '#e6393e' : row.score < 70 ? '#e6a23c' : '#67c23a', fontWeight: 600 }">
                {{ row.score }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="C/R/N" width="120">
            <template #default="{ row }">
              <span style="color: #67c23a;">{{ row.c_count }}</span> /
              <span style="color: #e6a23c;">{{ row.r_count }}</span> /
              <span style="color: #e6393e;">{{ row.n_count }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="total_n" label="有效n" width="70" />
          <el-table-column prop="coverage_status" label="覆盖状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.coverage_status === '正式排名' ? 'success' : row.coverage_status === '初步趋势' ? 'warning' : row.coverage_status === '暂无数据' ? 'info' : 'danger'" size="small">
                {{ row.coverage_status }}
              </el-tag>
            </template>
          </el-table-column>
        </template>
        <template v-else>
          <el-table-column v-for="b in batches" :key="b.id" :label="b.model_version || b.name" min-width="140">
            <template #default="{ row }">
              <div>
                <span :style="{ color: (row['score_' + b.id] || 0) < 50 ? '#e6393e' : (row['score_' + b.id] || 0) < 70 ? '#e6a23c' : '#67c23a', fontWeight: 600 }">
                  {{ row['score_' + b.id] != null ? row['score_' + b.id] : '-' }}
                </span>
                <span v-if="row['crn_' + b.id]" style="color: #999; font-size: 12px; margin-left: 6px;">{{ row['crn_' + b.id] }}</span>
              </div>
            </template>
          </el-table-column>
        </template>
      </el-table>
    </el-card>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card>
          <template #header><span style="font-weight: 600;">失败码分布</span></template>
          <el-table :data="failCodes" stripe size="small">
            <el-table-column prop="code" label="码" width="60" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="count" label="次数" width="80" sortable />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header><span style="font-weight: 600;">三级标签诊断（得分最低前20）</span></template>
          <el-table :data="tags.slice(0, 20)" stripe size="small">
            <el-table-column prop="tag_id" label="ID" width="100" />
            <el-table-column prop="tag_name" label="标签" />
            <el-table-column prop="score" label="得分" width="70" />
            <el-table-column prop="total_n" label="n" width="50" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <!-- 版本对比 -->
    <el-card style="margin-top: 20px;">
      <template #header><span style="font-weight: 600;">版本对比</span></template>
      <div style="display: flex; gap: 16px; align-items: center; margin-bottom: 16px;">
        <el-select v-model="compareA" placeholder="选择批次A" style="width: 250px;">
          <el-option v-for="b in batches" :key="b.id" :label="`${b.name} (${b.model_version})`" :value="b.id" />
        </el-select>
        <span style="font-size: 18px; font-weight: 600;">VS</span>
        <el-select v-model="compareB" placeholder="选择批次B" style="width: 250px;">
          <el-option v-for="b in batches" :key="b.id" :label="`${b.name} (${b.model_version})`" :value="b.id" />
        </el-select>
        <el-button type="primary" @click="doCompare" :disabled="!compareA || !compareB || compareA === compareB" :loading="comparing">
          对比
        </el-button>
      </div>
      <el-table v-if="comparison" :data="comparison.comparison" stripe :row-class-name="deltaRowClass">
        <el-table-column prop="ability_id" label="ID" width="60" />
        <el-table-column prop="ability_name" label="能力" min-width="180" />
        <el-table-column :label="comparison.batch_a.model || 'A'" width="80">
          <template #default="{ row }">{{ row.score_a }}</template>
        </el-table-column>
        <el-table-column :label="comparison.batch_b.model || 'B'" width="80">
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
import api from '../api.js'

const abilities = ref([])
const quality = ref({})
const failCodes = ref([])
const tags = ref([])
const batches = ref([])
const selectedBatch = ref(null)
const compareA = ref(null)
const compareB = ref(null)
const comparison = ref(null)
const comparing = ref(false)

onMounted(async () => {
  try {
    const [abRes, qRes, fcRes, tagRes, batchRes] = await Promise.all([
      api.get('/scores/abilities'),
      api.get('/scores/quality'),
      api.get('/scores/fail-codes'),
      api.get('/scores/tags'),
      api.get('/batches/'),
    ])
    abilities.value = abRes.data
    quality.value = qRes.data
    failCodes.value = fcRes.data
    tags.value = tagRes.data
    batches.value = batchRes.data
  } catch (e) {
    ElMessage.error('加载看板数据失败')
  }
})

async function loadAbilities() {
  try {
    if (selectedBatch.value) {
      const params = { batch_id: selectedBatch.value }
      const { data } = await api.get('/scores/abilities', { params })
      abilities.value = data
    } else {
      // All batches: load each batch's scores for comparison
      const allScores = {}
      for (const b of batches.value) {
        const { data } = await api.get('/scores/abilities', { params: { batch_id: b.id } })
        for (const row of data) {
          if (!allScores[row.ability_id]) {
            allScores[row.ability_id] = { ability_id: row.ability_id, ability_name: row.ability_name }
          }
          allScores[row.ability_id][`score_${b.id}`] = row.score
          allScores[row.ability_id][`crn_${b.id}`] = `${row.c_count}/${row.r_count}/${row.n_count}`
        }
      }
      abilities.value = Object.values(allScores).sort((a, b) => {
        const aAvg = batches.value.reduce((s, bt) => s + (a[`score_${bt.id}`] || 0), 0) / batches.value.length
        const bAvg = batches.value.reduce((s, bt) => s + (b[`score_${bt.id}`] || 0), 0) / batches.value.length
        return aAvg - bAvg
      })
    }
  } catch (e) {
    ElMessage.error('加载能力数据失败')
  }
}

async function loadQuality() {
  try {
    const params = selectedBatch.value ? { batch_id: selectedBatch.value } : {}
    const { data } = await api.get('/scores/quality', { params })
    quality.value = data
  } catch {}
}

async function loadFailCodes() {
  try {
    const params = selectedBatch.value ? { batch_id: selectedBatch.value } : {}
    const { data } = await api.get('/scores/fail-codes', { params })
    failCodes.value = data
  } catch {}
}

async function loadTags() {
  try {
    const params = selectedBatch.value ? { batch_id: selectedBatch.value } : {}
    const { data } = await api.get('/scores/tags', { params })
    tags.value = data
  } catch {}
}

async function onBatchChange() {
  await Promise.all([loadAbilities(), loadQuality(), loadFailCodes(), loadTags()])
}

function deltaRowClass({ row }) {
  if (row.delta > 5) return 'good-row'
  if (row.delta < -5) return 'bad-row'
  return ''
}

async function doCompare() {
  comparing.value = true
  try {
    const { data } = await api.get('/batches/compare', { params: { batch_a: compareA.value, batch_b: compareB.value } })
    comparison.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '对比失败')
  } finally { comparing.value = false }
}
</script>

<style scoped>
:deep(.good-row) { background-color: #f0f9eb !important; }
:deep(.bad-row) { background-color: #fef0f0 !important; }
</style>
