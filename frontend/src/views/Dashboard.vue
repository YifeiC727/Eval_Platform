<template>
  <div>
    <el-page-header title="结果看板" :icon="null" />

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="6">
        <el-statistic title="总检查点" :value="quality.total_checkpoints_compared || 0" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="A/B一致率" :value="quality.agreement_rate || 0" suffix="%" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="需第三人" :value="quality.third_needed || 0" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="待专家仲裁" :value="quality.pending_expert || 0" />
      </el-col>
    </el-row>

    <el-card style="margin-top: 20px;">
      <template #header>
        <span style="font-weight: 600;">30项核心能力排名（得分从低到高）</span>
      </template>
      <el-table :data="abilities" stripe style="width: 100%;" max-height="500">
        <el-table-column prop="ability_id" label="ID" width="60" />
        <el-table-column prop="ability_name" label="能力名称" min-width="200" />
        <el-table-column prop="score" label="得分" width="80" sortable>
          <template #default="{ row }">
            <span :style="{ color: row.score < 50 ? '#e6393e' : row.score < 70 ? '#e6a23c' : '#67c23a', fontWeight: 600 }">
              {{ row.score }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="C/R/N" width="120">
          <template #default="{ row }">
            <span style="color: #67c23a;">{{ row.c_count }}</span> /
            <span style="color: #e6a23c;">{{ row.r_count }}</span> /
            <span style="color: #e6393e;">{{ row.n_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="total_n" label="有效n" width="70" />
        <el-table-column prop="coverage_status" label="覆盖状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.coverage_status === '正式排名' ? 'success' : row.coverage_status === '初步趋势' ? 'warning' : 'danger'" size="small">
              {{ row.coverage_status }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card>
          <template #header><span style="font-weight: 600;">失败码分布</span></template>
          <el-table :data="failCodes" stripe size="small">
            <el-table-column prop="code" label="码" width="60" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="count" label="次数" width="80" sortable />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header><span style="font-weight: 600;">三级标签诊断（得分最低前20）</span></template>
          <el-table :data="tags.slice(0, 20)" stripe size="small">
            <el-table-column prop="tag_id" label="ID" width="100" />
            <el-table-column prop="tag_name" label="标签" />
            <el-table-column prop="score" label="得分" width="70" />
            <el-table-column prop="total_n" label="n" width="50" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api.js'

const abilities = ref([])
const quality = ref({})
const failCodes = ref([])
const tags = ref([])

onMounted(async () => {
  try {
    const [abRes, qRes, fcRes, tagRes] = await Promise.all([
      api.get('/scores/abilities'),
      api.get('/scores/quality'),
      api.get('/scores/fail-codes'),
      api.get('/scores/tags'),
    ])
    abilities.value = abRes.data
    quality.value = qRes.data
    failCodes.value = fcRes.data
    tags.value = tagRes.data
  } catch (e) {
    ElMessage.error('加载看板数据失败')
  }
})
</script>
