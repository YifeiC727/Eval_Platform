<template>
  <el-container style="min-height: calc(100vh - 100px);">
    <el-aside width="170px" style="background: #fff; border-right: 1px solid #e8ecf0;">
      <el-menu :default-active="activeMenu" @select="handleMenuSelect" style="border: none;">
        <el-menu-item index="batches">
          <span>评测批次</span>
        </el-menu-item>
        <el-menu-item index="batch-detail" v-if="currentBatch">
          <span>{{ currentBatch.name?.slice(0, 8) }}...</span>
        </el-menu-item>
        <el-menu-item index="banks">
          <span>题库管理</span>
        </el-menu-item>
        <el-menu-item index="compare">
          <span>版本对比</span>
        </el-menu-item>
        <el-menu-item index="annotators">
          <span>标注员</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main style="padding: 24px;">
      <BatchList v-if="activeMenu === 'batches'" @select="selectBatch" />
      <BatchDetail v-else-if="activeMenu === 'batch-detail' && currentBatch" :batch="currentBatch" :annotators="annotatorList" @refresh="refreshBatch" />
      <BankManager v-else-if="activeMenu === 'banks'" @refresh="loadBanks" />
      <VersionCompare v-else-if="activeMenu === 'compare'" />
      <AnnotatorManager v-else-if="activeMenu === 'annotators'" />
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api.js'
import BankManager from './admin/BankManager.vue'
import BatchList from './admin/BatchList.vue'
import BatchDetail from './admin/BatchDetail.vue'
import VersionCompare from './admin/VersionCompare.vue'
import AnnotatorManager from './admin/AnnotatorManager.vue'

const activeMenu = ref('batches')
const currentBatch = ref(null)
const annotatorList = ref([])

onMounted(async () => {
  await loadAnnotators()
})

async function loadBanks() {}

async function loadAnnotators() {
  const { data } = await api.get('/users/')
  annotatorList.value = data.filter(u => u.role.includes('annotator'))
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
}

function handleMenuSelect(key) {
  activeMenu.value = key
}
</script>
