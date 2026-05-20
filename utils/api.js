const app = getApp()

const USER_STORAGE_KEY = 'receipt_ocr_user'
const TOKEN_STORAGE_KEY = 'receipt_ocr_access_token'
const DEFAULT_USER_ID = '1'

function baseUrl() {
  return (app.globalData && app.globalData.apiBaseUrl) || 'http://127.0.0.1:8000'
}

function getAccessToken() {
  return wx.getStorageSync(TOKEN_STORAGE_KEY) || DEFAULT_USER_ID
}

function getCurrentUser() {
  return wx.getStorageSync(USER_STORAGE_KEY) || null
}

function setLoginSession(loginResult) {
  const token = String((loginResult && loginResult.access_token) || DEFAULT_USER_ID)
  wx.setStorageSync(TOKEN_STORAGE_KEY, token)
  if (loginResult && loginResult.user) {
    wx.setStorageSync(USER_STORAGE_KEY, loginResult.user)
  }
  return loginResult
}

function normalizeError(error) {
  if (!error) return '请求失败'
  if (typeof error === 'string') return error
  if (error.errMsg) return error.errMsg
  if (error.detail) {
    if (Array.isArray(error.detail)) {
      return error.detail.map((item) => {
        if (typeof item === 'string') return item
        if (item && item.msg) {
          const loc = Array.isArray(item.loc) ? item.loc.join('.') : ''
          return loc ? `${loc}: ${item.msg}` : item.msg
        }
        try {
          return JSON.stringify(item)
        } catch (ignore) {
          return String(item)
        }
      }).join('\n')
    }
    return String(error.detail)
  }
  if (error.message) return error.message
  return '请求失败'
}

function parseResponse(res) {
  const statusCode = res.statusCode || 0
  if (statusCode >= 200 && statusCode < 300) {
    return res.data
  }
  const message = normalizeError(res.data) || `请求失败：${statusCode}`
  const error = new Error(message)
  error.statusCode = statusCode
  throw error
}

