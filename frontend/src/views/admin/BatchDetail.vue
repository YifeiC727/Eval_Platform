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
            <el-form-item label="选择标注员">
              <el-select v-model="selectedAnnotators" multiple placeholder="选择标注员" style="width: 100%;">
                <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
              </el-select>
            </el-form-item>
            <el-button type="primary" @click="doAssign" :loading="assigning"
              :disabled="selectedAnnotators.length < (batch.annotation_mode === 'dual' ? 2 : 1)">
              分配未分配的视频
            </el-button>
          </el-form>
          <el-alert v-if="assignResult" :title="assignResult" type="success" show-icon style="margin-top: 16px;" />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="进度监控" name="monitor">
        <el-table :data="progress" stripe max-height="500">
          <el-table-column prop="video_id" label="视频" width="80" />
          <el-table-column prop="question_id" label="题目" width="80" />
          <el-table-column prop="prompt_summary" label="Prompt" min-width="180" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="annotator_a" label="标注员" width="80" />
          <el-table-column prop="finalized" label="定案" width="60" />
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
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../api.js'

const props = defineProps(['batch', 'annotators'])
const emit = defineEmits(['refresh'])

const activeTab = ref('assign')
const selectedAnnotators = ref([])
const assigning = ref(false)
const assignResult = ref('')
const progress = ref([])
const scores = ref([])

watch(() => props.batch, (b) => {
  if (b) {
    loadProgress()
    loadScores()
  }
}, { immediate: true })

function statusType(s) {
  const map = { '未分配': 'info', '已分配待标注': '', '已定案': 'success', '待第三人': 'warning' }
  return map[s] || ''
}

async function loadProgress() {
  if (!props.batch) return
  try {
    const { data } = await api.get('/assignments/progress', { params: { project_id: props.batch.bank_id, page_size: 999 } })
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
    })
    assignResult.value = `分配完成: 创建 ${data.created} 个任务, 覆盖 ${data.videos_assigned} 个视频`
    emit('refresh')
    loadProgress()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '分配失败')
  } finally { assigning.value = false }
}

function doExport() {
  window.open(`/api/export/results?project_id=${props.batch.bank_id}`, '_blank')
}
</script>
