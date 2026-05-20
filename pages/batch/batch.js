const api = require('../../utils/api')
const fmt = require('../../utils/format')

Page({
  data: {
    batchId: '',
    receiptIds: [],
    localMode: false,
    batch: {},
    receipts: [],
    countsList: [],
    batchStatusText: '加载中',
    batchTone: '',
    progressPercent: 0,
    canExport: false,
    loading: false,
    exporting: false
  },

  pollTimer: null,
  autoReviewPrompted: false,

  onLoad(options) {
    const receiptIds = (options.receipt_ids || '')
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean)
    this.setData({
      batchId: options.batch_id || options.id || '',
      receiptIds,
      localMode: receiptIds.length > 0,
      batch: receiptIds.length > 0 ? {
        id: 'local',
        title: decodeURIComponent(options.title || '临时批次'),
        status: 'processing',
        counts: {},
        progress_percent: 0
      } : {}
    })
    this.loadBatch()
  },

  onShow() {
    if (this.data.batchId || this.data.localMode) this.loadBatch()
  },

  onUnload() {
    this.clearPoll()
  },

  clearPoll() {
    if (this.pollTimer) {
      clearTimeout(this.pollTimer)
      this.pollTimer = null
    }
  },

  async loadBatch() {
    if (this.data.localMode) {
      this.loadLocalReceipts()
      return
    }
    if (!this.data.batchId) return
    this.setData({ loading: true })
    try {
      const batch = await api.getBatch(this.data.batchId)
      const receipts = (batch.receipts || []).map((receipt) => ({
        ...receipt,
        statusText: fmt.statusText(receipt.status),
        tone: fmt.statusTone(receipt.status)
      }))
      const canExport = receipts.some((receipt) => receipt.status === 'ready_for_review' || receipt.status === 'need_review' || receipt.status === 'confirmed')
      this.setData({
        batch,
        receipts,
        countsList: fmt.progressCounts(batch),
        batchStatusText: fmt.statusText(batch.status),
        batchTone: fmt.statusTone(batch.status),
        progressPercent: batch.progress_percent || 0,
        canExport,
        loading: false
      })
      this.schedulePoll(batch, receipts)
      this.promptReviewWhenComplete(batch, receipts)
    } catch (error) {
      this.setData({ loading: false })
      wx.showModal({
        title: '加载失败',
        content: error.message || '请确认后端服务已启动。',
        showCancel: false
      })
    }
  },

  async loadLocalReceipts() {
    if (!this.data.receiptIds.length) return
    this.setData({ loading: true })
    try {
      const fullReceipts = await Promise.all(this.data.receiptIds.map((id) => api.getReceipt(id)))
      const counts = {}
      fullReceipts.forEach((receipt) => {
        counts[receipt.status] = (counts[receipt.status] || 0) + 1
      })
      const receipts = fullReceipts.map((receipt) => ({
        receipt_id: receipt.id,
        filename: receipt.original_filename,
        status: receipt.status,
        duplicate: receipt.duplicate_status !== 'unique',
        duplicate_of_receipt_id: receipt.duplicate_of_receipt_id,
        statusText: fmt.statusText(receipt.status),
        tone: fmt.statusTone(receipt.status)
      }))
      const completedCount = receipts.filter((receipt) => fmt.isDoneStatus(receipt.status)).length
      const progressPercent = receipts.length ? Math.round((completedCount / receipts.length) * 100) : 0
      const allDone = progressPercent >= 100
      const anyFailed = receipts.some((receipt) => receipt.status === 'failed')
      const batchStatus = allDone ? (anyFailed ? 'partial_failed' : 'ready_for_review') : 'processing'
      const canExport = receipts.some((receipt) => receipt.status === 'ready_for_review' || receipt.status === 'need_review' || receipt.status === 'confirmed')
      const batch = Object.assign({}, this.data.batch, {
        status: batchStatus,
        counts,
        progress_percent: progressPercent,
        processing_count: receipts.filter((receipt) => fmt.isActiveStatus(receipt.status)).length,
        ready_for_review_count: receipts.filter((receipt) => receipt.status === 'ready_for_review').length,
        need_review_count: receipts.filter((receipt) => receipt.status === 'need_review').length,
        confirmed_count: receipts.filter((receipt) => receipt.status === 'confirmed').length,
        failed_count: receipts.filter((receipt) => receipt.status === 'failed').length,
        completed_count: completedCount
      })
      this.setData({
        batch,
        receipts,
        countsList: fmt.progressCounts(batch),
        batchStatusText: fmt.statusText(batchStatus),
        batchTone: fmt.statusTone(batchStatus),
        progressPercent,
        canExport,
        loading: false
      })
      this.schedulePoll(batch, receipts)
      this.promptReviewWhenComplete(batch, receipts)
    } catch (error) {
      this.setData({ loading: false })
      wx.showModal({
        title: '加载失败',
        content: error.message || '请确认后端服务已启动。',
        showCancel: false
      })
    }
  },

  promptReviewWhenComplete(batch, receipts) {
    if (this.autoReviewPrompted) return
    const progressDone = Number(batch.progress_percent || 0) >= 100
    const statusPending = fmt.isActiveStatus(batch.status) || receipts.some((receipt) => fmt.isActiveStatus(receipt.status))
    if (!progressDone && statusPending) return

    const reviewable = receipts.find((receipt) => receipt.status === 'need_review' || receipt.status === 'ready_for_review')
    if (reviewable) {
      this.autoReviewPrompted = true
      wx.showModal({
        title: '识别完成',
        content: '已提取票据数据，进入审核页面查看和修改。',
        confirmText: '去审核',
        cancelText: '留在列表',
        success: (res) => {
          if (res.confirm) {
            wx.navigateTo({
              url: `/pages/review/review?receipt_id=${reviewable.receipt_id}&batch_id=${this.data.batchId || 'local'}`
            })
          }
        }
      })
      return
    }

    const failed = receipts.find((receipt) => receipt.status === 'failed')
    if (progressDone && failed) {
      this.autoReviewPrompted = true
      wx.showModal({
        title: '识别结束',
        content: '本批次存在识别失败的票据，请在列表中查看并重试。',
        showCancel: false
      })
    }
  },

  schedulePoll(batch, receipts) {
    this.clearPoll()
    const statusPending = fmt.isActiveStatus(batch.status) || receipts.some((receipt) => fmt.isActiveStatus(receipt.status))
    const progressPending = Number(batch.progress_percent || 0) < 100
    if (!statusPending || !progressPending) return
    this.pollTimer = setTimeout(() => {
      this.loadBatch()
    }, 2500)
  },

  openReceipt(event) {
    const receiptId = event.currentTarget.dataset.id
    const receipt = this.data.receipts.find((item) => String(item.receipt_id) === String(receiptId))
    if (receipt && fmt.isActiveStatus(receipt.status)) {
      wx.showToast({
        title: '处理中，稍后审核',
        icon: 'none'
      })
      return
    }
    wx.navigateTo({
      url: `/pages/review/review?receipt_id=${receiptId}&batch_id=${this.data.batchId || 'local'}`
    })
  },

  async exportExcel() {
    if (!this.data.canExport || this.data.exporting) return
    this.setData({ exporting: true })
    wx.showLoading({ title: '导出中' })
    try {
      const tempFilePath = this.data.localMode
        ? await api.exportAllReceipts()
        : await api.exportBatch(this.data.batchId)
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
