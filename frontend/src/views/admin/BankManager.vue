<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0;">题库管理</h2>
      <el-button type="primary" @click="showCreate = true">新建题库</el-button>
    </div>

    <!-- 题库列表 -->
    <el-table :data="bankList" stripe style="margin-bottom: 24px;">
      <el-table-column prop="name" label="题库名称" min-width="150" />
      <el-table-column prop="version" label="版本" width="70" />
      <el-table-column prop="question_count" label="题目数" width="80" />
      <el-table-column prop="checkpoint_count" label="检查点数" width="90" />
      <el-table-column prop="updated_at" label="更新时间" width="160">
        <template #default="{ row }">{{ row.updated_at?.slice(0, 16) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="deleteBank(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 导入/更新区域 -->
    <el-card>
      <template #header><span style="font-weight: 600;">导入 / 更新题库</span></template>
      <div style="display: flex; flex-direction: column; gap: 16px;">
        <div style="display: flex; gap: 16px; align-items: center;">
          <span style="white-space: nowrap;">选择题库:</span>
          <el-select v-model="selectedBank" placeholder="选择要导入到哪个题库" style="width: 300px;">
            <el-option v-for="b in bankList" :key="b.id" :label="`${b.name} (v${b.version})`" :value="b.id" />
          </el-select>
          <el-radio-group v-model="importMode" size="small">
            <el-radio-button value="append">追加/更新</el-radio-button>
            <el-radio-button value="replace">覆盖</el-radio-button>
          </el-radio-group>
        </div>
        <el-upload :auto-upload="false" :limit="1" accept=".xlsx,.xls" :on-change="handleFile" drag style="width: 100%;">
          <div style="padding: 16px;">
            <p>拖拽或点击选择 .xlsx（需含"原题"+"检查点拆解" sheet）</p>
          </div>
        </el-upload>
        <div style="display: flex; gap: 12px; align-items: center;">
          <el-button type="primary" @click="doImport" :loading="importing" :disabled="!selectedBank || !file">
            执行导入
          </el-button>
          <span v-if="file" style="color: #67c23a; font-size: 13px;">已选: {{ file.name }}</span>
        </div>
        <el-alert v-if="importResult" :title="importResult" type="success" show-icon />
      </div>
    </el-card>

    <!-- 新建题库弹窗 -->
    <el-dialog v-model="showCreate" title="新建题库" width="400px">
      <el-form label-position="top" @submit.prevent="createBank">
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

const emit = defineEmits(['refresh'])

const bankList = ref([])
const showCreate = ref(false)
const newBank = ref({ name: '', description: '' })
const selectedBank = ref(null)
const file = ref(null)
const importMode = ref('append')
const importing = ref(false)
const importResult = ref('')

onMounted(loadBanks)

async function loadBanks() {
  const { data } = await api.get('/banks/')
  bankList.value = data
}

async function createBank() {
  if (!newBank.value.name) { ElMessage.warning('请输入题库名称'); return }
  try {
    await api.post('/banks/', newBank.value)
    ElMessage.success('创建成功')
    showCreate.value = false
    newBank.value = { name: '', description: '' }
    await loadBanks()
    emit('refresh')
  } catch (e) { ElMessage.error(e.response?.data?.detail || '创建失败') }
}

async function deleteBank(row) {
  try {
    await ElMessageBox.confirm(`删除题库「${row.name}」？`, '确认', { type: 'error' })
    await api.delete(`/banks/${row.id}`)
    ElMessage.success('已删除')
    await loadBanks()
    emit('refresh')
  } catch {}
}

function handleFile(f) { file.value = f.raw; file.value.name = f.name }

async function doImport() {
  importing.value = true
  importResult.value = ''
  const formData = new FormData()
  formData.append('file', file.value)
  formData.append('mode', importMode.value)
  try {
    const { data } = await api.post(`/banks/${selectedBank.value}/import`, formData)
    importResult.value = `导入成功 (v${data.new_version}): +${data.questions_added}题 +${data.checkpoints_added}检查点, 更新${data.questions_updated}题 ${data.checkpoints_updated}检查点`
    await loadBanks()
    emit('refresh')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally { importing.value = false }
}
</script>
