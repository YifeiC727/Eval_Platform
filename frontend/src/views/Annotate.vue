<template>
  <div v-loading="loading">
    <el-page-header @back="$router.push('/tasks')" :icon="null">
      <template #title>
        <span>返回任务列表</span>
      </template>
      <template #content>
        <div style="display: flex; align-items: center; gap: 16px;">
          <span style="font-size: 16px; font-weight: 600;">
            {{ detail?.question?.question_id }} — {{ detail?.assignment?.role === 'third' ? '仲裁任务' : '标注任务' }}
            <el-tag :type="detail?.assignment?.role === 'third' ? 'warning' : 'primary'" size="small" style="margin-left: 8px;">
              角色: {{ detail?.assignment?.role }}
            </el-tag>
          </span>
          <div style="display: flex; gap: 8px;">
            <el-button size="small" :disabled="!hasPrev" @click="goTask('prev')">上一题</el-button>
            <span style="font-size: 13px; color: #999;">{{ currentTaskIndex + 1 }} / {{ taskIds.length }}</span>
            <el-button size="small" :disabled="!hasNext" @click="goTask('next')">下一题</el-button>
          </div>
        </div>
      </template>
    </el-page-header>

    <div v-if="detail" style="margin-top: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <!-- Left: Video + Prompt -->
      <div>
        <el-card>
          <template #header><span style="font-weight: 600;">视频</span></template>
          <div v-if="detail.video.oss_url" style="background: #000; border-radius: 8px; overflow: hidden;">
            <video ref="videoEl" :src="detail.video.oss_url" controls style="width: 100%; max-height: 400px;" />
          </div>
          <el-empty v-else description="暂无视频URL" />
        </el-card>
        <el-card style="margin-top: 16px;">
          <template #header><span style="font-weight: 600;">Prompt</span></template>
          <p style="line-height: 1.8; white-space: pre-wrap;">{{ detail.question.prompt }}</p>
        </el-card>
      </div>

      <!-- Right: Checkpoints -->
      <div>
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600;">
                检查点 ({{ annotatedCount }}/{{ activeCheckpoints.length }})
              </span>
              <span v-if="detail.assignment.role === 'third'" style="color: #e6a23c; font-size: 13px;">
                仅需判断 {{ activeCheckpoints.length }}/{{ detail.checkpoints.length }} 个分歧检查点
              </span>
            </div>
          </template>
          <div style="padding: 10px 16px; background: #f0f7ff; border-bottom: 1px solid #e0e0e0; font-size: 12px; color: #555;">
            <strong>C 达标</strong> = 达到最低成功线 &nbsp;|&nbsp;
            <strong>R 部分</strong> = 有尝试但未达标 &nbsp;|&nbsp;
            <strong>N 缺失</strong> = 完全缺失或无关 &nbsp;|&nbsp;
            <strong>不适用</strong> = 该检查点与视频内容不匹配，不应用于此题（不计入得分）
          </div>
          <div style="max-height: 600px; overflow-y: auto;">
            <div v-for="(cp, idx) in detail.checkpoints" :key="cp.id"
              :style="{ opacity: cp.is_finalized ? 0.4 : 1, padding: '16px', borderBottom: '1px solid #eee', background: currentIdx === idx ? '#f0f9ff' : '' }"
              @click="currentIdx = idx">

              <div v-if="cp.is_finalized" style="color: #999;">
                <el-tag type="info" size="small">已定案</el-tag>
                {{ cp.text }}
              </div>

              <div v-else>
                <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 8px;">
                  <el-tag size="small">CP{{ String(cp.seq).padStart(2, '0') }}</el-tag>
                  <el-tag v-if="taskType === 't2av'" size="small" :type="cp.ability_id?.startsWith('AV') ? 'danger' : cp.ability_id?.startsWith('A') ? 'warning' : 'success'" effect="plain">
                    {{ cp.ability_id?.startsWith('AV') ? '音画同步' : cp.ability_id?.startsWith('A') ? '声音' : '视频' }}
                  </el-tag>
                  <span style="font-weight: 500;">{{ cp.text }}</span>
                </div>
                <div style="color: #666; font-size: 13px; margin-bottom: 12px;">
                  <strong>最低成功线：</strong>{{ cp.min_success_line }}
                </div>
                <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                  <el-radio-group v-model="annotations[cp.id].score" size="large">
                    <el-radio-button value="C">C 达标</el-radio-button>
                    <el-radio-button value="R">R 部分</el-radio-button>
                    <el-radio-button value="N">N 缺失</el-radio-button>
                    <el-radio-button value="NA">不适用</el-radio-button>
                  </el-radio-group>
                </div>
                <!-- 失败码选择 (score != C 且 fail_code_mode != disabled) -->
                <div v-if="annotations[cp.id].score && annotations[cp.id].score !== 'C' && annotations[cp.id].score !== 'NA' && failCodeMode !== 'disabled'"
                  style="margin-top: 8px;">
                  <el-select v-model="annotations[cp.id].fail_code"
                    :placeholder="failCodeMode === 'required' ? '请选择失败码（必填）' : '选择失败码（可选）'"
                    size="small" style="width: 280px;" clearable>
                    <el-option v-for="fc in getFailCodes(annotations[cp.id].score, cp.ability_id)" :key="fc.code" :label="fc.code + ' ' + fc.name" :value="fc.code" />
                  </el-select>
                </div>
                <el-input v-model="annotations[cp.id].note" placeholder="备注（可选，如对检查点拆解的建议等）" size="small" style="margin-top: 8px;" />
              </div>
            </div>
          </div>
        </el-card>

        <div style="margin-top: 16px; display: flex; gap: 12px; justify-content: space-between;">
          <div style="display: flex; gap: 8px;">
            <el-button v-if="detail.assignment.role === 'expert'" type="danger" @click="dropAsExpert">
              确认技术无效(废弃此题)
            </el-button>
            <el-button v-else type="danger" plain @click="reportIssue">技术无效</el-button>
          </div>
          <div style="display: flex; gap: 8px;">
            <el-button @click="saveAnnotations" :loading="saving">暂存</el-button>
            <el-button type="success" @click="completeAndNext" :loading="submitting"
              :disabled="!canSubmit || detail.assignment.status === 'submitted'">
              完成此题 →
            </el-button>
          </div>
        </div>
        <el-alert v-if="detail.assignment.status === 'submitted'" type="success" title="已全部提交锁定，不可修改" show-icon style="margin-top: 12px;" />
        <el-alert v-if="detail.assignment.status === 'issue_reported'" type="warning" title="已上报技术无效" show-icon style="margin-top: 12px;" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api.js'

