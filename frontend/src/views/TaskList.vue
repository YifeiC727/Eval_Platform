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
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="`待完成 (${pendingTasks.length})`" name="pending" />
      <el-tab-pane :label="`已完成 (${completedTasks.length})`" name="completed" />
      <el-tab-pane :label="`已锁定 (${submittedTasks.length})`" name="submitted" />
    </el-tabs>

    <!-- 批次筛选 -->
    <div style="margin-top: 12px; display: flex; gap: 12px; align-items: center;">
      <span style="font-size: 13px; color: #666;">筛选批次:</span>
      <el-select v-model="filterBatch" clearable placeholder="全部批次" size="small" style="width: 240px;">
        <el-option v-for="b in batchOptions" :key="b.id" :label="b.name" :value="b.id" />
      </el-select>
      <el-tag v-if="filterBatch" size="small" closable @close="filterBatch = null">
        {{ batchOptions.find(b => b.id === filterBatch)?.name }}
      </el-tag>
    </div>

    <!-- 按批次分组展示 -->
    <div style="margin-top: 16px;">
      <div v-for="group in groupedTasks" :key="group.batch_id" style="margin-bottom: 24px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #eee;">
          <span style="font-weight: 600; font-size: 14px; color: #303133;">{{ group.batch_name }}</span>
          <el-tag size="small" type="info">{{ group.tasks.length }} 题</el-tag>
          <el-tag v-if="group.third_count > 0" size="small" type="danger">{{ group.third_count }} 个仲裁</el-tag>
          <el-button v-if="activeTab === 'completed' && completedInGroup(group) > 0"
            size="small" type="primary" @click="submitBatch(group)" :loading="submittingBatch === group.batch_id">
            提交锁定已完成的 {{ completedInGroup(group) }} 题
          </el-button>
        </div>

        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div v-for="task in group.tasks" :key="task.id"
            :style="{
              background: task.role === 'third' ? '#fef0f0' : '#fff',
              border: '1px solid ' + (task.role === 'third' ? '#fab6b6' : '#e8ecf0'),
              borderRadius: '10px', padding: '16px', transition: 'all 0.15s', cursor: task.status === 'submitted' ? 'default' : 'pointer'
            }"
            @click="openTask(task)"
            @mouseenter="task.status !== 'submitted' && ($event.currentTarget.style.borderColor='#409eff', $event.currentTarget.style.boxShadow='0 2px 8px rgba(64,158,255,0.1)')"
            @mouseleave="$event.currentTarget.style.borderColor = task.role === 'third' ? '#fab6b6' : '#e8ecf0'; $event.currentTarget.style.boxShadow='none'">

            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
              <div style="display: flex; gap: 8px; align-items: center;">
                <el-tag :type="task.role === 'third' ? 'danger' : task.role === 'A' ? 'primary' : 'success'" size="small">
                  {{ task.role === 'third' ? '仲裁' : `角色 ${task.role}` }}
                </el-tag>
                <span style="font-weight: 600; font-size: 15px;">{{ task.question?.question_id }}</span>
                <span style="color: #999; font-size: 13px;">{{ task.video?.video_id }}</span>
              </div>
              <div style="display: flex; gap: 8px; align-items: center;">
                <el-tag v-if="task.role === 'third'" type="danger" size="small" effect="dark">高优先级</el-tag>
                <el-tag :type="statusTagType(task.status)" size="small">
                  {{ statusLabel(task.status) }}
                </el-tag>
              </div>
            </div>

            <div style="background: #f8fafc; border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; line-height: 1.6; font-size: 13px; color: #333; white-space: pre-wrap; word-break: break-word; max-height: 60px; overflow: hidden;">
              {{ task.question?.prompt }}
            </div>

            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div style="display: flex; gap: 16px; font-size: 12px; color: #888;">
                <span>检查点: {{ task.checkpoint_count }} 个</span>
                <span v-if="task.annotated_count > 0">已标注: {{ task.annotated_count }}/{{ task.checkpoint_count }}</span>
              </div>
              <el-button v-if="task.status !== 'submitted'" type="primary" size="small" @click.stop="openTask(task)">
                {{ task.role === 'third' ? '仲裁标注' : task.annotated_count > 0 ? '继续标注' : '开始标注' }}
              </el-button>
              <el-button v-else size="small" disabled @click.stop>已锁定</el-button>
            </div>

            <el-progress v-if="task.checkpoint_count > 0 && task.annotated_count > 0"
              :percentage="Math.round(task.annotated_count / task.checkpoint_count * 100)"
              :stroke-width="5" style="margin-top: 8px;" />
          </div>
        </div>
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
const submittingBatch = ref(null)
const filterBatch = ref(null)

