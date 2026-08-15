<template>
  <div v-loading="loading">
    <el-page-header @back="$router.push('/tasks')" :icon="null">
      <template #title>
        <span>返回任务列表</span>
      </template>
      <template #content>
        <div style="display: flex; align-items: center; gap: 16px;">
          <span style="font-size: 16px; font-weight: 600;">
            {{ detail?.question?.question_id }} — {{ detail?.assignment?.role === 'third' ? '仲裁任务' : detail?.assignment?.role === 'expert' ? '专家裁决' : '标注任务' }}
            <el-tag :type="detail?.assignment?.role === 'third' ? 'warning' : detail?.assignment?.role === 'expert' ? 'danger' : 'primary'" size="small" style="margin-left: 8px;">
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

    <!-- Batch context banner -->
    <div v-if="detail" style="margin-top: 12px; padding: 10px 20px; background: linear-gradient(135deg, #409eff 0%, #337ecc 100%); border-radius: 8px; display: flex; align-items: center; justify-content: space-between; color: #fff;">
      <div style="display: flex; align-items: center; gap: 10px;">
        <span style="font-weight: 700; font-size: 14px;">{{ batchName }}</span>
        <span style="background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 4px; font-size: 12px;">{{ evalMode === 'pe' ? 'PE配对评测' : '基础评测' }}</span>
        <span style="background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 4px; font-size: 12px;">{{ taskType === 't2av' ? 'T2AV' : 'T2V' }}</span>
        <span v-if="failCodeMode === 'required'" style="background: rgba(255,0,0,0.3); padding: 2px 8px; border-radius: 4px; font-size: 12px;">⚠ 失败码必选</span>
      </div>
      <div style="font-size: 13px; font-weight: 600;">
        剩余 {{ taskIds.length - currentTaskIndex - 1 }} 题
      </div>
    </div>

    <div v-if="detail" style="margin-top: 12px;">
      <!-- ===== PE MODE ===== -->
      <div v-if="evalMode === 'pe'" style="display: flex; flex-direction: column; height: calc(100vh - 140px);">
        <!-- Sticky top: Video + Prompt (compact) -->
        <div style="flex-shrink: 0; border-bottom: 2px solid #e0e0e0; padding-bottom: 12px; margin-bottom: 12px;">
          <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
            <!-- Left Video -->
            <div>
              <div style="text-align: center; font-size: 12px; font-weight: 600; margin-bottom: 4px; color: #409eff;">
                {{ isRandomized ? '左视频' : 'A 直出视频' }}
              </div>
              <div v-if="leftVideoUrl" style="background: #000; border-radius: 6px; overflow: hidden;">
                <video :src="leftVideoUrl" controls style="width: 100%; max-height: 200px;" />
              </div>
              <div v-else style="height: 120px; background: #f5f5f5; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #999; font-size: 12px;">无视频</div>
            </div>
            <!-- Right Video -->
            <div>
              <div style="text-align: center; font-size: 12px; font-weight: 600; margin-bottom: 4px; color: #67c23a;">
                {{ isRandomized ? '右视频' : 'B PE视频' }}
              </div>
              <div v-if="rightVideoUrl" style="background: #000; border-radius: 6px; overflow: hidden;">
                <video :src="rightVideoUrl" controls style="width: 100%; max-height: 200px;" />
              </div>
              <div v-else style="height: 120px; background: #f5f5f5; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #999; font-size: 12px;">无视频</div>
            </div>
            <!-- Prompt (scrollbar always visible) -->
            <div class="prompt-scroll" style="max-height: 220px; background: #f8fafc; border-radius: 6px; padding: 10px; border: 1px solid #eee; overflow-y: scroll;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 11px; color: #999; font-weight: 600;">PROMPT ↕</span>
                <el-button size="small" :type="showTranslation ? 'primary' : 'default'" @click="toggleTranslation" :loading="translating" round style="font-size: 11px; padding: 2px 10px; height: 22px;">
                  {{ showTranslation ? '原文' : '中文' }}
                </el-button>
              </div>
              <p style="line-height: 1.6; font-size: 13px; margin: 0; white-space: pre-wrap; word-break: break-word;">{{ showTranslation && translatedPrompt ? translatedPrompt : detail.question.prompt }}</p>
            </div>
          </div>
        </div>

        <!-- Scrollable: Checkpoints + GSB -->
        <div style="flex: 1; overflow-y: auto;">
          <!-- Dual Scoring per checkpoint -->
          <div style="background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
              <span style="font-weight: 600; font-size: 15px; color: #303133;">检查点评分</span>
              <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 12px; color: #999;">C=达标 | R=部分 | N=缺失 | NA=不适用</span>
                <el-tag type="primary" size="small">{{ peAnnotatedCount }}/{{ activeCheckpoints.length }}</el-tag>
              </div>
            </div>
            <div v-for="(cp, idx) in activeCheckpoints" :key="cp.id"
              style="padding: 12px 16px; border-radius: 8px; margin-bottom: 8px;"
              :style="{ background: (peAnnotations[cp.id]?.left && peAnnotations[cp.id]?.right) ? '#f6ffed' : '#fafafa', border: '1px solid ' + ((peAnnotations[cp.id]?.left && peAnnotations[cp.id]?.right) ? '#b7eb8f' : '#eee') }">
              <div style="font-size: 13px; margin-bottom: 10px;">
                <span style="display: inline-block; background: #409eff; color: #fff; padding: 1px 6px; border-radius: 3px; font-size: 11px; margin-right: 8px;">{{ idx + 1 }}</span>
                <span style="font-weight: 500;">{{ cp.text }}</span>
              </div>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 4px;">
                <div style="padding: 10px 14px; background: #f0f7ff; border-radius: 8px;">
                  <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 13px; color: #409eff; font-weight: 700;">A</span>
                    <el-radio-group v-model="peAnnotations[cp.id].left">
                      <el-radio-button value="C" style="margin-right: 4px;">C 达标</el-radio-button>
                      <el-radio-button value="R" style="margin-right: 4px;">R 部分</el-radio-button>
                      <el-radio-button value="N" style="margin-right: 4px;">N 缺失</el-radio-button>
                      <el-radio-button value="NA">不适用</el-radio-button>
                    </el-radio-group>
                  </div>
                  <div v-if="peAnnotations[cp.id].left && peAnnotations[cp.id].left !== 'C' && peAnnotations[cp.id].left !== 'NA' && failCodeMode !== 'disabled'" style="margin-top: 6px;">
                    <el-select v-model="peAnnotations[cp.id].left_fc" :placeholder="failCodeMode === 'required' ? '失败码（必填）' : '失败码（可选）'" size="small" style="width: 100%;" clearable>
                      <el-option v-for="fc in getFailCodes(peAnnotations[cp.id].left, cp.ability_id)" :key="fc.code" :label="fc.code + ' ' + fc.name" :value="fc.code" />
                    </el-select>
                  </div>
                </div>
                <div style="padding: 10px 14px; background: #f0faf0; border-radius: 8px;">
                  <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 13px; color: #67c23a; font-weight: 700;">B</span>
                    <el-radio-group v-model="peAnnotations[cp.id].right">
                      <el-radio-button value="C" style="margin-right: 4px;">C 达标</el-radio-button>
                      <el-radio-button value="R" style="margin-right: 4px;">R 部分</el-radio-button>
                      <el-radio-button value="N" style="margin-right: 4px;">N 缺失</el-radio-button>
                      <el-radio-button value="NA">不适用</el-radio-button>
                    </el-radio-group>
                  </div>
                  <div v-if="peAnnotations[cp.id].right && peAnnotations[cp.id].right !== 'C' && peAnnotations[cp.id].right !== 'NA' && failCodeMode !== 'disabled'" style="margin-top: 6px;">
                    <el-select v-model="peAnnotations[cp.id].right_fc" :placeholder="failCodeMode === 'required' ? '失败码（必填）' : '失败码（可选）'" size="small" style="width: 100%;" clearable>
                      <el-option v-for="fc in getFailCodes(peAnnotations[cp.id].right, cp.ability_id)" :key="fc.code" :label="fc.code + ' ' + fc.name" :value="fc.code" />
                    </el-select>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Overall Comparison (GSB per dimension) -->
          <div style="background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 20px; margin-bottom: 16px;">
            <div style="font-weight: 600; font-size: 15px; margin-bottom: 16px; color: #303133;">整体比较（按维度 GSB）</div>
            <p style="font-size: 12px; color: #999; margin-bottom: 16px;">基于对视频整体表现的判断，逐维度选择 A/B 谁更好</p>

            <div v-for="dim in peGsbDimensions" :key="dim.key"
              style="padding: 12px 16px; margin-bottom: 10px; border-radius: 8px;"
              :style="{ background: peGsb[dim.key] === 'a_better' ? '#fef0f0' : peGsb[dim.key] === 'b_better' ? '#f0f9eb' : '#f5f7fa' }">
              <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                <span style="font-size: 14px; font-weight: 600; min-width: 150px;">{{ dim.label }}</span>
                <el-radio-group v-model="peGsb[dim.key]">
                  <el-radio-button value="a_better">A更好</el-radio-button>
                  <el-radio-button value="same_good">一样好</el-radio-button>
                  <el-radio-button value="same_bad">一样差</el-radio-button>
                  <el-radio-button value="b_better">B更好</el-radio-button>
                </el-radio-group>
              </div>
              <!-- Reason required when A is better (B is worse) -->
              <div v-if="peGsb[dim.key] === 'a_better'" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #fab6b6;">
                <span style="font-size: 12px; color: #c62828; font-weight: 500;">相对 Prompt 描述，B 更差的主要原因（必选）：</span>
                <el-radio-group v-model="peReasons[dim.key]" size="small" style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px;">
                  <el-radio value="原始要求被遗漏或篡改">要求遗漏/篡改</el-radio>
                  <el-radio value="增加模型难以完成的内容">增加难完成内容</el-radio>
                  <el-radio value="画面稳定性下降">稳定性下降</el-radio>
                  <el-radio value="信息冲突或过载">信息冲突/过载</el-radio>
                  <el-radio value="其他">其他</el-radio>
                </el-radio-group>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div style="display: flex; justify-content: space-between; padding: 12px 0;">
            <el-button type="danger" plain @click="reportIssue">技术无效</el-button>
            <div style="display: flex; gap: 8px;">
              <el-button @click="saveAnnotations" :loading="saving">暂存</el-button>
              <el-button type="success" @click="completeAndNext" :loading="submitting"
                :disabled="!canSubmitPE || detail.assignment.status === 'submitted'">
                完成此题 →
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== BASE MODE (existing) ===== -->
      <div v-else style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
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
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 600;">Prompt</span>
              <el-button size="small" :type="showTranslation ? 'primary' : 'default'" @click="toggleTranslation" :loading="translating" round>
                {{ showTranslation ? '原文' : '中文' }}
              </el-button>
            </div>
          </template>
          <p style="line-height: 1.8; white-space: pre-wrap;">{{ showTranslation && translatedPrompt ? translatedPrompt : detail.question.prompt }}</p>
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
    </div><!-- end v-else base mode -->
    </div><!-- end v-if detail -->
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
const evalMode = computed(() => detail.value?.batch?.eval_mode || 'base')
const batchName = computed(() => detail.value?.batch?.name || '未知批次')

