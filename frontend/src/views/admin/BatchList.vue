<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
      <h2 style="margin: 0;">评测批次</h2>
      <el-button type="primary" @click="showCreate = true">新建批次</el-button>
    </div>

    <el-table :data="batchList" stripe @row-click="(row) => emit('select', row)">
      <el-table-column prop="name" label="批次名称" min-width="150" />
      <el-table-column prop="bank_name" label="题库" width="120" />
      <el-table-column prop="model_version" label="模型版本" width="100" />
      <el-table-column prop="annotation_mode" label="模式" width="80">
        <template #default="{ row }">
          <el-tag :type="row.annotation_mode === 'dual' ? 'warning' : 'info'" size="small">
            {{ row.annotation_mode === 'dual' ? '双人' : '单人' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'completed' ? 'success' : row.status === 'labeling' ? 'warning' : 'info'" size="small">
            {{ row.status === 'completed' ? '已完成' : row.status === 'labeling' ? '标注中' : '准备中' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="120">
        <template #default="{ row }">
          <el-progress :percentage="row.progress" :stroke-width="12" :text-inside="true" />
        </template>
      </el-table-column>
      <el-table-column prop="total_videos" label="视频" width="60" />
      <el-table-column prop="created_at" label="创建时间" width="110">
        <template #default="{ row }">{{ row.created_at?.slice(0, 10) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click.stop="deleteBatch(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!batchList.length" description="暂无评测批次" />

    <el-dialog v-model="showCreate" title="新建评测批次" width="500px">
      <el-form label-position="top">
        <el-form-item label="选择题库">
          <el-select v-model="newBatch.bank_id" style="width: 100%;">
            <el-option v-for="b in banks" :key="b.id" :label="`${b.name} (${b.question_count}题, v${b.version})`" :value="b.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型版本">
          <el-input v-model="newBatch.model_version" placeholder="如: model_v13" />
        </el-form-item>
        <el-form-item label="批次名称（可选）">
          <el-input v-model="newBatch.name" placeholder="默认: 题库名 + 模型版本" />
        </el-form-item>
        <el-form-item label="标注模式">
          <el-radio-group v-model="newBatch.annotation_mode">
            <el-radio-button value="single">单人标注</el-radio-button>
            <el-radio-button value="dual">双人盲标</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newBatch.description" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createBatch" :disabled="!newBatch.bank_id || !newBatch.model_version">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api.js'

const props = defineProps(['banks'])
const emit = defineEmits(['select'])

const batchList = ref([])
const showCreate = ref(false)
const newBatch = ref({ bank_id: null, model_version: '', name: '', annotation_mode: 'single', description: '' })

onMounted(loadBatches)

async function loadBatches() {
  const { data } = await api.get('/batches/')
  batchList.value = data
}

async function createBatch() {
  try {
    const { data } = await api.post('/batches/', newBatch.value)
    ElMessage.success(`批次创建成功，已生成 ${data.videos_created} 个视频`)
    showCreate.value = false
    newBatch.value = { bank_id: null, model_version: '', name: '', annotation_mode: 'single', description: '' }
    await loadBatches()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '创建失败') }
}

async function deleteBatch(row) {
  try {
    await ElMessageBox.confirm(`确认删除批次「${row.name}」？所有标注数据将被删除。`, '删除', { type: 'error' })
    await api.delete(`/batches/${row.id}`)
    ElMessage.success('已删除')
    await loadBatches()
  } catch {}
}
</script>
