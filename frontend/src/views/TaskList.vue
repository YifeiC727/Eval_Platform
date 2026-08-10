<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
      <h2 style="margin: 0;">我的任务</h2>
      <div style="display: flex; gap: 12px; align-items: center;">
        <el-tag v-if="completedTasks.length > 0" type="warning">已完成 {{ completedTasks.length }} 题</el-tag>
        <el-tag>共 {{ tasks.length }} 个任务</el-tag>
        <el-button size="small" @click="exportMy" :disabled="completedTasks.length === 0 && submittedTasks.length === 0">
          导出我的标注
        </el-button>
        <el-button type="primary" @click="submitAll" :loading="submittingAll"
          :disabled="!canSubmitAll">
          全部提交锁定
        </el-button>
      </div>
    </div>

    <el-alert v-if="!canSubmitAll && completedTasks.length > 0 && pendingTasks.length > 0"
      type="warning" :closable="false" style="margin-bottom: 16px;">
      还有 {{ pendingTasks.length }} 题未完成，需全部完成或标记技术无效后才能提交锁定。
    </el-alert>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="`待完成 (${pendingTasks.length})`" name="pending" />
      <el-tab-pane :label="`已完成 (${completedTasks.length})`" name="completed" />
      <el-tab-pane :label="`已锁定 (${submittedTasks.length})`" name="submitted" />
    </el-tabs>

    <div style="display: flex; flex-direction: column; gap: 12px; margin-top: 16px;">
      <div v-for="task in currentTasks" :key="task.id"
        style="background: #fff; border: 1px solid #e8ecf0; border-radius: 10px; padding: 20px; transition: all 0.15s; cursor: pointer;"
        @click="openTask(task)"
        @mouseenter="$event.currentTarget.style.borderColor='#409eff'; $event.currentTarget.style.boxShadow='0 2px 8px rgba(64,158,255,0.1)'"
        @mouseleave="$event.currentTarget.style.borderColor='#e8ecf0'; $event.currentTarget.style.boxShadow='none'">

        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-tag :type="task.role === 'third' ? 'danger' : task.role === 'A' ? 'primary' : 'success'" size="small">
              {{ task.role === 'third' ? '仲裁' : `角色 ${task.role}` }}
            </el-tag>
            <span style="font-weight: 600; font-size: 15px;">{{ task.question?.question_id }}</span>
            <span style="color: #999; font-size: 13px;">{{ task.video?.video_id }}</span>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <el-tag v-if="task.role === 'third'" type="danger" size="small" effect="dark">高优先级</el-tag>
            <el-tag :type="task.status === 'submitted' ? 'success' : task.status === 'completed' ? 'warning' : task.status === 'issue_reported' ? 'danger' : 'info'" size="small">
              {{ task.status === 'submitted' ? '已锁定' : task.status === 'completed' ? '已完成' : task.status === 'issue_reported' ? '技术无效' : '待标注' }}
            </el-tag>
          </div>
        </div>

        <div style="background: #f8fafc; border-radius: 6px; padding: 12px; margin-bottom: 12px; line-height: 1.7; font-size: 14px; color: #333; white-space: pre-wrap; word-break: break-word;">
          {{ task.question?.prompt }}
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div style="display: flex; gap: 16px; font-size: 13px; color: #888;">
            <span>检查点: {{ task.checkpoint_count }} 个</span>
            <span v-if="task.annotated_count > 0">已标注: {{ task.annotated_count }}/{{ task.checkpoint_count }}</span>
            <span v-if="task.assigned_at">分配: {{ task.assigned_at?.slice(0, 10) }}</span>
          </div>
          <el-button v-if="task.status !== 'submitted'" type="primary" size="small" @click.stop="openTask(task)">
            {{ task.annotated_count > 0 ? '继续标注' : '开始标注' }}
          </el-button>
          <el-button v-else size="small" disabled @click.stop>已锁定</el-button>
        </div>

        <el-progress v-if="task.checkpoint_count > 0 && task.annotated_count > 0"
          :percentage="Math.round(task.annotated_count / task.checkpoint_count * 100)"
          :stroke-width="6" style="margin-top: 10px;" />
      </div>

      <el-empty v-if="currentTasks.length === 0" description="暂无任务" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api.js'

const router = useRouter()
const tasks = ref([])
const activeTab = ref('pending')
const submittingAll = ref(false)

const pendingTasks = computed(() => tasks.value.filter(t => t.status === 'pending' || t.status === 'in_progress'))
const completedTasks = computed(() => tasks.value.filter(t => t.status === 'completed'))
const submittedTasks = computed(() => tasks.value.filter(t => t.status === 'submitted'))

const canSubmitAll = computed(() => {
  if (tasks.value.length === 0) return false
  return tasks.value.every(t => t.status === 'completed' || t.status === 'submitted' || t.status === 'issue_reported' || t.status === 'invalidated')
})

const currentTasks = computed(() => {
  const map = { pending: pendingTasks, completed: completedTasks, submitted: submittedTasks }
  const list = map[activeTab.value]?.value || []
  return [...list].sort((a, b) => {
    if (a.role === 'third' && b.role !== 'third') return -1
    if (b.role === 'third' && a.role !== 'third') return 1
    return 0
  })
})

onMounted(async () => {
  const user = JSON.parse(localStorage.getItem('user') || '{}')
  if (!user.id) return
  try {
    const { data } = await api.get('/assignments/my', { params: { user_id: user.id } })
    tasks.value = data
  } catch (e) {
    ElMessage.error('获取任务失败')
  }
})

function openTask(task) {
  if (task.status === 'submitted') return
  router.push(`/annotate/${task.id}`)
}

function exportMy() {
  const user = JSON.parse(localStorage.getItem('user') || '{}')
  window.open(`/api/export/my-annotations?user_id=${user.id}`, '_blank')
}

async function submitAll() {
  try {
    await ElMessageBox.confirm(
      `确认全部提交锁定？共 ${completedTasks.value.length} 题将被锁定，提交后不可修改。`,
      '全部提交锁定',
      { type: 'warning', confirmButtonText: '确认提交', cancelButtonText: '取消' }
    )
  } catch { return }

  submittingAll.value = true
  const user = JSON.parse(localStorage.getItem('user') || '{}')
  try {
    const { data } = await api.post('/annotations/submit-all', { user_id: user.id })
    ElMessage.success(`已锁定 ${data.locked_count} 题`)
    // Reload tasks
    const { data: newTasks } = await api.get('/assignments/my', { params: { user_id: user.id } })
    tasks.value = newTasks
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally {
    submittingAll.value = false
  }
}
</script>
