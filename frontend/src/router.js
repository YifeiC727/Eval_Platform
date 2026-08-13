import { createRouter, createWebHistory } from 'vue-router'
import Login from './views/Login.vue'
import TaskList from './views/TaskList.vue'
import Annotate from './views/Annotate.vue'
import Dashboard from './views/Dashboard.vue'
import Admin from './views/Admin.vue'

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: Login },
  { path: '/tasks', component: TaskList },
  { path: '/annotate/:assignmentId', component: Annotate, props: true },
  { path: '/dashboard', component: Dashboard },
  { path: '/admin', component: Admin },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
  if (to.path !== '/login' && !user.id) {
    next('/login')
  } else {
    next()
  }
})

export default router
