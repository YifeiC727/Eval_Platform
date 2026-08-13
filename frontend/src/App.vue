<template>
  <el-config-provider :locale="zhCn">
    <div id="app-root">
      <el-container v-if="isLoggedIn" style="min-height: 100vh">
        <el-header style="background: #2c3e50; display: flex; align-items: center; justify-content: space-between;">
          <div style="display: flex; align-items: center; gap: 24px;">
            <span style="color: #fff; font-size: 18px; font-weight: 600;">V6 T2V 评测平台</span>
            <el-menu mode="horizontal" :default-active="$route.path" router :ellipsis="false"
              background-color="#2c3e50" text-color="#bdc3c7" active-text-color="#fff"
              style="border: none;">
              <el-menu-item v-if="user.role !== 'admin'" index="/tasks">我的任务</el-menu-item>
              <el-menu-item v-if="user.role === 'admin' || user.role === 'lead'" index="/dashboard">结果看板</el-menu-item>
              <el-menu-item v-if="user.role === 'admin'" index="/admin">管理后台</el-menu-item>
            </el-menu>
          </div>
          <div style="display: flex; align-items: center; gap: 12px;">
            <el-tag :type="user.role === 'admin' ? 'danger' : 'info'" size="small">{{ user.role }}</el-tag>
            <span style="color: #ecf0f1;">{{ user.display_name || user.username }}</span>
            <el-button size="small" @click="logout">退出</el-button>
          </div>
        </el-header>
        <el-main style="padding: 20px; background: #f5f7fa;">
          <router-view />
        </el-main>
      </el-container>
      <router-view v-else />
    </div>
  </el-config-provider>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

const router = useRouter()
const route = useRoute()

const user = ref(JSON.parse(sessionStorage.getItem('user') || '{}'))
const isLoggedIn = computed(() => !!user.value.id)

watch(() => route.path, () => {
  user.value = JSON.parse(sessionStorage.getItem('user') || '{}')
})

function logout() {
  sessionStorage.removeItem('user')
  user.value = {}
  router.push('/login')
}
</script>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
</style>