const filteredByBatch = computed(() => {
  if (!filterBatch.value) return tasks.value
  return tasks.value.filter(t => t.batch_id === filterBatch.value)
})

const batchOptions = computed(() => {
  const map = {}
  for (const t of tasks.value) {
    if (t.batch_id && !map[t.batch_id]) {
      map[t.batch_id] = { id: t.batch_id, name: t.batch_name || `批次 ${t.batch_id}` }
    }
  }
  return Object.values(map)
})

const pendingTasks = computed(() => filteredByBatch.value.filter(t => t.status === 'pending' || t.status === 'in_progress'))
const completedTasks = computed(() => filteredByBatch.value.filter(t => t.status === 'completed' || t.status === 'issue_reported'))
const submittedTasks = computed(() => filteredByBatch.value.filter(t => t.status === 'submitted'))

const canSubmitAll = computed(() => {
  if (tasks.value.length === 0) return false
  return tasks.value.every(t => t.status === 'completed' || t.status === 'submitted' || t.status === 'issue_reported' || t.status === 'invalidated')
})

const currentTasks = computed(() => {
  const map = { pending: pendingTasks, completed: completedTasks, submitted: submittedTasks }
  const list = map[activeTab.value]?.value || []
  // 仲裁任务排最前
  return [...list].sort((a, b) => {
    if (a.role === 'third' && b.role !== 'third') return -1
    if (b.role === 'third' && a.role !== 'third') return 1
    return 0
  })
})

const groupedTasks = computed(() => {
  const groups = {}
  for (const task of currentTasks.value) {
    const key = task.batch_id || 'unknown'
    if (!groups[key]) {
      groups[key] = { batch_id: key, batch_name: task.batch_name || '未知批次', tasks: [], third_count: 0 }
    }
    groups[key].tasks.push(task)
    if (task.role === 'third') groups[key].third_count++
  }
  // 有仲裁任务的批次排前面
  return Object.values(groups).sort((a, b) => b.third_count - a.third_count)
})

function statusTagType(status) {
  const map = { submitted: 'success', completed: 'warning', issue_reported: 'danger' }
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = { submitted: '已锁定', completed: '已完成', issue_reported: '技术无效', pending: '待标注', in_progress: '标注中' }
  return map[status] || status
}

onMounted(async () => {
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
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
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
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
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
  try {
    const { data } = await api.post('/annotations/submit-all', { user_id: user.id })
    ElMessage.success(`已锁定 ${data.locked_count} 题`)
    const { data: newTasks } = await api.get('/assignments/my', { params: { user_id: user.id } })
    tasks.value = newTasks
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally {
    submittingAll.value = false
  }
}

function completedInGroup(group) {
  return group.tasks.filter(t => t.status === 'completed' || t.status === 'issue_reported').length
}

async function submitBatch(group) {
  const count = completedInGroup(group)
  try {
    await ElMessageBox.confirm(
      `确认提交锁定？将锁定「${group.batch_name}」中已完成的 ${count} 题，提交后不可修改。`,
      '提交锁定',
      { type: 'warning', confirmButtonText: '确认提交', cancelButtonText: '取消' }
    )
  } catch { return }

  submittingBatch.value = group.batch_id
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
  try {
    const { data } = await api.post('/annotations/submit-all', { user_id: user.id, batch_id: group.batch_id })
    ElMessage.success(`已锁定 ${data.locked_count} 题`)
    const { data: newTasks } = await api.get('/assignments/my', { params: { user_id: user.id } })
    tasks.value = newTasks
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally {
    submittingBatch.value = null
  }
}
</script>
