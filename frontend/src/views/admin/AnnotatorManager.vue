<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0;">标注员管理</h2>
      <el-button type="primary" @click="showCreate = true">添加用户</el-button>
    </div>

    <el-table :data="users" stripe>
      <el-table-column prop="username" label="用户名" width="100" />
      <el-table-column prop="display_name" label="姓名" width="80" />
      <el-table-column prop="password" label="密码" width="120">
        <template #default="{ row }"><span style="font-family: monospace;">{{ row.password || '-' }}</span></template>
      </el-table-column>
      <el-table-column prop="role" label="角色" width="100" />
      <el-table-column prop="total_tasks" label="总任务" width="70" />
      <el-table-column prop="submitted_tasks" label="已提交" width="70" />
      <el-table-column label="完成率" width="100">
        <template #default="{ row }">
          <el-progress :percentage="row.completion_rate || 0" :stroke-width="10" :text-inside="true" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" @click="openPassword(row)">密码</el-button>
          <el-button size="small" type="danger" @click="deleteUser(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showCreate" title="添加用户" width="400px">
      <el-form label-position="top">
        <el-form-item label="用户名"><el-input v-model="newUser.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="newUser.display_name" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="newUser.role" style="width: 100%;">
            <el-option label="标注员" value="annotator" />
            <el-option label="组长" value="lead" />
            <el-option label="管理员" value="admin" />
            <el-option label="管理员+标注员" value="admin,annotator" />
          </el-select>
        </el-form-item>
        <el-form-item label="密码（可选）"><el-input v-model="newUser.password" placeholder="不填则无需密码" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createUser">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEdit" title="编辑用户" width="400px">
      <el-form label-position="top">
        <el-form-item label="用户名"><el-input v-model="editData.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="editData.display_name" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="editData.role" style="width: 100%;">
            <el-option label="标注员" value="annotator" />
            <el-option label="组长" value="lead" />
            <el-option label="管理员" value="admin" />
            <el-option label="管理员+标注员" value="admin,annotator" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" @click="doEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showPassword" title="设置密码" width="400px">
      <p>为 <strong>{{ pwUser?.display_name }}</strong> 设置密码</p>
      <el-input v-model="pwValue" placeholder="输入新密码" style="margin-top: 12px;" />
      <template #footer>
        <el-button @click="showPassword = false">取消</el-button>
        <el-button type="primary" @click="doPassword">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api.js'

const users = ref([])
const showCreate = ref(false)
const showEdit = ref(false)
const showPassword = ref(false)
const newUser = ref({ username: '', display_name: '', role: 'annotator', password: '' })
const editData = ref({ id: null, username: '', display_name: '', role: '' })
const pwUser = ref(null)
const pwValue = ref('')

onMounted(loadUsers)

async function loadUsers() {
  const { data } = await api.get('/stats/annotators')
  // Also get admins/leads
  const { data: allUsers } = await api.get('/users/')
  const statsMap = {}
  for (const s of data) { statsMap[s.id] = s }
  users.value = allUsers.map(u => ({ ...u, ...(statsMap[u.id] || { total_tasks: 0, submitted_tasks: 0, completion_rate: 0 }) }))
}

async function createUser() {
  try {
    await api.post('/users/', newUser.value)
    ElMessage.success('创建成功')
    showCreate.value = false
    newUser.value = { username: '', display_name: '', role: 'annotator', password: '' }
    await loadUsers()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '失败') }
}

function openEdit(row) {
  editData.value = { id: row.id, username: row.username, display_name: row.display_name, role: row.role }
  showEdit.value = true
}

async function doEdit() {
  try {
    await api.put(`/users/${editData.value.id}`, editData.value)
    ElMessage.success('保存成功')
    showEdit.value = false
    await loadUsers()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '失败') }
}

function openPassword(row) {
  pwUser.value = row
  pwValue.value = ''
  showPassword.value = true
}

async function doPassword() {
  if (!pwValue.value || pwValue.value.length < 4) { ElMessage.warning('至少4位'); return }
  try {
    await api.put(`/users/${pwUser.value.id}/password`, { password: pwValue.value })
    ElMessage.success('设置成功')
    showPassword.value = false
    await loadUsers()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '失败') }
}

async function deleteUser(row) {
  try {
    await ElMessageBox.confirm(`删除「${row.display_name || row.username}」？`, '确认', { type: 'error' })
    await api.delete(`/users/${row.id}`)
    ElMessage.success('已删除')
    await loadUsers()
  } catch {}
}
</script>
