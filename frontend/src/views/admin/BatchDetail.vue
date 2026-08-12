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
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="视频总数" :value="batch.total_videos" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="已分配" :value="batch.assigned_videos" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover">
        <el-statistic title="A(主标)" :value="roleStats.A.submitted + '/' + roleStats.A.total" />
      </el-card></el-col>
      <el-col :span="4"><el-card shadow="hover">
        <el-statistic title="B(副标)" :value="roleStats.B.submitted + '/' + roleStats.B.total" />
      </el-card></el-col>
      <el-col :span="4"><el-card shadow="hover">
        <el-statistic title="C(仲裁)" :value="roleStats.C.submitted + '/' + roleStats.C.total" />
      </el-card></el-col>
      <el-col :span="4"><el-card shadow="hover">
        <el-statistic title="专家裁决" :value="roleStats.expert.submitted + '/' + roleStats.expert.total" />
      </el-card></el-col>
    </el-row>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="分配任务" name="assign">
        <!-- Step 1: 项目成员 -->
        <el-card style="margin-bottom: 16px;">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600;">项目成员</span>
              <el-button type="primary" size="small" @click="showAddMemberDialog = true">添加成员</el-button>
            </div>
          </template>
          <el-empty v-if="!members.length" description="暂无成员，请先添加标注员到项目中" :image-size="60" />
          <div v-else style="display: flex; flex-wrap: wrap; gap: 8px;">
            <el-tag v-for="m in members" :key="m.user_id" closable @close="removeMember(m.user_id)" size="large" style="padding: 6px 12px;">
              {{ m.display_name || m.username }}
              <span v-if="m.task_count > 0" style="color: #909399; margin-left: 4px; font-size: 11px;">({{ m.task_count }}题)</span>
            </el-tag>
          </div>
        </el-card>

        <!-- 添加成员弹窗 -->
        <el-dialog v-model="showAddMemberDialog" title="添加项目成员" width="450px">
          <el-select v-model="newMemberIds" multiple placeholder="选择要添加的标注员" style="width: 100%;" filterable>
            <el-option v-for="u in availableAnnotators" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
          </el-select>
          <template #footer>
            <el-button @click="showAddMemberDialog = false">取消</el-button>
            <el-button type="primary" @click="addMembers" :disabled="!newMemberIds.length">添加</el-button>
          </template>
        </el-dialog>

        <!-- Step 2: 分配任务（从成员中选） -->
        <el-card>
          <el-form label-position="top">
            <el-form-item label="标注模式">
              <el-radio-group v-model="assignMode" disabled>
                <el-radio-button value="single">单人标注</el-radio-button>
                <el-radio-button value="dual">双人盲标</el-radio-button>
              </el-radio-group>
              <p style="color: #999; font-size: 12px; margin-top: 4px;">
                {{ assignMode === 'dual' ? '每个视频分配2人独立标注，不一致时引入第三人' : '每个视频仅1人标注，直接出结果' }}
                <span style="color: #e6a23c;">（创建批次时已确定，不可修改）</span>
              </p>
            </el-form-item>

            <el-form-item label="从项目成员中选择" v-if="assignMode === 'single'">
              <el-select v-model="selectedAnnotators" multiple placeholder="选择要分配任务的成员" style="width: 100%;">
                <el-option v-for="m in members" :key="m.user_id" :label="m.display_name || m.username" :value="m.user_id" />
              </el-select>
              <p v-if="!members.length" style="color: #e6393e; font-size: 12px; margin-top: 4px;">请先在上方添加项目成员</p>
            </el-form-item>
          </el-form>

          <!-- 双人模式：一键自动分配 -->
          <div v-if="assignMode === 'dual'" style="margin-top: 16px;">
            <div style="background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
              <p style="font-size: 14px; font-weight: 600; color: #0369a1; margin-bottom: 8px;">自动负载均衡分配</p>
              <p style="font-size: 13px; color: #666; line-height: 1.6;">
                系统将为每个视频自动分配 A（主标）、B（副标）、C（仲裁）三个角色。<br>
                分配规则：优先将任务分给当前总任务数最少的成员，确保所有人工作量尽量均衡。<br>
                项目成员数 ≥ 3 时自动预分配仲裁人，&lt; 3 人时不分配。
              </p>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <el-tag type="info">待分配: {{ unassignedCount }} 个视频 × 项目成员 {{ members.length }} 人</el-tag>
              <el-button type="primary" size="large" @click="doAutoAssign" :loading="assigning" :disabled="unassignedCount === 0 || members.length < 2">
                一键分配
              </el-button>
            </div>
          </div>

          <!-- 单人模式：手动配额表 -->
          <div v-if="assignMode === 'single' && allocationTable.length" style="margin-top: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
              <span style="font-weight: 600; font-size: 14px;">分配方案（待分配: {{ unassignedCount }} 个视频）</span>
              <div style="display: flex; gap: 8px;">
                <el-button size="small" @click="distributeEvenly">均匀分配</el-button>
              </div>
            </div>

            <el-table :data="allocationTable" border size="small" show-summary :summary-method="getSummary">
              <el-table-column prop="name" label="标注员" width="120" />
              <el-table-column label="数量 (A)" width="150">
                <template #default="{ row }">
                  <el-input-number v-model="row.count" :min="0" :max="unassignedCount" size="small" style="width: 120px;" />
                </template>
              </el-table-column>
              <el-table-column label="占比" width="70">
                <template #default="{ row }">
                  {{ unassignedCount > 0 ? Math.round(row.count / unassignedCount * 100) : 0 }}%
                </template>
              </el-table-column>
              <el-table-column label="题目范围">
                <template #default="{ row, $index }">
                  <span style="color: #999; font-size: 12px;">{{ getRangeLabel($index) }}</span>
                </template>
              </el-table-column>
            </el-table>

            <div style="margin-top: 12px; display: flex; justify-content: space-between; align-items: center;">
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <el-tag v-if="allocationDiff === 0 && totalAllocated > 0" type="success">合计正确，等于待分配总数</el-tag>
                <el-tag v-else-if="allocationDiff > 0" type="danger">超出 {{ allocationDiff }} 题</el-tag>
                <el-tag v-else-if="totalAllocated > 0" type="warning">还差 {{ -allocationDiff }} 题未分配</el-tag>
              </div>
              <el-button type="primary" @click="doAssign" :loading="assigning" :disabled="!canAssign">
                确认执行
              </el-button>
            </div>
          </div>

          <!-- AI 分析说明 -->
          <el-alert v-if="assignResult" :title="assignResult" type="success" show-icon style="margin-top: 12px;" />
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
            <el-option label="比对完成" value="比对完成" />
            <el-option label="待第三人" value="待第三人" />
            <el-option label="待专家" value="待专家" />
            <el-option label="技术无效" value="技术无效" />
            <el-option label="已定案" value="已定案" />
          </el-select>
          <el-select v-model="filterAnnotator" placeholder="筛选标注员" clearable size="small" style="width: 140px;">
            <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.display_name || u.username" />
          </el-select>
          <el-button type="warning" size="small" @click="batchAssignThird" :disabled="!hasUnassignedThird">
            批量分配仲裁人
          </el-button>
        </div>
        <el-table :data="filteredProgress" stripe max-height="500">
          <el-table-column prop="video_id" label="视频" width="70" />
          <el-table-column prop="question_id" label="题目" width="70" />
          <el-table-column prop="prompt_summary" label="Prompt" min-width="120" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="annotator_a" label="A" width="70" />
          <el-table-column prop="annotator_b" label="B" width="70" />
          <el-table-column prop="annotator_third" label="C(仲裁)" width="80" />
          <el-table-column label="仲裁状态" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.arbitration_status" :type="arbitrationTagType(row.arbitration_status)" size="small">
                {{ arbitrationLabel(row.arbitration_status) }}
              </el-tag>
              <span v-else style="color:#ccc;">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="finalized" label="定案" width="50" />
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <el-button v-if="row.status !== '未分配'" size="small" type="primary" link @click="viewDetail(row)">详情</el-button>
              <el-button v-if="row.arbitration_status === 'unassigned'" size="small" type="warning" link @click="assignThirdSingle(row)">分配仲裁</el-button>
              <el-button v-if="row.annotator_a" size="small" type="danger" link @click="resetVideo(row)">重置</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 查看详情弹窗 -->
        <el-dialog v-model="showDetailDialog" :title="'标注对比 - ' + (detailData?.video_id || '')" width="900px" top="5vh">
          <div v-if="detailData" style="max-height: 70vh; overflow-y: auto;">
            <div style="margin-bottom: 12px;">
              <div style="font-size: 13px; color: #333; line-height: 1.6; white-space: pre-wrap; word-break: break-word; background: #f8fafc; padding: 12px; border-radius: 6px; border: 1px solid #eee;">
                <b>{{ detailData.question_id }}</b>: {{ detailData.prompt }}
              </div>
              <div v-if="detailData.video_url" style="margin-top: 8px;">
                <video controls preload="metadata" style="width: 100%; max-height: 300px; border-radius: 6px; background: #000;" :src="detailData.video_url"></video>
              </div>
              <div v-else style="margin-top: 4px; font-size: 12px; color: #999;">无视频URL</div>
            </div>
            <div style="display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap;">
              <el-tag v-for="(info, role) in detailData.roles" :key="role"
                :type="role === 'expert' ? 'danger' : role === 'third' ? 'warning' : role === 'A' ? 'primary' : 'success'"
                size="small">
                {{ role === 'third' ? 'C' : role }}={{ info.annotator }} ({{ info.status === 'submitted' ? '已提交' : '进行中' }})
              </el-tag>
            </div>
            <el-table :data="detailData.checkpoints" border size="small" stripe>
              <el-table-column prop="checkpoint_id" label="检查点" width="110" />
              <el-table-column prop="text" label="内容" min-width="200" show-overflow-tooltip />
              <el-table-column label="A" width="55">
                <template #default="{ row }">
                  <span :style="scoreStyle(row.A?.score)">{{ row.A?.score || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="B" width="55">
                <template #default="{ row }">
                  <span :style="scoreStyle(row.B?.score)">{{ row.B?.score || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="C" width="55">
                <template #default="{ row }">
                  <span :style="scoreStyle(row.third?.score)">{{ row.third?.score || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="专家" width="55">
                <template #default="{ row }">
                  <span :style="scoreStyle(row.expert?.score)">{{ row.expert?.score || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="定案" width="55">
                <template #default="{ row }">
                  <span style="font-weight: 600;">{{ row.final_score || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="方式" width="70">
                <template #default="{ row }">
                  <span style="font-size: 11px; color: #999;">{{ methodLabel(row.final_method) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="一致" width="50">
                <template #default="{ row }">
                  <span v-if="row.A && row.B && row.A.score === row.B.score" style="color: #67c23a;">✓</span>
                  <span v-else-if="row.A && row.B" style="color: #e6393e;">✗</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-dialog>

        <!-- 分配仲裁人弹窗 -->
        <el-dialog v-model="showThirdDialog" title="分配仲裁人" width="400px">
          <p style="margin-bottom: 12px; color: #666; font-size: 13px;">为视频 {{ thirdDialogVideo?.video_id }} 选择仲裁标注员（已排除A/B）</p>
          <el-select v-model="thirdDialogAnnotatorId" placeholder="选择标注员" style="width: 100%;">
            <el-option v-for="u in thirdCandidates" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
          </el-select>
          <template #footer>
            <el-button @click="showThirdDialog = false">取消</el-button>
            <el-button type="primary" @click="confirmAssignThird" :disabled="!thirdDialogAnnotatorId">确认</el-button>
          </template>
        </el-dialog>
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
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api.js'

const props = defineProps(['batch', 'annotators'])
const emit = defineEmits(['refresh'])

const activeTab = ref('assign')
const selectedAnnotators = ref([])
const assignMode = ref('single')
const assigning = ref(false)
const assignResult = ref('')
const progress = ref([])
const scores = ref([])
const filterStatus = ref('')
const filterAnnotator = ref('')
const assignedAnnotators = ref([])
const unassignedCount = ref(0)

const roleStats = computed(() => {
  const rs = props.batch?.role_stats
  if (!rs) return { A: {total:0,submitted:0}, B: {total:0,submitted:0}, C: {total:0,submitted:0}, expert: {total:0,submitted:0} }
  return rs
})

// Members management
const members = ref([])
const showAddMemberDialog = ref(false)
const newMemberIds = ref([])

const availableAnnotators = computed(() => {
  const memberIds = new Set(members.value.map(m => m.user_id))
  return (props.annotators || []).filter(u => !memberIds.has(u.id))
})

// AI dialog
const showAiDialog = ref(false)
const aiInstruction = ref('')
const aiLoading = ref(false)
const aiReasoning = ref('')

// Allocation table
const allocationTable = reactive([])

const totalAllocated = computed(() => allocationTable.reduce((sum, row) => sum + (row.count || 0), 0))
const allocationDiff = computed(() => totalAllocated.value - unassignedCount.value)
const activeAnnotatorCount = computed(() => allocationTable.filter(r => r.count > 0).length)
const canAssign = computed(() => {
  if (allocationDiff.value !== 0 || totalAllocated.value === 0) return false
  // 双人模式下如果只有1人有分配，后端会校验是否所有待分配视频都已有A（只需补B）
  // 前端不再硬性拦截，交给后端判断
  return true
})

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
    loadUnassignedCount()
    loadMembers()
  }
}, { immediate: true })

watch(selectedAnnotators, (ids) => {
  // Sync allocation table with selected annotators
  const existing = new Map(allocationTable.map(r => [r.id, r.count]))
  allocationTable.length = 0
  for (const id of ids) {
    const ann = props.annotators.find(a => a.id === id)
    allocationTable.push({
      id,
      name: ann ? (ann.display_name || ann.username) : String(id),
      count: existing.get(id) || 0,
    })
  }
})

async function loadMembers() {
  if (!props.batch) return
  try {
    const { data } = await api.get(`/batches/${props.batch.id}/members`)
    members.value = data
  } catch {}
}

async function addMembers() {
  if (!props.batch || !newMemberIds.value.length) return
  try {
    await api.post(`/batches/${props.batch.id}/members`, { user_ids: newMemberIds.value })
    showAddMemberDialog.value = false
    newMemberIds.value = []
    await loadMembers()
    ElMessage.success('成员已添加')
  } catch (e) {
    ElMessage.error('添加失败')
  }
}

async function removeMember(userId) {
  if (!props.batch) return
  try {
    await api.delete(`/batches/${props.batch.id}/members/${userId}`)
    await loadMembers()
  } catch {}
}

async function loadUnassignedCount() {
  if (!props.batch) return
  try {
    const { data } = await api.get(`/batches/${props.batch.id}`)
    unassignedCount.value = data.unassigned_videos || 0
  } catch {}
}

function distributeEvenly() {
  const n = allocationTable.length
  if (n === 0) return
  const base = Math.floor(unassignedCount.value / n)
  const remainder = unassignedCount.value % n
  for (let i = 0; i < n; i++) {
    allocationTable[i].count = base + (i < remainder ? 1 : 0)
  }
}

async function aiAssist() {
  if (!aiInstruction.value.trim()) {
    ElMessage.warning('请输入分配指令')
    return
  }
  aiLoading.value = true
  try {
    const { data } = await api.post(`/batches/${props.batch.id}/ai-suggest`, {
      annotator_ids: selectedAnnotators.value,
      annotation_mode: assignMode.value,
      instruction: aiInstruction.value,
    })
    // Fill allocation table with AI results
    if (data.plan_full) {
      const countMap = {}
      for (const p of data.plan_full) {
        countMap[p.annotator_a_id] = (countMap[p.annotator_a_id] || 0) + 1
      }
      for (const row of allocationTable) {
        row.count = countMap[row.id] || 0
      }
    }
    aiReasoning.value = data.reasoning || ''
    showAiDialog.value = false
    ElMessage.success('AI 方案已填入，可继续调整')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'AI 生成失败')
  } finally { aiLoading.value = false }
}

async function doAutoAssign() {
  assigning.value = true
  assignResult.value = ''
  try {
    const { data } = await api.post(`/batches/${props.batch.id}/assign-by-allocation`, {
      allocations: [],
      annotation_mode: 'dual',
    })
    assignResult.value = `自动分配完成: 创建 ${data.created} 个任务, 覆盖 ${data.videos_assigned} 个视频`
    emit('refresh')
    loadProgress()
    loadAssignedAnnotators()
    loadUnassignedCount()
    loadMembers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '分配失败')
  } finally { assigning.value = false }
}

async function doAssign() {
  assigning.value = true
  assignResult.value = ''
  try {
    const allocations = allocationTable
      .filter(r => r.count > 0)
      .map(r => ({ annotator_id: r.id, count: r.count }))
    const { data } = await api.post(`/batches/${props.batch.id}/assign-by-allocation`, {
      allocations,
      annotation_mode: assignMode.value,
    })
    assignResult.value = `分配完成: 创建 ${data.created} 个任务, 覆盖 ${data.videos_assigned} 个视频`
    emit('refresh')
    loadProgress()
    loadAssignedAnnotators()
    loadUnassignedCount()
    // Reset counts
    for (const row of allocationTable) row.count = 0
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '分配失败')
  } finally { assigning.value = false }
}

function getRangeLabel(index) {
  let start = 1
  for (let i = 0; i < index; i++) {
    start += allocationTable[i].count || 0
  }
  const count = allocationTable[index].count || 0
  if (count === 0) return '-'
  return `第 ${start} ~ ${start + count - 1} 题`
}

function getBCount(annotatorId) {
  if (assignMode.value !== 'dual') return 0
  const activeRows = allocationTable.filter(r => r.count > 0)
  if (activeRows.length < 2) return 0
  // Simulate B-role rotation: for each A-assigned video, B is picked from others
  let bCount = 0
  let videoIdx = 0
  for (const row of allocationTable) {
    if (row.count <= 0) continue
    const candidates = activeRows.filter(r => r.id !== row.id)
    for (let i = 0; i < row.count; i++) {
      const bRow = candidates[videoIdx % candidates.length]
      if (bRow.id === annotatorId) bCount++
      videoIdx++
    }
  }
  return bCount
}

function getSummary({ data }) {
  if (assignMode.value === 'dual') {
    const totalB = allocationTable.reduce((sum, r) => sum + getBCount(r.id), 0)
    return ['合计', totalAllocated.value, totalB, totalAllocated.value + totalB, '', `/ ${unassignedCount.value}`]
  }
  return ['合计', totalAllocated.value, '', `/ ${unassignedCount.value}`]
}

function statusType(s) {
  const map = { '未分配': 'info', '已分配待标注': '', '已定案': 'success', '待第三人': 'warning', '待专家': 'danger', '技术无效': 'danger', '比对完成': '' }
  return map[s] || ''
}

function arbitrationTagType(s) {
  const map = { unassigned: 'danger', waiting: 'info', pending: 'warning', submitted: '', resolved: 'success' }
  return map[s] || 'info'
}

function arbitrationLabel(s) {
  const map = { unassigned: '未分配', waiting: '待激活', pending: '待标注', submitted: '已提交', resolved: '已裁决' }
  return map[s] || s
}

const hasUnassignedThird = computed(() => progress.value.some(p => p.arbitration_status === 'unassigned'))

// Third-person assignment dialog
const showThirdDialog = ref(false)
const thirdDialogVideo = ref(null)
const thirdDialogAnnotatorId = ref(null)

const thirdCandidates = computed(() => {
  if (!thirdDialogVideo.value || !props.annotators) return []
  const excludeIds = new Set()
  if (thirdDialogVideo.value.annotator_a_id) excludeIds.add(thirdDialogVideo.value.annotator_a_id)
  if (thirdDialogVideo.value.annotator_b_id) excludeIds.add(thirdDialogVideo.value.annotator_b_id)
  return props.annotators.filter(u => !excludeIds.has(u.id))
})

function assignThirdSingle(row) {
  thirdDialogVideo.value = row
  thirdDialogAnnotatorId.value = null
  showThirdDialog.value = true
}

async function confirmAssignThird() {
  if (!thirdDialogVideo.value || !thirdDialogAnnotatorId.value) return
  try {
    await api.post('/arbitration/assign-third-single', {
      video_db_id: thirdDialogVideo.value.video_db_id,
      annotator_id: thirdDialogAnnotatorId.value,
    })
    ElMessage.success('仲裁人已分配')
    showThirdDialog.value = false
    loadProgress()
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '分配失败')
  }
}

async function batchAssignThird() {
  if (!props.batch) return
  try {
    await ElMessageBox.confirm('将为所有有分歧但未分配仲裁人的视频自动分配第三人（负载均衡）', '批量分配仲裁人', { type: 'warning' })
    const { data } = await api.post(`/arbitration/assign-third-batch/${props.batch.id}`)
    ElMessage.success(`已分配 ${data.count} 个仲裁任务`)
    loadProgress()
  } catch {}
}

// Detail view
const showDetailDialog = ref(false)
const detailData = ref(null)

async function viewDetail(row) {
  try {
    const { data } = await api.get(`/annotations/compare-view/${row.video_db_id}`)
    detailData.value = data
    showDetailDialog.value = true
  } catch (e) {
    ElMessage.error('加载详情失败')
  }
}

function scoreStyle(score) {
  if (score === 'C') return { color: '#67c23a', fontWeight: 600 }
  if (score === 'R') return { color: '#e6a23c', fontWeight: 600 }
  if (score === 'N') return { color: '#e6393e', fontWeight: 600 }
  return { color: '#ccc' }
}

function methodLabel(method) {
  const map = { consensus: '一致', majority: '多数票', expert: '专家', pending_expert: '待专家', single: '单人' }
  return map[method] || method || ''
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

async function loadAssignedAnnotators() {
  if (!props.batch) return
  try {
    const { data } = await api.get('/assignments/progress', { params: { batch_id: props.batch.id, page_size: 9999 } })
    const countMap = {}
    for (const item of data.items) {
      if (item.annotator_a) countMap[item.annotator_a] = (countMap[item.annotator_a] || 0) + 1
      if (item.annotator_b) countMap[item.annotator_b] = (countMap[item.annotator_b] || 0) + 1
      if (item.annotator_third) countMap[item.annotator_third] = (countMap[item.annotator_third] || 0) + 1
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
    loadUnassignedCount()
    emit('refresh')
  } catch {}
}

function doExport() {
  window.open(`/api/export/results?batch_id=${props.batch.id}`, '_blank')
}

async function resetVideo(row) {
  try {
    await ElMessageBox.confirm(`重置视频「${row.video_id}」的标注？`, '重置', { type: 'warning' })
    await api.post('/assignments/reset-single', { video_id: row.video_id })
    ElMessage.success('已重置')
    loadProgress()
    loadUnassignedCount()
  } catch {}
}
</script>
