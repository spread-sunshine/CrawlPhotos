const API_BASE = ''

function request(url, options = {}) {
  const config = {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  }

  return fetch(API_BASE + url, config).then((res) => {
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`)
    }
    if (url.includes('/metrics')) return res.text()
    return res.json()
  })
}

export const api = {
  health() {
    return request('/health')
  },

  listPhotos(params = {}) {
    const query = new URLSearchParams(params).toString()
    return request(`/api/v1/photos?${query}`)
  },

  getPhotoDetail(photoId) {
    return request(`/api/v1/photos/${photoId}`)
  },

  getPhotoUrl(photoId, size = 'original') {
    return `/api/v1/photos/${photoId}/file?size=${size}`
  },

  getCalendarData(year, month) {
    return request(`/api/v1/photos/calendar/${year}/${month}`)
  },

  getStats() {
    return request('/api/v1/stats')
  },

  getStatus() {
    return request('/api/v1/status')
  },

  triggerTask(options = {}) {
    return request('/api/v1/tasks/trigger', {
      method: 'POST',
      body: JSON.stringify({
        trigger_type: 'manual',
        options,
      }),
    })
  },

  getRecentTasks(limit = 10) {
    return request(`/api/v1/tasks/recent?limit=${limit}`)
  },

  // Review pool
  listReviews(status, limit = 20) {
    let url = `/api/v1/review?limit=${limit}`
    if (status) url += `&status=${status}`
    return request(url)
  },

  approveReview(id, note = '') {
    return request(`/api/v1/review/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ reviewer: 'admin', note }),
    })
  },

  rejectReview(id, note = '') {
    return request(`/api/v1/review/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reviewer: 'admin', note }),
    })
  },

  getReviewSummary() {
    return request('/api/v1/review/summary')
  },

  // Metrics
  getMetricsSnapshot() {
    return request('/api/v1/metrics/snapshot')
  },
}