// Translation state (persists across questions)
const showTranslation = ref(false)
const translating = ref(false)
const translatedPrompt = ref('')
const translationCache = reactive({})  // { promptHash: translatedText }

// PE mode state
const peAnnotations = reactive({})  // {cp_id: {left: 'C', right: 'N'}}
const peComparison = ref('')  // legacy, kept for compat
const peReason = ref('')
const peGsb = reactive({})  // {dimension_key: 'a_better'|'same_good'|'same_bad'|'b_better'}
const peReasons = reactive({})  // {dimension_key: reason_string} — required when a_better

const peGsbDimensions = computed(() => {
  const dims = [
    { key: 'dynamics', label: '动态与物理合理性' },
    { key: 'camera', label: '镜头语言与跨镜连贯' },
    { key: 'aesthetics', label: '视觉美学' },
    { key: 'overall', label: '综合评价' },
  ]
  if (taskType.value === 't2av') {
    dims.splice(1, 0, { key: 'audio', label: '声音效果' })
  }
  return dims
})

const leftVideoUrl = computed(() => {
  if (!detail.value) return ''
  const order = detail.value.video.display_order || 'ab'
  return order === 'ab' ? detail.value.video.oss_url : detail.value.video.pair_b_url
})
const rightVideoUrl = computed(() => {
  if (!detail.value) return ''
  const order = detail.value.video.display_order || 'ab'
  return order === 'ab' ? detail.value.video.pair_b_url : detail.value.video.oss_url
})
const isRandomized = computed(() => {
  if (!detail.value) return false
  // Hide source if batch setting says so (default: hide)
  const hideSource = detail.value.batch?.pe_hide_source !== 0
  return hideSource
})

