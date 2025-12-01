import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 60000, // 圖片處理可能較慢，設定 60 秒
  headers: {
    'Content-Type': 'application/json',
  },
});

// 請求攔截器
apiClient.interceptors.request.use(
  (config) => {
    // 可以在這裡添加 auth token 等
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 回應攔截器
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // 統一錯誤處理
    const message = error.response?.data?.message || error.message || '發生未知錯誤';
    console.error('API Error:', message);
    return Promise.reject(error);
  }
);

export default apiClient;
