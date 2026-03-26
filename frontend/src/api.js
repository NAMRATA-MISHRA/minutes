const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function uploadAudio(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE_URL}/upload-audio`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error('Failed to upload audio')
  }

  return response.json()
}

export async function generateNotes({ file, fileUrl }) {
  const formData = new FormData()
  if (file) {
    formData.append('file', file)
  }
  if (fileUrl) {
    formData.append('file_url', fileUrl)
  }

  const response = await fetch(`${API_BASE_URL}/generate-notes`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || 'Failed to generate notes')
  }

  return response.json()
}

export async function getMeetings(limit = 50) {
  const response = await fetch(`${API_BASE_URL}/meetings?limit=${limit}`)
  if (!response.ok) {
    throw new Error('Failed to fetch meeting history')
  }
  return response.json()
}

export { API_BASE_URL }
