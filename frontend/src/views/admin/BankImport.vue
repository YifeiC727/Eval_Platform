<template>
  <div>
    <h2 style="margin-bottom: 16px;">导入 / 更新题库</h2>

    <el-alert type="info" :closable="false" style="margin-bottom: 20px;">
      <template #title>操作说明</template>
      <p>选择题库 → 上传 xlsx → 选择模式（追加/覆盖）→ 执行导入。</p>
      <p style="margin-top: 4px; color: #666;">追加模式：新检查点加入，已有的更新内容。覆盖模式：清空题库后重新导入。</p>
    </el-alert>

    <el-card>
      <div style="display: flex; flex-direction: column; gap: 20px;">
        <div>
          <h4 style="margin-bottom: 8px;">① 选择题库</h4>
          <el-select v-model="selectedBank" placeholder="选择题库" style="width: 300px;">
            <el-option v-for="b in banks" :key="b.id" :label="`${b.name} (v${b.version})`" :value="b.id" />
          </el-select>
        </div>

        <div>
          <h4 style="margin-bottom: 8px;">② 上传 Excel</h4>
          <el-upload :auto-upload="false" :limit="1" accept=".xlsx,.xls" :on-change="handleFile" drag>
            <div style="padding: 20px;">
              <p>拖拽或点击选择 .xlsx 文件</p>
              <p style="color: #999; font-size: 12px;">需包含"原题"和"检查点拆解"两个 sheet</p>
            </div>
          </el-upload>
          <p v-if="file" style="margin-top: 8px; color: #67c23a;">已选择: {{ file.name }}</p>
        </div>

        <div>
          <h4 style="margin-bottom: 8px;">③ 导入模式</h4>
          <el-radio-group v-model="mode">
            <el-radio-button value="append">追加/更新</el-radio-button>
            <el-radio-button value="replace">覆盖（清空后重导）</el-radio-button>
          </el-radio-group>
        </div>

        <el-button type="primary" size="large" @click="doImport" :loading="importing" :disabled="!selectedBank || !file">
          执行导入
        </el-button>

        <el-alert v-if="result" :title="result" type="success" show-icon />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../api.js'

const props = defineProps(['banks'])
const emit = defineEmits(['refresh'])

const selectedBank = ref(null)
const file = ref(null)
const mode = ref('append')
const importing = ref(false)
const result = ref('')

function handleFile(f) { file.value = f.raw; file.value.name = f.name }

async function doImport() {
  importing.value = true
  result.value = ''
  const formData = new FormData()
  formData.append('file', file.value)
  formData.append('mode', mode.value)
  try {
    const { data } = await api.post(`/banks/${selectedBank.value}/import`, formData)
    result.value = `导入成功 (v${data.new_version}): +${data.questions_added}题 +${data.checkpoints_added}检查点, 更新${data.questions_updated}题 ${data.checkpoints_updated}检查点`
    emit('refresh')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally { importing.value = false }
}
</script>
