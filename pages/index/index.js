const api = require('../../utils/api')
const fmt = require('../../utils/format')

Page({
  data: {
    receipts: [],
    selectedReceiptIds: [],
    loadingReceipts: false,
    exportingSelected: false,
    uploading: false,
    loginLoading: false,
    baseUrl: api.baseUrl(),
    userId: api.getAccessToken(),
    userName: ''
  },

  onLoad() {
    this.ensureLogin()
  },

  onShow() {
    this.loadRecentReceipts()
  },

  async ensureLogin() {
    this.setData({ loginLoading: true })
    const result = await api.ensureWechatLogin()
    this.setData({
      loginLoading: false,
      userId: result.access_token || api.getAccessToken(),
      userName: result.user && result.user.display_name ? result.user.display_name : ''
    })
    this.loadRecentReceipts()
  },

  normalizeList(result, keys) {
    if (Array.isArray(result)) return result
    for (let index = 0; index < keys.length; index += 1) {
      const value = result && result[keys[index]]
      if (Array.isArray(value)) return value
    }
    return []
  },

  async loadRecentReceipts() {
    if (this.data.loadingReceipts) return
    this.setData({ loadingReceipts: true })
    try {
      const result = await api.listReceipts({ limit: 20, offset: 0 })
      const list = this.normalizeList(result, ['items', 'receipts', 'data'])
      const details = await Promise.all(list.map((receipt) => (
        api.getReceipt(receipt.id).catch(() => null)
      )))
      const selectedMap = {}
      this.data.selectedReceiptIds.forEach((id) => {
        selectedMap[String(id)] = true
      })
      const receipts = list.map((receipt, index) => {
        const styleText = receipt.display_item || '-'
        const descText = this.buildCompactDesc(receipt, details[index])
        return {
          ...receipt,
          styleText,
          descText,
          supplierText: receipt.merchant_name || '-',
          statusText: receipt.status === 'confirmed' ? '修改' : fmt.statusText(receipt.status),
          tone: fmt.statusTone(receipt.status),
          selected: Boolean(selectedMap[String(receipt.id)])
        }
      })
      this.setData({
        receipts,
        selectedReceiptIds: receipts.filter((receipt) => receipt.selected).map((receipt) => String(receipt.id)),
        loadingReceipts: false
      })
    } catch (error) {
      this.setData({ loadingReceipts: false })
      wx.showModal({
        title: '账单加载失败',
        content: error.message || '请确认后端账单列表接口可用。',
        showCancel: false
      })
    }
  },

  truncateText(text, limit) {
    const value = text || '-'
    return value.length > limit ? `${value.slice(0, limit - 1)}…` : value
  },

  buildCompactDesc(receipt, detail) {
    const source = detail && (detail.final_json || detail.corrected_json || detail.structured_json)
    const items = source && Array.isArray(source.items) ? source.items : []
    const item = items[0] || {}
    const parts = [
      item.style_no || item.product_name || receipt.display_item || '-',
      item.color || '',
      item.size || ''
    ].filter(Boolean)
    return this.truncateText(parts.join(' '), 30)
  },

  openReceiptsPage() {
    wx.navigateTo({
      url: '/pages/receipts/receipts'
    })
  },

  openReceipt(event) {
    const receiptId = event.currentTarget.dataset.id
    wx.navigateTo({
      url: `/pages/review/review?receipt_id=${receiptId}`
    })
  },

  toggleReceiptSelect(event) {
    const receiptId = String(event.currentTarget.dataset.id)
    const selectedMap = {}
    this.data.selectedReceiptIds.forEach((id) => {
      selectedMap[String(id)] = true
    })
    if (selectedMap[receiptId]) {
      delete selectedMap[receiptId]
    } else {
      selectedMap[receiptId] = true
    }
    const selectedReceiptIds = Object.keys(selectedMap)
    this.setData({
      selectedReceiptIds,
      receipts: this.data.receipts.map((receipt) => ({
        ...receipt,
        selected: Boolean(selectedMap[String(receipt.id)])
      }))
    })
  },

  async exportSelectedReceipts() {
    if (this.data.exportingSelected) return
    const selectedIds = this.data.selectedReceiptIds
    if (!selectedIds.length) {
      wx.showToast({ title: '请先选择账单', icon: 'none' })
      return
    }
    this.setData({ exportingSelected: true })
    wx.showLoading({ title: '导出中' })
    try {
      const tempFilePath = await api.exportSelectedReceipts(selectedIds)
      wx.hideLoading()
      this.setData({ exportingSelected: false })
      wx.openDocument({
        filePath: tempFilePath,
        fileType: 'xlsx',
        showMenu: true,
        fail: () => {
          wx.showModal({
            title: '已导出',
            content: `Excel 文件已生成：${tempFilePath}`,
            showCancel: false
          })
        }
      })
    } catch (error) {
      wx.hideLoading()
      this.setData({ exportingSelected: false })
      wx.showModal({
        title: '导出失败',
        content: error.message || '请稍后重试。',
        showCancel: false
      })
    }
  },

  uploadReceiptImages() {
    if (this.data.uploading) return
    wx.chooseMedia({
      count: 9,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const files = (res.tempFiles || []).map((file) => ({
          tempFilePath: file.tempFilePath,
          size: file.size
        }))
        if (!files.length) return
        this.uploadFiles(files)
      }
    })
  },

  async uploadFiles(files) {
    this.setData({ uploading: true })
    wx.showLoading({ title: '上传中' })
    try {
      if (files.length > 1) {
        try {
          wx.showLoading({ title: '创建批次' })
          const batch = await api.uploadBatchMultipart({
            title: '拿货账单',
            files
          })
          wx.hideLoading()
          this.setData({ uploading: false })
          wx.navigateTo({
            url: `/pages/batch/batch?batch_id=${batch.id}`
          })
        } catch (batchError) {
          const receipts = await api.uploadReceiptsSequentially(files, (current, total) => {
            wx.showLoading({ title: `上传 ${current}/${total}` })
          })
          const receiptIds = receipts.map((receipt) => receipt.id).join(',')
          wx.hideLoading()
          this.setData({ uploading: false })
          wx.navigateTo({
            url: `/pages/batch/batch?receipt_ids=${receiptIds}&title=${encodeURIComponent('拿货账单')}`
          })
        }
        return
      }

      const batch = await api.uploadBatch({
        title: '拿货账单',
        files
      })
      wx.hideLoading()
      this.setData({ uploading: false })
      wx.navigateTo({
        url: `/pages/batch/batch?batch_id=${batch.id}`
      })
    } catch (error) {
      wx.hideLoading()
      this.setData({ uploading: false })
      wx.showModal({
        title: '上传失败',
        content: error.message || '请确认后端服务已启动，并在开发者工具关闭合法域名校验。',
        showCancel: false
      })
    }
  }
})