const props = defineProps(['assignmentId'])
const route = useRoute()
const router = useRouter()

const loading = ref(true)
const saving = ref(false)
const submitting = ref(false)
const detail = ref(null)
const annotations = reactive({})
const currentIdx = ref(0)
const videoEl = ref(null)
const taskIds = ref([])
const currentTaskIndex = computed(() => {
  const id = parseInt(props.assignmentId || route.params.assignmentId)
  const idx = taskIds.value.indexOf(id)
  return idx >= 0 ? idx : 0
})
const hasPrev = computed(() => currentTaskIndex.value > 0)
const hasNext = computed(() => currentTaskIndex.value < taskIds.value.length - 1)

const FAIL_CODES_T2V = [
  { code: 'F01', name: '要求遗漏' },
  { code: 'F02', name: '语义/指令错误' },
  { code: 'F03', name: '数量/绑定错误' },
  { code: 'F04', name: '结构/解剖错误' },
  { code: 'F05', name: '动作动态错误' },
  { code: 'F06', name: '交互/接触错误' },
  { code: 'F07', name: '物理/因果错误' },
  { code: 'F08', name: '时序错误' },
  { code: 'F09', name: '一致性错误' },
  { code: 'F10', name: '镜头/构图错误' },
  { code: 'F11', name: '视觉呈现错误' },
]

const FAIL_CODES_T2AV_R = [
  { code: 'RF01', name: '内容/类型错误' },
  { code: 'RF02', name: '数量、身份或角色绑定错误' },
  { code: 'RF03', name: '时序、顺序或同步错误' },
  { code: 'RF04', name: '音质伪影' },
  { code: 'RF05', name: '连续性错误' },
  { code: 'RF06', name: '混音层级错误' },
  { code: 'RF07', name: '空间声错误' },
]

const FAIL_CODES_T2AV_N = [
  { code: 'N1', name: '目标声音缺失' },
  { code: 'N2', name: '完全错误或无关' },
  { code: 'N3', name: '严重崩坏不可辨' },
]

const taskType = computed(() => detail.value?.batch?.task_type || 't2v')

function getFailCodes(score, abilityId) {
  if (taskType.value === 't2av') {
    // 视频层检查点(C开头)用 F01-F11，声音/同步层(A/AV开头)用 RF/N
    const isAudioOrSync = abilityId && (abilityId.startsWith('AV') || abilityId.startsWith('A'))
    if (isAudioOrSync) {
      return score === 'R' ? FAIL_CODES_T2AV_R : FAIL_CODES_T2AV_N
    }
    return FAIL_CODES_T2V
  }
  return FAIL_CODES_T2V
}