function request(options) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl()}${options.url}`,
      method: options.method || 'GET',
      data: options.data,
      header: Object.assign({
        'X-User-Id': getAccessToken(),
        'content-type': 'application/json'
      }, options.header || {}),
      success(res) {
        try {
          resolve(parseResponse(res))
        } catch (error) {
          reject(error)
        }
      },
      fail(error) {
        reject(new Error(normalizeError(error)))
      }
    })
  })
}

function wxLoginCode() {
  return new Promise((resolve, reject) => {
    wx.login({
      success(res) {
        if (res.code) {
          resolve(res.code)
        } else {
          reject(new Error('微信登录未返回 code'))
        }
      },
      fail(error) {
        reject(new Error(normalizeError(error)))
      }
    })
  })
}

async function wechatLogin(profile) {
  const code = await wxLoginCode()
  const result = await request({
    url: '/api/v1/auth/wechat-login',
    method: 'POST',
    data: {
      code,
      display_name: profile && profile.display_name ? profile.display_name : undefined,
      phone: profile && profile.phone ? profile.phone : undefined
    }
  })
  return setLoginSession(result)
}

async function ensureWechatLogin() {
  const existingToken = wx.getStorageSync(TOKEN_STORAGE_KEY)
  if (existingToken) {
    return {
      access_token: existingToken,
      user: getCurrentUser()
    }
  }
  try {
    return await wechatLogin()
  } catch (error) {
    wx.setStorageSync(TOKEN_STORAGE_KEY, DEFAULT_USER_ID)
    return {
      access_token: DEFAULT_USER_ID,
      user: null,
      fallback: true,
      error: error.message
    }
  }
}

function uploadBatch({ title, files }) {
  return new Promise((resolve, reject) => {
    if (!files || !files.length) {
      reject(new Error('请先选择票据照片'))
      return
    }

    const uploadFiles = files.map((file) => ({
      name: 'files',
      filePath: file.tempFilePath || file.path
    }))

    const uploadOptions = {
      url: `${baseUrl()}/api/v1/batches`,
      formData: {
        title: title || ''
      },
      header: {
        'X-User-Id': getAccessToken()
      },
      success(res) {
        try {
          const data = typeof res.data === 'string' ? JSON.parse(res.data || '{}') : res.data
          resolve(parseResponse({
            statusCode: res.statusCode,
            data
          }))
        } catch (error) {
          reject(error)
        }
      },
      fail(error) {
        reject(new Error(`${normalizeError(error)}。当前环境不支持 uploadFile 多文件参数时会自动尝试 multipart 兼容上传。`))
      }
    }

    if (uploadFiles.length === 1) {
      uploadOptions.name = 'files'
      uploadOptions.filePath = uploadFiles[0].filePath
    } else {
      uploadOptions.files = uploadFiles
    }

    wx.uploadFile(uploadOptions)
  })
}

function utf8Bytes(text) {
  const bytes = []
  for (let index = 0; index < text.length; index += 1) {
    let code = text.charCodeAt(index)
    if (code >= 0xd800 && code <= 0xdbff && index + 1 < text.length) {
      const next = text.charCodeAt(index + 1)
      if (next >= 0xdc00 && next <= 0xdfff) {
        code = 0x10000 + ((code - 0xd800) << 10) + (next - 0xdc00)
        index += 1
      }
    }
    if (code < 0x80) {
      bytes.push(code)
    } else if (code < 0x800) {
      bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f))
    } else if (code < 0x10000) {
      bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f))
    } else {
      bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f))
    }
  }
  return new Uint8Array(bytes)
}

function readFileArrayBuffer(filePath) {
  return new Promise((resolve, reject) => {
    wx.getFileSystemManager().readFile({
      filePath,
      success(res) {
        resolve(res.data)
      },
      fail(error) {
        reject(new Error(normalizeError(error)))
      }
    })
  })
}

function fileNameFromPath(filePath, index) {
  const parts = String(filePath || '').split(/[\\/]/)
  return parts[parts.length - 1] || `receipt-${index + 1}.jpg`
}

function concatUint8Arrays(chunks) {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const result = new Uint8Array(total)
  let offset = 0
  chunks.forEach((chunk) => {
    result.set(chunk, offset)
    offset += chunk.length
  })
  return result.buffer
}

async function uploadBatchMultipart({ title, files }) {
  if (!files || !files.length) {
    throw new Error('请先选择票据照片')
  }

  const boundary = `----receipt-miniapp-${Date.now()}-${Math.random().toString(16).slice(2)}`
  const chunks = []
  chunks.push(utf8Bytes(`--${boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n${title || ''}\r\n`))

  for (let index = 0; index < files.length; index += 1) {
    const filePath = files[index].tempFilePath || files[index].path
    const filename = fileNameFromPath(filePath, index)
    const fileBuffer = await readFileArrayBuffer(filePath)
    chunks.push(utf8Bytes(`--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="${filename}"\r\nContent-Type: image/jpeg\r\n\r\n`))
    chunks.push(new Uint8Array(fileBuffer))
    chunks.push(utf8Bytes('\r\n'))
  }

  chunks.push(utf8Bytes(`--${boundary}--\r\n`))

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl()}/api/v1/batches`,
      method: 'POST',
      data: concatUint8Arrays(chunks),
      header: {
        'X-User-Id': getAccessToken(),
        'content-type': `multipart/form-data; boundary=${boundary}`
      },
      success(res) {
        try {
          resolve(parseResponse(res))
        } catch (error) {
          reject(error)
        }
      },
      fail(error) {
        reject(new Error(normalizeError(error)))
      }
    })
  })
}

function uploadReceipt(file) {
  return new Promise((resolve, reject) => {
    const filePath = file.tempFilePath || file.path
    if (!filePath) {
      reject(new Error('图片路径无效'))
      return
    }

    wx.uploadFile({
      url: `${baseUrl()}/api/v1/receipts`,
      name: 'file',
      filePath,
      header: {
        'X-User-Id': getAccessToken()
      },
      success(res) {
        try {
          const data = typeof res.data === 'string' ? JSON.parse(res.data || '{}') : res.data
          resolve(parseResponse({
            statusCode: res.statusCode,
            data
          }))
        } catch (error) {
          reject(error)
        }
      },
      fail(error) {
        reject(new Error(normalizeError(error)))
      }
    })
  })
}

function createManualReceipt(payload) {
  return request({
    url: '/api/v1/receipts/manual',
    method: 'POST',
    data: payload
  })
}

async function uploadReceiptsSequentially(files, onProgress) {
  const receipts = []
  for (let index = 0; index < files.length; index += 1) {
    if (onProgress) onProgress(index + 1, files.length)
    const receipt = await uploadReceipt(files[index])
    receipts.push(receipt)
  }
  return receipts
}

function getBatch(batchId) {
  return request({ url: `/api/v1/batches/${batchId}` })
}

