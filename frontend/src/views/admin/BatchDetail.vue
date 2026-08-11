<template>
  <div v-if="batch">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
      <div>
        <h2 style="margin: 0;">{{ batch.name }}</h2>
        <p style="color: #666; margin: 4px 0 0;">题库: {{ batch.bank_name }} | 模型: {{ batch.model_version }} | 模式: {{ batch.annotation_mode === 'dual' ? '双人盲标' : '单人标注' }}</p>
      </div>
      <el-tag :type="batch.status === 'completed' ? 'success' : batch.status === 'labeling' ? 'warning' : 'info'" size="large">
        {{ batch.status === 'completed' ? '已完成' : batch.status === 'labeling' ? '标注中' : '准备中' }}
      </el-tag>
    </div>

    <el-row :gutter="16" style="margin-bottom: 20px;">
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="视频总数" :value="batch.total_videos" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="已分配" :value="batch.assigned_videos" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="已提交" :value="batch.submitted_assignments" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="已定案" :value="batch.finalized_checkpoints" /></el-card></el-col>
    </el-row>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="分配任务" name="assign">
        <el-card>
          <el-form label-position="top">
            <el-form-item label="标注模式">
              <el-radio-group v-model="assignMode">
                <el-radio-button value="single">单人标注</el-radio-button>
                <el-radio-button value="dual">双人盲标</el-radio-button>
              </el-radio-group>
              <p style="color: #999; font-size: 12px; margin-top: 4px;">
                {{ assignMode === 'dual' ? '每个视频分配2人独立标注，不一致时引入第三人' : '每个视频仅1人标注，直接出结果' }}
              </p>
            </el-form-item>
            <el-form-item label="分配方式">
              <el-radio-group v-model="assignMethod">
                <el-radio-button value="round_robin">均匀轮转</el-radio-button>
                <el-radio-button value="manual">手动指派</el-radio-button>
                <el-radio-button value="ai">AI 帮填</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="选择标注员">
              <el-select v-model="selectedAnnotators" multiple placeholder="选择标注员" style="width: 100%;">
                <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
              </el-select>
            </el-form-item>

            <!-- AI 指令 -->
            <el-form-item v-if="assignMethod === 'ai'" label="分配指令">
              <el-input v-model="aiInstruction" type="textarea" :rows="2" placeholder="如：每人平均分配、前100个给标注员01和02..." />
            </el-form-item>

            <div style="display: flex; gap: 12px;">
              <el-button @click="previewAssign" :loading="previewing"
                :disabled="selectedAnnotators.length < (assignMode === 'dual' ? 2 : 1)">
                预览分配
              </el-button>
              <el-button type="primary" @click="doAssign" :loading="assigning"
                :disabled="selectedAnnotators.length < (assignMode === 'dual' ? 2 : 1)">
                确认执行
              </el-button>
            </div>
          </el-form>

          <!-- 预览结果 -->
          <div v-if="previewData" style="margin-top: 20px; border-top: 1px solid #eee; padding-top: 16px;">
            <p><strong>待分配:</strong> {{ previewData.total_to_assign }} 个视频</p>
            <p style="margin-top: 8px;"><strong>每人任务量:</strong></p>
            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0;">
              <el-tag v-for="(count, name) in previewData.per_person" :key="name">{{ name }}: {{ count }}</el-tag>
            </div>
          </div>

          <el-alert v-if="assignResult" :title="assignResult" type="success" show-icon style="margin-top: 16px;" />
        </el-card>

        <!-- 已分配人员列表 -->
        <el-card style="margin-top: 16px;" v-if="assignedAnnotators.length">
          <template #header><span style="font-weight: 600;">已分配的标注员</span></template>
          <el-table :data="assignedAnnotators" stripe size="small">
            <el-table-column prop="name" label="标注员" />
            <el-table-column prop="count" label="任务数" width="80" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button size="small" type="danger" link @click="kickAnnotator(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="进度监控" name="monitor">
        <div style="display: flex; gap: 12px; margin-bottom: 12px;">
          <el-select v-model="filterStatus" placeholder="筛选状态" clearable size="small" style="width: 140px;">
            <el-option label="未分配" value="未分配" />
            <el-option label="已分配待标注" value="已分配待标注" />
            <el-option label="A/B部分提交" value="A/B部分提交" />
            <el-option label="已定案" value="已定案" />
          </el-select>
          <el-select v-model="filterAnnotator" placeholder="筛选标注员" clearable size="small" style="width: 140px;">
            <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.display_name || u.username" />
          </el-select>
        </div>
        <el-table :data="filteredProgress" stripe max-height="500">
          <el-table-column prop="video_id" label="视频" width="80" />
          <el-table-column prop="question_id" label="题目" width="80" />
          <el-table-column prop="prompt_summary" label="Prompt" min-width="180" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="annotator_a" label="A" width="80" />
          <el-table-column prop="annotator_b" label="B" width="80" />
          <el-table-column prop="finalized" label="定案" width="60" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button v-if="row.annotator_a" size="small" type="danger" link @click="resetVideo(row)">重置</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="得分结果" name="scores">
        <el-table :data="scores" stripe v-if="scores.length">
          <el-table-column prop="ability_id" label="ID" width="60" />
          <el-table-column prop="ability_name" label="能力" min-width="180" />
          <el-table-column prop="score" label="得分" width="80" sortable>
            <template #default="{ row }">
              <span :style="{ color: row.score < 50 ? '#e6393e' : row.score < 70 ? '#e6a23c' : '#67c23a', fontWeight: 600 }">{{ row.score }}</span>
            </template>
          </el-table-column>
          <el-table-column label="C/R/N" width="100">
            <template #default="{ row }">{{ row.c_count }}/{{ row.r_count }}/{{ row.n_count }}</template>
          </el-table-column>
          <el-table-column prop="total_n" label="n" width="60" />
        </el-table>
        <el-empty v-else description="暂无定案数据" />
      </el-tab-pane>

      <el-tab-pane label="导出" name="export">
        <el-button type="success" size="large" @click="doExport">下载评测结果 Excel</el-button>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api.js'

