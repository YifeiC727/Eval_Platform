<template>
  <div v-loading="loading">
    <el-page-header @back="$router.push('/tasks')" :icon="null">
      <template #title>
        <span>返回任务列表</span>
      </template>
      <template #content>
        <span style="font-size: 16px; font-weight: 600;">
          {{ detail?.question?.question_id }} — {{ detail?.assignment?.role === 'third' ? '仲裁任务' : '标注任务' }}
          <el-tag :type="detail?.assignment?.role === 'third' ? 'warning' : 'primary'" size="small" style="margin-left: 8px;">
            角色: {{ detail?.assignment?.role }}
          </el-tag>
        </span>
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
                  <span style="font-weight: 500;">{{ cp.text }}</span>
                </div>
                <div style="color: #666; font-size: 13px; margin-bottom: 12px;">
                  <strong>最低成功线：</strong>{{ cp.min_success_line }}
                </div>
                <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                  <el-radio-group v-model="annotations[cp.id].score" size="large">
                    <el-radio-button value="C">C</el-radio-button>
                    <el-radio-button value="R">R</el-radio-button>
                    <el-radio-button value="N">N</el-radio-button>
                  </el-radio-group>

                  <el-select v-if="annotations[cp.id].score && annotations[cp.id].score !== 'C'"
                    v-model="annotations[cp.id].fail_code" placeholder="失败码" size="small" style="width: 200px;">
                    <el-option v-for="fc in failCodes" :key="fc.code" :label="`${fc.code} ${fc.name}`" :value="fc.code" />
                  </el-select>

                  <el-input v-model="annotations[cp.id].evidence_ts" placeholder="时间戳" size="small" style="width: 100px;" />
                </div>
                <el-input v-model="annotations[cp.id].note" placeholder="备注（可选）" size="small" style="margin-top: 8px;" />
              </div>
            </div>
          </div>
        </el-card>

        <div style="margin-top: 16px; display: flex; gap: 12px; justify-content: space-between;">
          <div style="display: flex; gap: 8px;">
            <el-button type="danger" plain @click="reportIssue">技术无效上报</el-button>
            <el-button plain @click="skipTask">跳过此题</el-button>
          </div>
          <div style="display: flex; gap: 8px;">
            <el-button @click="saveAnnotations" :loading="saving">暂存</el-button>
            <el-button type="primary" @click="submitAndLock" :loading="submitting"
              :disabled="!canSubmit || detail.assignment.status === 'submitted'">
              提交锁定
            </el-button>
          </div>
        </div>
        <el-alert v-if="detail.assignment.status === 'submitted'" type="success" title="已提交锁定，不可修改" show-icon style="margin-top: 12px;" />
        <el-alert v-if="detail.assignment.status === 'issue_reported'" type="warning" title="已上报技术无效，等待管理员处理" show-icon style="margin-top: 12px;" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
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

const failCodes = [
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

const activeCheckpoints = computed(() => detail.value?.checkpoints?.filter(cp => cp.needs_annotation) || [])
const annotatedCount = computed(() => activeCheckpoints.value.filter(cp => annotations[cp.id]?.score).length)
const canSubmit = computed(() => {
  return activeCheckpoints.value.every(cp => {
    const ann = annotations[cp.id]
    if (!ann?.score) return false
    if (ann.score !== 'C' && !ann.fail_code) return false
    return true
  })
})

onMounted(async () => {
  const id = props.assignmentId || route.params.assignmentId
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
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

async function submitAndLock() {
  try {
    await ElMessageBox.confirm('提交后将锁定，不可修改。确认提交？', '确认提交', { type: 'warning' })
  } catch { return }

  submitting.value = true
  try {
    const { data } = await api.post('/annotations/submit-and-lock', buildPayload())
    ElMessage.success('提交成功，已锁定')
    detail.value.assignment.status = 'submitted'
    if (data.comparison) {
      ElMessage.info(`比对完成: ${data.comparison.consensus} 一致, ${data.comparison.need_third} 需仲裁`)
    }
  } catch (e) {
    ElMessage.error('提交失败: ' + (e.response?.data?.detail || e.message))
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

function skipTask() {
  router.push('/tasks')
  ElMessage.info('已跳过，可稍后在任务列表中继续')
}
</script>