function listBatches(options) {
  const limit = options && options.limit ? options.limit : 20
  const offset = options && options.offset ? options.offset : 0
  const status = options && options.status ? `&status=${encodeURIComponent(options.status)}` : ''
  return request({ url: `/api/v1/batches?limit=${limit}&offset=${offset}${status}` })
}

function listReceipts(options) {
  const query = Object.assign({
    limit: 20,
    offset: 0
  }, options || {})
  const parts = []
  Object.keys(query).forEach((key) => {
    const value = query[key]
    if (value === '' || value === null || value === undefined || value === false) return
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
  })
  return request({ url: `/api/v1/receipts?${parts.join('&')}` })
}

function deleteReceipt(receiptId) {
  return request({
    url: `/api/v1/receipts/${receiptId}`,
    method: 'DELETE'
  })
}

function getReceipt(receiptId) {
  return request({ url: `/api/v1/receipts/${receiptId}` })
}

function updateReviewFields(receiptId, fields, summary) {
  return request({
    url: `/api/v1/receipts/${receiptId}/review-fields`,
    method: 'PATCH',
    data: {
      fields,
      summary: summary || null
    }
  })
}

function addReviewItem(receiptId, item) {
  return request({
    url: `/api/v1/receipts/${receiptId}/review-items`,
    method: 'POST',
    data: item
  })
}

function updateReviewItem(receiptId, itemIndex, item) {
  return request({
    url: `/api/v1/receipts/${receiptId}/review-items/${itemIndex}`,
    method: 'PATCH',
    data: item
  })
}

function deleteReviewItem(receiptId, itemIndex) {
  return request({
    url: `/api/v1/receipts/${receiptId}/review-items/${itemIndex}`,
    method: 'DELETE'
  })
}

function confirmReceipt(receiptId, finalJson) {
  return request({
    url: `/api/v1/receipts/${receiptId}/confirm`,
    method: 'POST',
    data: {
      final_json: finalJson
    }
  })
}

function retryReceipt(receiptId) {
  return request({
    url: `/api/v1/receipts/${receiptId}/retry`,
    method: 'POST'
  })
}

function receiptImageUrl(receiptId) {
  return `${baseUrl()}/api/v1/receipts/${receiptId}/image`
}

function downloadReceiptImage(receiptId) {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: receiptImageUrl(receiptId),
      header: {
        'X-User-Id': getAccessToken()
      },
      success(res) {
        if ((res.statusCode || 0) >= 200 && res.statusCode < 300) {
          resolve(res.tempFilePath)
          return
        }
        reject(new Error(`原图下载失败：${res.statusCode || '未知状态'}`))
      },
      fail(error) {
        reject(new Error(normalizeError(error)))
      }
    })
  })
}

function exportBatch(batchId) {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: `${baseUrl()}/api/v1/batches/${batchId}/export.xlsx`,
      header: {
        'X-User-Id': getAccessToken()
      },
      success(res) {
        if ((res.statusCode || 0) >= 200 && res.statusCode < 300) {
          resolve(res.tempFilePath)
          return
        }
        reject(new Error(`导出失败：${res.statusCode || '未知状态'}`))
      },
      fail(error) {
        reject(new Error(normalizeError(error)))
      }
    })
  })
}

function exportAllReceipts() {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: `${baseUrl()}/api/v1/receipts/export.xlsx`,
      header: {
        'X-User-Id': getAccessToken()
      },
      success(res) {
        if ((res.statusCode || 0) >= 200 && res.statusCode < 300) {
          resolve(res.tempFilePath)
          return
        }
        reject(new Error(`导出失败：${res.statusCode || '未知状态'}`))
      },
      fail(error) {
        reject(new Error(normalizeError(error)))
      }
    })
  })
}

module.exports = {
  baseUrl,
  getAccessToken,
  getCurrentUser,
  ensureWechatLogin,
  wechatLogin,
  request,
  uploadBatch,
  uploadBatchMultipart,
  uploadReceipt,
  createManualReceipt,
  uploadReceiptsSequentially,
  getBatch,
  listBatches,
  listReceipts,
  deleteReceipt,
  getReceipt,
  updateReviewFields,
  addReviewItem,
  updateReviewItem,
  deleteReviewItem,
  confirmReceipt,
  retryReceipt,
  receiptImageUrl,
  downloadReceiptImage,
  exportBatch,
  exportAllReceipts
}
