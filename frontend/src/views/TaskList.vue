<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
      <h2 style="margin: 0;">我的任务</h2>
      <div style="display: flex; gap: 12px; align-items: center;">
        <el-tag v-if="todaySubmitted > 0" type="success">今日已提交 {{ todaySubmitted }} 个</el-tag>
        <el-tag>共 {{ tasks.length }} 个任务</el-tag>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="`待完成 (${pendingTasks.length})`" name="pending" />
      <el-tab-pane :label="`进行中 (${inProgressTasks.length})`" name="in_progress" />
      <el-tab-pane :label="`已提交 (${submittedTasks.length})`" name="submitted" />
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
            <el-tag :type="task.status === 'submitted' ? 'success' : task.status === 'in_progress' ? 'warning' : 'info'" size="small">
              {{ task.status === 'submitted' ? '已提交' : task.status === 'in_progress' ? '进行中' : '待开始' }}
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
import { ElMessage } from 'element-plus'
import api from '../api.js'

const router = useRouter()
const tasks = ref([])
const activeTab = ref('pending')

const pendingTasks = computed(() => tasks.value.filter(t => t.status === 'pending'))
const inProgressTasks = computed(() => tasks.value.filter(t => t.status === 'in_progress'))
const submittedTasks = computed(() => tasks.value.filter(t => t.status === 'submitted'))

const currentTasks = computed(() => {
  const map = { pending: pendingTasks, in_progress: inProgressTasks, submitted: submittedTasks }
  const list = map[activeTab.value]?.value || []
  return [...list].sort((a, b) => {
    if (a.role === 'third' && b.role !== 'third') return -1
    if (b.role === 'third' && a.role !== 'third') return 1
    return 0
  })
})

const todaySubmitted = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  return submittedTasks.value.filter(t => t.submitted_at?.startsWith(today)).length
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
</script>
