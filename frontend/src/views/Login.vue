<template>
  <div style="min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
    <el-card style="width: 400px;" shadow="always">
      <template #header>
        <h2 style="margin: 0; text-align: center;">V6 T2V 评测平台</h2>
        <p style="text-align: center; color: #999; margin: 8px 0 0;">标注员工作台</p>
      </template>
      <el-form @submit.prevent="handleLogin" label-position="top">
        <el-form-item label="ERP工号 / 用户名">
          <el-input v-model="username" placeholder="输入ERP工号或用户名" size="large" />
        </el-form-item>
        <el-form-item label="密码（如已设置则必填）">
          <el-input v-model="password" type="password" placeholder="未设置密码可留空" size="large" show-password />
        </el-form-item>
        <el-form-item label="登录身份">
          <el-select v-model="role" size="large" style="width: 100%;">
            <el-option label="标注员" value="annotator" />
            <el-option label="组长" value="lead" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%;" @click="handleLogin" :loading="loading">
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api.js'

const router = useRouter()
const username = ref('')
const password = ref('')
const role = ref('annotator')
const loading = ref(false)

async function handleLogin() {
  if (!username.value.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  loading.value = true
  try {
    const { data } = await api.post('/users/login', {
      username: username.value.trim(),
      password: password.value || null,
      display_name: username.value.trim(),
      role: role.value,
    })
    sessionStorage.setItem('user', JSON.stringify(data))
    ElMessage.success(`欢迎, ${data.display_name}`)
    const target = data.role === 'admin' ? '/admin' : data.role === 'lead' ? '/dashboard' : '/tasks'
    router.push(target)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
