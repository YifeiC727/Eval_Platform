<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <el-page-header title="结果看板" :icon="null" />
      <div style="display: flex; gap: 12px; align-items: center;">
        <el-radio-group v-model="filterTaskType" size="small" @change="onTaskTypeChange">
          <el-radio-button value="t2v">T2V</el-radio-button>
          <el-radio-button value="t2av">T2AV</el-radio-button>
        </el-radio-group>
        <el-switch v-model="filterPE" active-text="PE" inactive-text="基础" style="margin: 0 4px;" @change="onPEChange" />
        <el-select v-model="selectedBatch" placeholder="选择批次" clearable size="default" style="width: 280px;" @change="onBatchChange">
          <el-option label="全部批次（汇总）" :value="null" />
          <el-option v-for="b in filteredBatches" :key="b.id" :label="b.name + (b.model_version ? ' (' + b.model_version + ')' : '')" :value="b.id" />
        </el-select>
      </div>
    </div>

    <!-- T2AV 模块得分卡片 -->
    <el-row v-if="moduleScores && selectedBatchTaskType === 't2av' && !filterPE" :gutter="16" style="margin-top: 16px;">
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="视频层 (Visual)" :value="moduleScores.visual?.score || 0" suffix="分" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="声音层 (Audio)" :value="moduleScores.audio?.score || 0" suffix="分" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="音画同步 (AV Sync)" :value="moduleScores.av_sync?.score || 0" suffix="分" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="综合分" :value="moduleScores.overall || 0" suffix="分" /></el-card></el-col>
    </el-row>

    <!-- ===== PE模式看板 ===== -->
    <div v-if="filterPE">
      <!-- PE总览指标 -->
      <el-row :gutter="16" style="margin-top: 16px;">
        <el-col :span="4"><el-card shadow="hover"><el-statistic title="A(直出)得分" :value="peOverview.a_score || 0" :precision="1" suffix="分" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="hover"><el-statistic title="B(PE)得分" :value="peOverview.b_score || 0" :precision="1" suffix="分" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="hover"><el-statistic title="PE增益Δ" :value="peOverview.delta || 0" :precision="1" :value-style="{ color: (peOverview.delta || 0) > 0 ? '#67c23a' : (peOverview.delta || 0) < 0 ? '#e6393e' : '#909399' }" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="hover"><el-statistic title="B更好(胜)" :value="peOverview.b_better || 0" :suffix="`/${peOverview.total || 0}`" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="hover"><el-statistic title="持平(平)" :value="peOverview.tie || 0" :suffix="`/${peOverview.total || 0}`" /></el-card></el-col>
        <el-col :span="4"><el-card shadow="hover"><el-statistic title="B更差(负)" :value="peOverview.b_worse || 0" :suffix="`/${peOverview.total || 0}`" /></el-card></el-col>
      </el-row>

      <!-- PE能力维度增益表 -->
      <el-card style="margin-top: 20px;">
        <template #header><span style="font-weight: 600;">能力维度 PE 增益（Δ 从低到高）</span></template>
        <el-table :data="peAbilities" stripe max-height="500" :default-sort="{ prop: 'delta', order: 'ascending' }">
          <el-table-column prop="ability_id" label="ID" width="60" />
          <el-table-column prop="ability_name" label="能力名称" min-width="180" />
          <el-table-column prop="a_score" label="A得分" width="80">
            <template #default="{ row }"><span style="color: #909399;">{{ row.a_score ?? '-' }}</span></template>
          </el-table-column>
          <el-table-column prop="b_score" label="B得分" width="80">
            <template #default="{ row }"><span style="color: #409eff;">{{ row.b_score ?? '-' }}</span></template>
          </el-table-column>
          <el-table-column prop="delta" label="增益Δ" width="90" sortable>
            <template #default="{ row }">
              <span :style="{ color: (row.delta||0) > 0 ? '#67c23a' : (row.delta||0) < 0 ? '#e6393e' : '#999', fontWeight: 600 }">
                {{ row.delta != null ? ((row.delta > 0 ? '+' : '') + row.delta) : '-' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="a_n" label="A-n" width="50" />
          <el-table-column prop="b_n" label="B-n" width="50" />
        </el-table>
      </el-card>

      <!-- PE原因分布 -->
      <el-row :gutter="20" style="margin-top: 20px;">
        <el-col :span="12">
          <el-card>
            <template #header><span style="font-weight: 600;">增值原因分布（B更好时）</span></template>
            <el-table :data="peReasons.filter(r => r.type === 'better')" stripe size="small">
              <el-table-column prop="reason" label="原因" />
              <el-table-column prop="count" label="次数" width="70" />
              <el-table-column prop="pct" label="占比" width="70" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card>
            <template #header><span style="font-weight: 600;">副作用分布（B更差时）</span></template>
            <el-table :data="peReasons.filter(r => r.type === 'worse')" stripe size="small">
              <el-table-column prop="reason" label="原因" />
              <el-table-column prop="count" label="次数" width="70" />
              <el-table-column prop="pct" label="占比" width="70" />
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- ===== 基础评测看板（非PE时显示）===== -->
    <div v-if="!filterPE">

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
      <el-table :data="filteredAbilities" stripe style="width: 100%;" max-height="500">
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
          <el-table-column v-for="b in filteredBatches" :key="b.id" :label="b.model_version || b.name" min-width="140">
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
          <el-table :data="filteredFailCodes" stripe size="small">
            <el-table-column prop="code" label="码" width="60" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="count" label="次数" width="80" sortable />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header><span style="font-weight: 600;">三级标签诊断（得分最低前20）</span></template>
          <el-table :data="filteredTags.slice(0, 20)" stripe size="small">
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
          <el-option v-for="b in filteredBatches" :key="b.id" :label="`${b.name} (${b.model_version})`" :value="b.id" />
        </el-select>
        <span style="font-size: 18px; font-weight: 600;">VS</span>
        <el-select v-model="compareB" placeholder="选择批次B" style="width: 250px;">
          <el-option v-for="b in filteredBatches" :key="b.id" :label="`${b.name} (${b.model_version})`" :value="b.id" />
        </el-select>
        <el-button type="primary" @click="doCompare" :disabled="!compareA || !compareB || compareA === compareB" :loading="comparing">
          对比
        </el-button>
      </div>
      <el-table v-if="comparison" :data="filteredComparison" stripe :row-class-name="deltaRowClass">
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
    </div><!-- end !filterPE -->
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api.js'

const abilities = ref([])
const quality = ref({})
const failCodes = ref([])
const tags = ref([])
const batches = ref([])
const selectedBatch = ref(null)
const filterTaskType = ref('t2v')
const filterPE = ref(false)
const moduleScores = ref(null)
const compareA = ref(null)
const compareB = ref(null)
const comparison = ref(null)
const comparing = ref(false)

// PE data
const peOverview = ref({})
const peAbilities = ref([])
const peReasons = ref([])

const filteredBatches = computed(() => {
  return batches.value.filter(b => {
    const typeMatch = !filterTaskType.value || (b.task_type || 't2v') === filterTaskType.value
    const peMatch = filterPE.value ? b.eval_mode === 'pe' : b.eval_mode !== 'pe'
    return typeMatch && peMatch
  })
})

const selectedBatchTaskType = computed(() => {
  if (!selectedBatch.value) return filterTaskType.value || null
  const b = batches.value.find(x => x.id === selectedBatch.value)
  return b?.task_type || 't2v'
})

function isAbilityForTaskType(abilityId) {
  if (filterTaskType.value === 't2v') return abilityId?.startsWith('C')
  return true // t2av shows all
}

const filteredAbilities = computed(() => {
  return abilities.value.filter(a => isAbilityForTaskType(a.ability_id))
})

const filteredFailCodes = computed(() => {
  if (filterTaskType.value === 't2v') {
    return failCodes.value.filter(f => f.code?.startsWith('F'))
  }
  return failCodes.value
})

const filteredTags = computed(() => {
  if (filterTaskType.value === 't2v') {
    // T2V tags start with D (not AD, not AVD)
    return tags.value.filter(t => t.tag_id && t.tag_id.startsWith('D') && !t.tag_id.startsWith('AD') && !t.tag_id.startsWith('AVD'))
  }
  return tags.value
})

const filteredComparison = computed(() => {
  if (!comparison.value) return []
  return comparison.value.comparison.filter(a => isAbilityForTaskType(a.ability_id))
})

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
      // All batches of current type: load each batch's scores for comparison
      const allScores = {}
      for (const b of filteredBatches.value) {
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
        const aAvg = filteredBatches.value.reduce((s, bt) => s + (a[`score_${bt.id}`] || 0), 0) / (filteredBatches.value.length || 1)
        const bAvg = filteredBatches.value.reduce((s, bt) => s + (b[`score_${bt.id}`] || 0), 0) / (filteredBatches.value.length || 1)
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
  if (filterPE.value) {
    await loadPEData()
  } else {
    await Promise.all([loadAbilities(), loadQuality(), loadFailCodes(), loadTags(), loadModuleScores()])
  }
}

function onTaskTypeChange() {
  selectedBatch.value = null
  moduleScores.value = null
  onBatchChange()
}

function onPEChange() {
  selectedBatch.value = null
  moduleScores.value = null
  peOverview.value = {}
  peAbilities.value = []
  peReasons.value = []
  onBatchChange()
}

async function loadPEData() {
  if (!filterPE.value || !selectedBatch.value) {
    peOverview.value = {}
    peAbilities.value = []
    peReasons.value = []
    return
  }
  try {
    const { data } = await api.get('/scores/pe-overview', { params: { batch_id: selectedBatch.value } })
    peOverview.value = data.overview || {}
    peAbilities.value = data.abilities || []
    peReasons.value = data.reasons || []
  } catch {
    peOverview.value = {}
    peAbilities.value = []
    peReasons.value = []
  }
}

async function loadModuleScores() {
  if (selectedBatch.value && selectedBatchTaskType.value === 't2av') {
    try {
      const { data } = await api.get('/scores/modules', { params: { batch_id: selectedBatch.value } })
      moduleScores.value = data
    } catch { moduleScores.value = null }
  } else {
    moduleScores.value = null
  }
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