const props = defineProps(['batch', 'annotators'])
const emit = defineEmits(['refresh'])

const activeTab = ref('assign')
const selectedAnnotators = ref([])
const assignMode = ref('single')
const assignMethod = ref('round_robin')
const aiInstruction = ref('')
const assigning = ref(false)
const previewing = ref(false)
const assignResult = ref('')
const previewData = ref(null)
const progress = ref([])
const scores = ref([])
const filterStatus = ref('')
const filterAnnotator = ref('')
const assignedAnnotators = ref([])

const filteredProgress = computed(() => {
  let list = progress.value
  if (filterStatus.value) list = list.filter(p => p.status === filterStatus.value)
  if (filterAnnotator.value) list = list.filter(p => p.annotator_a === filterAnnotator.value || p.annotator_b === filterAnnotator.value)
  return list
})

watch(() => props.batch, (b) => {
  if (b) {
    assignMode.value = b.annotation_mode || 'single'
    loadProgress()
    loadScores()
    loadAssignedAnnotators()
  }
}, { immediate: true })

function statusType(s) {
  const map = { '未分配': 'info', '已分配待标注': '', '已定案': 'success', '待第三人': 'warning' }
  return map[s] || ''
}

async function loadProgress() {
  if (!props.batch) return
  try {
    const { data } = await api.get('/assignments/progress', { params: { batch_id: props.batch.id, page_size: 999 } })
    progress.value = data.items
  } catch {}
}

async function loadScores() {
  if (!props.batch) return
  try {
    const { data } = await api.get(`/batches/${props.batch.id}/scores`)
    scores.value = data
  } catch {}
}

async function doAssign() {
  assigning.value = true
  assignResult.value = ''
  try {
    const { data } = await api.post(`/batches/${props.batch.id}/assign`, {
      annotator_ids: selectedAnnotators.value,
      annotation_mode: assignMode.value,
    })
    assignResult.value = `分配完成: 创建 ${data.created} 个任务, 覆盖 ${data.videos_assigned} 个视频`
    previewData.value = null
    emit('refresh')
    loadProgress()
    loadAssignedAnnotators()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '分配失败')
  } finally { assigning.value = false }
}

async function previewAssign() {
  previewing.value = true
  previewData.value = null
  try {
    const { data } = await api.post(`/batches/${props.batch.id}/assign-preview`, {
      annotator_ids: selectedAnnotators.value,
      annotation_mode: assignMode.value,
    })
    previewData.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '预览失败')
  } finally { previewing.value = false }
}

async function loadAssignedAnnotators() {
  if (!props.batch) return
  try {
    const { data } = await api.get('/assignments/progress', { params: { batch_id: props.batch.id, page_size: 9999 } })
    const countMap = {}
    for (const item of data.items) {
      if (item.annotator_a) countMap[item.annotator_a] = (countMap[item.annotator_a] || 0) + 1
      if (item.annotator_b) countMap[item.annotator_b] = (countMap[item.annotator_b] || 0) + 1
    }
    assignedAnnotators.value = Object.entries(countMap).map(([name, count]) => ({ name, count }))
  } catch {}
}

async function kickAnnotator(row) {
  try {
    await ElMessageBox.confirm(`移除「${row.name}」？将释放该标注员在此批次中的所有任务。`, '移除标注员', { type: 'warning' })
    await api.post('/assignments/reset-single-by-annotator', {
      batch_id: props.batch.id,
      annotator_name: row.name,
    })
    ElMessage.success(`已移除「${row.name}」的 ${row.count} 个任务`)
    loadProgress()
    loadAssignedAnnotators()
    emit('refresh')
  } catch {}
}

function doExport() {
  window.open(`/api/export/results?project_id=${props.batch.bank_id}`, '_blank')
}

async function resetVideo(row) {
  try {
    await ElMessageBox.confirm(`重置视频「${row.video_id}」的标注？`, '重置', { type: 'warning' })
    await api.post('/assignments/reset-single', { video_id: row.video_id })
    ElMessage.success('已重置')
    loadProgress()
  } catch {}
}
</script>
