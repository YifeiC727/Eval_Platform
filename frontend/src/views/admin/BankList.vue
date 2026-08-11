<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0;">题库列表</h2>
      <el-button type="primary" @click="showCreate = true">新建题库</el-button>
    </div>
    <el-table :data="banks" stripe>
      <el-table-column prop="name" label="题库名称" min-width="150" />
      <el-table-column prop="version" label="版本" width="70" />
      <el-table-column prop="question_count" label="题目数" width="80" />
      <el-table-column prop="checkpoint_count" label="检查点数" width="90" />
      <el-table-column prop="updated_at" label="更新时间" width="160">
        <template #default="{ row }">{{ row.updated_at?.slice(0, 16) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="deleteBank(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!banks.length" description="暂无题库，请先导入" />

    <el-dialog v-model="showCreate" title="新建题库" width="400px">
      <el-form label-position="top">
        <el-form-item label="题库名称"><el-input v-model="newBank.name" placeholder="如: T2V-10s 能力题库" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="newBank.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createBank">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api.js'

const emit = defineEmits(['select'])
const banks = ref([])
const showCreate = ref(false)
const newBank = ref({ name: '', description: '' })

onMounted(loadBanks)

async function loadBanks() {
  const { data } = await api.get('/banks/')
  banks.value = data
}

async function createBank() {
  try {
    await api.post('/banks/', newBank.value)
    ElMessage.success('创建成功')
    showCreate.value = false
    newBank.value = { name: '', description: '' }
    await loadBanks()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '创建失败') }
}

async function deleteBank(row) {
  try {
    await ElMessageBox.confirm(`确认删除题库「${row.name}」？所有题目和检查点将被删除。`, '删除', { type: 'error' })
    await api.delete(`/banks/${row.id}`)
    ElMessage.success('已删除')
    await loadBanks()
  } catch {}
}
</script>