const peAnnotatedCount = computed(() => {
  return activeCheckpoints.value.filter(cp => peAnnotations[cp.id]?.left && peAnnotations[cp.id]?.right).length
})

const canSubmitPE = computed(() => {
  // All checkpoints must have left+right scores
  const cpsDone = activeCheckpoints.value.every(cp => peAnnotations[cp.id]?.left && peAnnotations[cp.id]?.right)
  if (!cpsDone) return false
  // If fail_code_mode = required, check fail codes for R/N
  if (failCodeMode.value === 'required') {
    const fcDone = activeCheckpoints.value.every(cp => {
      const pa = peAnnotations[cp.id]
      if (pa.left === 'R' || pa.left === 'N') { if (!pa.left_fc) return false }
      if (pa.right === 'R' || pa.right === 'N') { if (!pa.right_fc) return false }
      return true
    })
    if (!fcDone) return false
  }
  // All GSB dimensions must be selected
  const gsbDone = peGsbDimensions.value.every(dim => peGsb[dim.key])
  if (!gsbDone) return false
  // For every dimension where A is better, must have a reason
  const reasonsDone = peGsbDimensions.value.every(dim => {
    if (peGsb[dim.key] === 'a_better') return !!peReasons[dim.key]
    return true
  })
  if (!reasonsDone) return false
  return true
})

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
  // Load all task IDs for navigation (filtered to current batch)
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
  if (user.id) {
    try {
      const { data: allTasks } = await api.get('/assignments/my', { params: { user_id: user.id } })
      // Get current task's batch_id from the list
      const currentTask = allTasks.find(t => t.id === parseInt(id))
      const currentBatchId = currentTask?.batch_id
      // Filter to same batch only, exclude submitted
      taskIds.value = allTasks
        .filter(t => t.status !== 'submitted' && (!currentBatchId || t.batch_id === currentBatchId))
        .map(t => t.id)
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
  Object.keys(peAnnotations).forEach(k => delete peAnnotations[k])
  Object.keys(peGsb).forEach(k => delete peGsb[k])
  Object.keys(peReasons).forEach(k => delete peReasons[k])
  peComparison.value = ''
  peReason.value = ''
  try {
    const { data } = await api.get(`/assignments/${id}`)
    detail.value = data
    for (const cp of data.checkpoints) {
      annotations[cp.id] = { score: '', fail_code: null, evidence_ts: '', note: '' }
      peAnnotations[cp.id] = { left: '', right: '', left_fc: null, right_fc: null }
    }
    const { data: existing } = await api.get(`/annotations/assignment/${id}`)
    for (const ann of existing) {
      if (ann.target && peAnnotations[ann.checkpoint_id]) {
        // PE mode: map target A/B to left/right based on display_order
        const order = data.video.display_order || 'ab'
        if (ann.target === 'A') {
          peAnnotations[ann.checkpoint_id][order === 'ab' ? 'left' : 'right'] = ann.score
        } else if (ann.target === 'B') {
          peAnnotations[ann.checkpoint_id][order === 'ab' ? 'right' : 'left'] = ann.score
        }
      } else if (annotations[ann.checkpoint_id]) {
        annotations[ann.checkpoint_id].score = ann.score
        annotations[ann.checkpoint_id].fail_code = ann.fail_code
        annotations[ann.checkpoint_id].evidence_ts = ann.evidence_ts || ''
        annotations[ann.checkpoint_id].note = ann.note || ''
      }
    }
    // Load PE comparison from assignment
    if (data.assignment.pe_comparison) {
      try {
        const gsb = JSON.parse(data.assignment.pe_comparison)
        Object.assign(peGsb, gsb)
      } catch {
        peComparison.value = data.assignment.pe_comparison
      }
    }
    if (data.assignment.pe_reason) {
      try {
        const reasons = JSON.parse(data.assignment.pe_reason)
        Object.assign(peReasons, reasons)
      } catch {
        peReason.value = data.assignment.pe_reason
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

// Translation
async function fetchTranslation(prompt) {
  if (!prompt) return
  const key = prompt.slice(0, 100)
  if (translationCache[key]) {
    translatedPrompt.value = translationCache[key]
    return
  }
  translating.value = true
  try {
    const { data } = await api.post('/translate/', { text: prompt })
    translatedPrompt.value = data.translated
    translationCache[key] = data.translated
  } catch {
    translatedPrompt.value = '[翻译失败，请重试]'
  } finally {
    translating.value = false
  }
}

function toggleTranslation() {
  showTranslation.value = !showTranslation.value
  if (showTranslation.value && !translatedPrompt.value) {
    fetchTranslation(detail.value?.question?.prompt)
  }
}

// Auto-fetch translation when loading a new question if translation mode is on
watch(() => detail.value?.question?.prompt, (newPrompt) => {
  translatedPrompt.value = ''
  if (showTranslation.value && newPrompt) {
    const key = newPrompt.slice(0, 100)
    if (translationCache[key]) {
      translatedPrompt.value = translationCache[key]
    } else {
      fetchTranslation(newPrompt)
    }
  }
})

function buildPayload() {
  const id = props.assignmentId || route.params.assignmentId

  if (evalMode.value === 'pe') {
    // PE mode: two annotations per checkpoint (target A and B)
    const order = detail.value.video.display_order || 'ab'
    const items = []
    for (const cp of activeCheckpoints.value) {
      const pa = peAnnotations[cp.id]
      if (!pa) continue
      const leftTarget = order === 'ab' ? 'A' : 'B'
      const rightTarget = order === 'ab' ? 'B' : 'A'
      if (pa.left) items.push({ checkpoint_id: cp.id, score: pa.left, target: leftTarget, fail_code: pa.left !== 'C' && pa.left !== 'NA' ? pa.left_fc : null })
      if (pa.right) items.push({ checkpoint_id: cp.id, score: pa.right, target: rightTarget, fail_code: pa.right !== 'C' && pa.right !== 'NA' ? pa.right_fc : null })
    }
    return {
      assignment_id: parseInt(id),
      annotations: items,
      pe_comparison: JSON.stringify(peGsb),
      pe_reason: JSON.stringify(peReasons),
    }
  }

  // Base mode
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
    await api.post('/annotations/complete', { assignment_id: parseInt(props.assignmentId || route.params.assignmentId) })
    ElMessage.success('已完成此题')
    if (hasNext.value) {
      goTask('next')
    } else {
      await ElMessageBox.alert(
        `当前批次「${batchName.value}」的所有任务已完成！\n请返回任务列表提交锁定或选择其他批次。`,
        '批次任务已完成',
        { confirmButtonText: '返回任务列表', type: 'success' }
      )
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

<style scoped>
.prompt-scroll::-webkit-scrollbar {
  width: 8px;
}
.prompt-scroll::-webkit-scrollbar-track {
  background: #e8ecf0;
  border-radius: 4px;
}
.prompt-scroll::-webkit-scrollbar-thumb {
  background: #909399;
  border-radius: 4px;
}
.prompt-scroll::-webkit-scrollbar-thumb:hover {
  background: #606266;
}
</style>
