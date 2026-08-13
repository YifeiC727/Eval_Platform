import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use(config => {
  const user = JSON.parse(sessionStorage.getItem('user') || '{}')
  if (user.id) {
    config.headers['X-User-Id'] = user.id
  }
  return config
})

export default api
