<template>
  <el-container style="min-height: calc(100vh - 100px);">
    <el-aside width="180px" style="background: #fff; border-right: 1px solid #e8ecf0;">
      <el-menu :default-active="activeMenu" @select="handleMenuSelect" style="border: none;">
        <el-menu-item-group title="题库管理">
          <el-menu-item index="banks">题库列表</el-menu-item>
          <el-menu-item index="bank-import">导入 / 更新</el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group title="评测批次">
          <el-menu-item index="batches">批次列表</el-menu-item>
          <el-menu-item index="batch-detail" v-if="currentBatch">当前批次</el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group title="分析">
          <el-menu-item index="compare">版本对比</el-menu-item>
        </el-menu-item-group>
        <el-menu-item-group title="人员">
          <el-menu-item index="annotators">标注员管理</el-menu-item>
        </el-menu-item-group>
      </el-menu>
    </el-aside>
    <el-main style="padding: 24px;">
      <BankList v-if="activeMenu === 'banks'" @select="selectBank" />
      <BankImport v-else-if="activeMenu === 'bank-import'" :banks="banks" @refresh="loadBanks" />
      <BatchList v-else-if="activeMenu === 'batches'" :banks="banks" @select="selectBatch" />
      <BatchDetail v-else-if="activeMenu === 'batch-detail'" :batch="currentBatch" :annotators="annotatorList" @refresh="refreshBatch" />
      <VersionCompare v-else-if="activeMenu === 'compare'" :batches="batchList" />
      <AnnotatorManager v-else-if="activeMenu === 'annotators'" />
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'
import BankList from './admin/BankList.vue'
import BankImport from './admin/BankImport.vue'
import BatchList from './admin/BatchList.vue'
import BatchDetail from './admin/BatchDetail.vue'
import VersionCompare from './admin/VersionCompare.vue'
import AnnotatorManager from './admin/AnnotatorManager.vue'

const activeMenu = ref('batches')
const banks = ref([])
const batchList = ref([])
const currentBatch = ref(null)
const annotatorList = ref([])

onMounted(async () => {
  await Promise.all([loadBanks(), loadBatches(), loadAnnotators()])
})

async function loadBanks() {
  const { data } = await api.get('/banks/')
  banks.value = data
}

async function loadBatches() {
  const { data } = await api.get('/batches/')
  batchList.value = data
}

async function loadAnnotators() {
  const { data } = await api.get('/users/')
  annotatorList.value = data.filter(u => u.role.includes('annotator'))
}

function selectBank(bank) {
  activeMenu.value = 'banks'
}

function selectBatch(batch) {
  currentBatch.value = batch
  activeMenu.value = 'batch-detail'
}

async function refreshBatch() {
  if (currentBatch.value) {
    const { data } = await api.get(`/batches/${currentBatch.value.id}`)
    currentBatch.value = data
  }
  await loadBatches()
}

function handleMenuSelect(key) {
  activeMenu.value = key
}
</script>
