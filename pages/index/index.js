const api = require('../../utils/api')
const fmt = require('../../utils/format')

Page({
  data: {
    title: '',
    files: [],
    batches: [],
    receipts: [],
    activeHistoryTab: 'batches',
    receiptFilters: {
      status: '',
      source_type: '',
      start_date: '',
      end_date: '',
      merchant_name: '',
      keyword: '',
      include_deleted: false
    },
    historyLoading: false,
    uploading: false,
    loginLoading: false,
    exporting: false,
    baseUrl: api.baseUrl(),
    userId: api.getAccessToken(),
    userName: ''
  },

  onLoad() {
    this.ensureLogin()
  },

  onShow() {
    this.loadHistory()
  },

  async ensureLogin() {
    this.setData({ loginLoading: true })
    const result = await api.ensureWechatLogin()
    this.setData({
      loginLoading: false,
      userId: result.access_token || api.getAccessToken(),
      userName: result.user && result.user.display_name ? result.user.display_name : ''
    })
    this.loadHistory()
  },

  async relogin() {
    this.setData({ loginLoading: true })
    try {
      const result = await api.wechatLogin()
      this.setData({
        loginLoading: false,
        userId: result.access_token,
        userName: result.user && result.user.display_name ? result.user.display_name : ''
      })
      wx.showToast({ title: '登录成功', icon: 'success' })
      this.loadHistory()
    } catch (error) {
      this.setData({ loginLoading: false })
      wx.showModal({
        title: '登录失败',
        content: error.message || '微信登录接口不可用，已保留本地默认用户。',
        showCancel: false
      })
    }
  },

  normalizeList(result, keys) {
    if (Array.isArray(result)) return result
    for (let index = 0; index < keys.length; index += 1) {
      const value = result && result[keys[index]]
      if (Array.isArray(value)) return value
    }
    return []
  },

  async loadHistory() {
    if (this.data.historyLoading) return
    this.setData({ historyLoading: true })
    try {
      const results = await Promise.all([
        api.listBatches({ limit: 20, offset: 0 }),
        api.listReceipts(Object.assign({
          limit: 20,
          offset: 0
        }, this.data.receiptFilters))
      ])
      const batches = this.normalizeList(results[0], ['items', 'batches', 'data']).map((batch) => ({
        ...batch,
        statusText: fmt.statusText(batch.status),
        tone: fmt.statusTone(batch.status),
        progressPercent: batch.progress_percent || 0
      }))
      const receipts = this.normalizeList(results[1], ['items', 'receipts', 'data']).map((receipt) => ({
        ...receipt,
        statusText: fmt.statusText(receipt.status),
        tone: fmt.statusTone(receipt.status),
        titleText: receipt.merchant_name || receipt.original_filename || '未命名账单',
        metaText: `${receipt.order_date || ''} · 数量 ${receipt.total_quantity || 0} · 金额 ${receipt.total_amount || 0}`
      }))
      this.setData({
        batches,
        receipts,
        historyLoading: false
      })
    } catch (error) {
      this.setData({ historyLoading: false })
      wx.showModal({
        title: '列表加载失败',
        content: error.message || '请确认后端列表接口可用。',
        showCancel: false
      })
    }
  },

  switchHistoryTab(event) {
    this.setData({
      activeHistoryTab: event.currentTarget.dataset.tab
    })
  },

  onFilterInput(event) {
    const field = event.currentTarget.dataset.field
    this.setData({
      [`receiptFilters.${field}`]: event.detail.value
    })
  },

  onStatusFilterChange(event) {
    const values = ['', 'ready_for_review', 'need_review', 'confirmed', 'failed', 'deleted']
    const status = values[Number(event.detail.value)] || ''
    this.setData({
      'receiptFilters.status': status,
      'receiptFilters.include_deleted': status === 'deleted'
    })
    this.loadHistory()
  },

  onSourceFilterChange(event) {
    const values = ['', 'image', 'manual']
    this.setData({
      'receiptFilters.source_type': values[Number(event.detail.value)] || ''
    })
    this.loadHistory()
  },

  applyReceiptFilters() {
    this.loadHistory()
  },

  resetReceiptFilters() {
    this.setData({
      receiptFilters: {
        status: '',
        source_type: '',
        start_date: '',
        end_date: '',
        merchant_name: '',
        keyword: '',
        include_deleted: false
      }
    })
    this.loadHistory()
  },

  openBatch(event) {
    const batchId = event.currentTarget.dataset.id
    wx.navigateTo({
      url: `/pages/batch/batch?batch_id=${batchId}`
    })
  },

  openReceipt(event) {
    const receiptId = event.currentTarget.dataset.id
    wx.navigateTo({
      url: `/pages/review/review?receipt_id=${receiptId}`
    })
  },

  deleteReceipt(event) {
    const receiptId = event.currentTarget.dataset.id
    wx.showModal({
      title: '删除账单',
      content: '删除后默认列表、详情和导出不再显示该账单。',
      confirmText: '删除',
      confirmColor: '#b42318',
      success: async (res) => {
        if (!res.confirm) return
        wx.showLoading({ title: '删除中' })
        try {
          await api.deleteReceipt(receiptId)
          wx.hideLoading()
          wx.showToast({ title: '已删除', icon: 'success' })
          this.loadHistory()
        } catch (error) {
          wx.hideLoading()
          wx.showModal({
            title: '删除失败',
            content: error.message || '请稍后重试。',
            showCancel: false
          })
        }
      }
    })
  },

  openManual() {
    wx.navigateTo({
      url: '/pages/manual/manual'
    })
  },

  onTitleInput(event) {
    this.setData({
      title: event.detail.value
    })
  },

  chooseImages() {
    wx.chooseMedia({
      count: 9,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const selected = (res.tempFiles || []).map((file) => ({
          tempFilePath: file.tempFilePath,
          size: file.size
        }))
        this.setData({
          files: this.data.files.concat(selected)
        })
      }
    })
  },

  removeImage(event) {
    const index = event.currentTarget.dataset.index
    const files = this.data.files.slice()
    files.splice(index, 1)
    this.setData({ files })
  },

  previewImage(event) {
    const index = event.currentTarget.dataset.index
    wx.previewImage({
      current: this.data.files[index].tempFilePath,
      urls: this.data.files.map((file) => file.tempFilePath)
    })
  },

  async upload() {
    if (!this.data.files.length || this.data.uploading) return
    this.setData({ uploading: true })
    wx.showLoading({ title: '上传中' })
    try {
      if (this.data.files.length > 1) {
        const title = this.data.title || '未命名批次'
        try {
          wx.showLoading({ title: '创建批次' })
          const batch = await api.uploadBatchMultipart({
            title,
            files: this.data.files
          })
          wx.hideLoading()
          this.setData({
            uploading: false,
            files: [],
            title: ''
          })
          wx.navigateTo({
            url: `/pages/batch/batch?batch_id=${batch.id}`
          })
        } catch (batchError) {
          const receipts = await api.uploadReceiptsSequentially(this.data.files, (current, total) => {
            wx.showLoading({ title: `上传 ${current}/${total}` })
          })
          const receiptIds = receipts.map((receipt) => receipt.id).join(',')
          wx.hideLoading()
          this.setData({
            uploading: false,
            files: [],
            title: ''
          })
          wx.navigateTo({
            url: `/pages/batch/batch?receipt_ids=${receiptIds}&title=${encodeURIComponent(title)}`
          })
        }
        return
      }

      const batch = await api.uploadBatch({
        title: this.data.title,
        files: this.data.files
      })
      wx.hideLoading()
      this.setData({
        uploading: false,
        files: [],
        title: ''
      })
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
  },

  async exportAll() {
    if (this.data.exporting) return
    this.setData({ exporting: true })
    wx.showLoading({ title: '导出中' })
    try {
      const tempFilePath = await api.exportAllReceipts()
      wx.hideLoading()
      this.setData({ exporting: false })
      wx.openDocument({
        filePath: tempFilePath,
        fileType: 'xlsx',
        showMenu: true,
        fail: () => {
          wx.showModal({
            title: '已下载',
            content: `文件已下载到临时路径：${tempFilePath}`,
            showCancel: false
          })
        }
      })
    } catch (error) {
      wx.hideLoading()
      this.setData({ exporting: false })
      wx.showModal({
        title: '导出失败',
        content: error.message || '暂无可导出的票据。',
        showCancel: false
      })
    }
  }
})
