<template>
  <el-container style="min-height: calc(100vh - 100px);">
    <el-aside width="170px" style="background: #fff; border-right: 1px solid #e8ecf0;">
      <el-menu :default-active="activeMenu" @select="handleMenuSelect" style="border: none;">
        <el-menu-item index="expert">
          <span>待我裁决</span>
          <el-badge v-if="expertCount > 0" :value="expertCount" style="margin-left: 6px;" />
        </el-menu-item>
        <el-menu-item index="batches">
          <span>评测批次</span>
        </el-menu-item>
        <el-menu-item index="batch-detail" v-if="currentBatch">
          <span>{{ currentBatch.name?.slice(0, 8) }}...</span>
        </el-menu-item>
        <el-menu-item index="banks">
          <span>题库管理</span>
        </el-menu-item>
        <el-menu-item index="annotators">
          <span>标注员</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main style="padding: 24px;">
      <div v-if="activeMenu === 'expert'">
        <h2 style="margin-bottom: 16px;">待裁决任务</h2>
        <p v-if="!expertTasks.length && !invalidTasks.length" style="color: #999;">暂无需要裁决的任务</p>

        <!-- 技术无效审核 -->
        <div v-if="invalidTasks.length > 0" style="margin-bottom: 24px;">
          <h3 style="font-size: 15px; color: #e65100; margin-bottom: 12px;">技术无效审核 ({{ invalidTasks.length }})</h3>
          <div v-for="task in invalidTasks" :key="'inv-'+task.id"
            style="background: #fff3e0; border: 1px solid #ffe0b2; border-radius: 10px; padding: 16px; margin-bottom: 12px; cursor: pointer;"
            @click="$router.push('/annotate/' + task.id)">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div style="display: flex; gap: 8px; align-items: center;">
                <el-tag type="warning" size="small" effect="dark">技术无效</el-tag>
                <span style="font-weight: 600;">{{ task.question?.question_id }}</span>
                <span style="color: #999; font-size: 13px;">{{ task.video?.video_id }}</span>
              </div>
              <el-tag size="small">点击进入查看详情</el-tag>
            </div>
            <div style="font-size: 13px; color: #666; line-height: 1.5; max-height: 40px; overflow: hidden;">
              {{ task.question?.prompt }}
            </div>
          </div>
        </div>

        <!-- 三人不一致裁决 -->
        <div v-if="expertTasks.length > 0">
          <h3 style="font-size: 15px; color: #c62828; margin-bottom: 12px;">三人不一致裁决 ({{ expertTasks.length }})</h3>
          <div v-for="task in expertTasks" :key="task.id"
            style="background: #fff7ed; border: 1px solid #fed7aa; border-radius: 10px; padding: 16px; margin-bottom: 12px; cursor: pointer;"
            @click="$router.push('/annotate/' + task.id)">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div style="display: flex; gap: 8px; align-items: center;">
                <el-tag type="danger" size="small" effect="dark">专家裁决</el-tag>
                <span style="font-weight: 600;">{{ task.question?.question_id }}</span>
                <span style="color: #999; font-size: 13px;">{{ task.video?.video_id }}</span>
              </div>
              <el-tag size="small">{{ task.checkpoint_count }} 个待裁决</el-tag>
            </div>
            <div style="font-size: 13px; color: #666; line-height: 1.5; max-height: 40px; overflow: hidden;">
              {{ task.question?.prompt }}
            </div>
          </div>
        </div>
      </div>
      <BatchList v-else-if="activeMenu === 'batches'" @select="selectBatch" />
      <BatchDetail v-else-if="activeMenu === 'batch-detail' && currentBatch" :batch="currentBatch" :annotators="annotatorList" @refresh="refreshBatch" />
      <BankManager v-else-if="activeMenu === 'banks'" @refresh="loadBanks" />
      <AnnotatorManager v-else-if="activeMenu === 'annotators'" />
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api.js'
import BankManager from './admin/BankManager.vue'
import BatchList from './admin/BatchList.vue'
import BatchDetail from './admin/BatchDetail.vue'
import AnnotatorManager from './admin/AnnotatorManager.vue'

const router = useRouter()
const activeMenu = ref('expert')
const currentBatch = ref(null)
const annotatorList = ref([])
const expertTasks = ref([])
const invalidTasks = ref([])

const expertCount = computed(() => expertTasks.value.filter(t => t.status !== 'submitted').length + invalidTasks.value.length)

onMounted(async () => {
  await loadAnnotators()
  await loadExpertTasks()
})

async function loadExpertTasks() {
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
  if (!user.id) return
  try {
    const { data } = await api.get('/assignments/my', { params: { user_id: user.id } })
    const allExpert = data.filter(t => t.role === 'expert' && t.status !== 'submitted')
    // Separate by type: technical invalid (has issue_type marker) vs disagreement
    invalidTasks.value = allExpert.filter(t => t.is_invalid_review)
    expertTasks.value = allExpert.filter(t => !t.is_invalid_review)
  } catch {}
}

async function loadBanks() {}

async function dropVideo(task) {
  const { ElMessageBox, ElMessage } = await import('element-plus')
  try {
    await ElMessageBox.confirm(
      `确认废弃视频 ${task.video?.video_id}（${task.question?.question_id}）？废弃后该题不计入任何统计。`,
      '确认技术无效废弃',
      { type: 'error', confirmButtonText: '确认废弃', cancelButtonText: '取消' }
    )
    await api.post(`/issues/drop/${task.video_id}`)
    ElMessage.success('已废弃')
    await loadExpertTasks()
  } catch {}
}

async function loadAnnotators() {
  const { data } = await api.get('/users/')
  annotatorList.value = data.filter(u => u.role.includes('annotator'))
}

async function selectBatch(batch) {
  currentBatch.value = batch
  activeMenu.value = 'batch-detail'
  // Fetch full detail (includes role_stats)
  try {
    const { data } = await api.get(`/batches/${batch.id}`)
    currentBatch.value = data
  } catch {}
}

async function refreshBatch() {
  if (currentBatch.value) {
    const { data } = await api.get(`/batches/${currentBatch.value.id}`)
    currentBatch.value = data
  }
}

function handleMenuSelect(key) {
  activeMenu.value = key
}
</script>