const activeCheckpoints = computed(() => detail.value?.checkpoints?.filter(cp => cp.needs_annotation) || [])
const annotatedCount = computed(() => activeCheckpoints.value.filter(cp => annotations[cp.id]?.score).length)
const failCodeMode = computed(() => detail.value?.batch?.fail_code_mode || 'optional')
const canSubmit = computed(() => {
  return activeCheckpoints.value.every(cp => {
    const ann = annotations[cp.id]
    if (!ann?.score) return false
    // If fail_code_mode is required and score is R/N, must have fail_code
    if (failCodeMode.value === 'required' && (ann.score === 'R' || ann.score === 'N') && !ann.fail_code) return false
    return true
  })
})

onMounted(async () => {
  const id = props.assignmentId || route.params.assignmentId
  // Load all task IDs for navigation
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
  if (user.id) {
    try {
      const { data: allTasks } = await api.get('/assignments/my', { params: { user_id: user.id } })
      taskIds.value = allTasks.filter(t => t.status !== 'submitted').map(t => t.id)
      if (!taskIds.value.includes(parseInt(id))) {
        taskIds.value = [parseInt(id), ...taskIds.value]
      }
    } catch {}
  }
  await loadAssignment(id)
})

function goTask(direction) {
  const idx = currentTaskIndex.value
  const nextIdx = direction === 'next' ? idx + 1 : idx - 1
  if (nextIdx >= 0 && nextIdx < taskIds.value.length) {
    router.push(`/annotate/${taskIds.value[nextIdx]}`)
  }
}

async function loadAssignment(id) {
  loading.value = true
  detail.value = null
  Object.keys(annotations).forEach(k => delete annotations[k])
  try {
    const { data } = await api.get(`/assignments/${id}`)
    detail.value = data
    for (const cp of data.checkpoints) {
      annotations[cp.id] = { score: '', fail_code: null, evidence_ts: '', note: '' }
    }
    const { data: existing } = await api.get(`/annotations/assignment/${id}`)
    for (const ann of existing) {
      if (annotations[ann.checkpoint_id]) {
        annotations[ann.checkpoint_id].score = ann.score
        annotations[ann.checkpoint_id].fail_code = ann.fail_code
        annotations[ann.checkpoint_id].evidence_ts = ann.evidence_ts || ''
        annotations[ann.checkpoint_id].note = ann.note || ''
      }
    }
  } catch (e) {
    ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

watch(() => route.params.assignmentId, (newId) => {
  if (newId) loadAssignment(newId)
})

function buildPayload() {
  const id = props.assignmentId || route.params.assignmentId
  const items = activeCheckpoints.value
    .filter(cp => annotations[cp.id]?.score)
    .map(cp => ({
      checkpoint_id: cp.id,
      score: annotations[cp.id].score,
      fail_code: annotations[cp.id].score === 'C' ? null : annotations[cp.id].fail_code,
      evidence_ts: annotations[cp.id].evidence_ts || null,
      note: annotations[cp.id].note || null,
    }))
  return { assignment_id: parseInt(id), annotations: items }
}

async function saveAnnotations() {
  saving.value = true
  try {
    await api.post('/annotations/submit', buildPayload())
    ElMessage.success('已暂存')
  } catch (e) {
    const detail = e.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail) || e.message
    ElMessage.error('保存失败: ' + msg)
  } finally {
    saving.value = false
  }
}

async function completeAndNext() {
  submitting.value = true
  try {
    await api.post('/annotations/submit', buildPayload())
    // Mark as completed (in_progress means annotations saved)
    await api.post('/annotations/complete', { assignment_id: parseInt(props.assignmentId || route.params.assignmentId) })
    ElMessage.success('已完成此题')
    // Go to next task
    if (hasNext.value) {
      goTask('next')
    } else {
      ElMessage.info('所有任务已完成，返回任务列表')
      router.push('/tasks')
    }
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    submitting.value = false
  }
}

async function reportIssue() {
  try {
    const { value: description } = await ElMessageBox.prompt(
      '请描述问题（如：视频黑屏、无法播放、文件损坏等）',
      '上报技术无效',
      { inputPlaceholder: '问题描述', confirmButtonText: '上报', cancelButtonText: '取消' }
    )
    const id = props.assignmentId || route.params.assignmentId
    await api.post('/issues/report', {
      assignment_id: parseInt(id),
      issue_type: '技术无效',
      description: description || '',
    })
    ElMessage.success('已上报，等待管理员处理')
    detail.value.assignment.status = 'issue_reported'
  } catch {}
}

async function dropAsExpert() {
  try {
    await ElMessageBox.confirm(
      '确认此视频存在技术问题需要废弃？废弃后该题不计入任何统计。',
      '确认技术无效',
      { type: 'error', confirmButtonText: '确认废弃', cancelButtonText: '取消' }
    )
    const videoId = detail.value.video.id
    await api.post(`/issues/drop/${videoId}`)
    ElMessage.success('已废弃，该题不计入统计')
    router.push('/admin')
  } catch {}
}

function skipTask() {
  router.push('/tasks')
  ElMessage.info('已跳过，可稍后在任务列表中继续')
}
</script>
