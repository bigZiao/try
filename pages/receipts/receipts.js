const api = require('../../utils/api')
const fmt = require('../../utils/format')

Page({
  data: {
    receipts: [],
    selectedReceiptIds: [],
    receiptFilters: {
      status: '',
      source_type: '',
      start_date: '',
      end_date: '',
      merchant_name: '',
      keyword: '',
      include_deleted: false
    },
    historyLoading: false
  },

  onShow() {
    this.loadReceipts()
  },

  normalizeList(result, keys) {
    if (Array.isArray(result)) return result
    for (let index = 0; index < keys.length; index += 1) {
      const value = result && result[keys[index]]
      if (Array.isArray(value)) return value
    }
    return []
  },

  buildReceiptRow(receipt, selectedMap) {
    const styleText = receipt.display_item || '-'
    return {
      ...receipt,
      statusText: fmt.statusText(receipt.status),
      tone: fmt.statusTone(receipt.status),
      supplierText: receipt.merchant_name || '-',
      styleText,
      rowText: `${receipt.merchant_name || '-'} / ${styleText} / 总数 ${receipt.total_quantity || 0} / 总金额 ${receipt.total_amount || 0}`,
      selected: Boolean(selectedMap[String(receipt.id)])
    }
  },

  async loadReceipts() {
    if (this.data.historyLoading) return
    this.setData({ historyLoading: true })
    try {
      const result = await api.listReceipts(Object.assign({
        limit: 50,
        offset: 0
      }, this.data.receiptFilters))
      const selectedMap = {}
      this.data.selectedReceiptIds.forEach((id) => {
        selectedMap[String(id)] = true
      })
      const receipts = this.normalizeList(result, ['items', 'receipts', 'data'])
        .map((receipt) => this.buildReceiptRow(receipt, selectedMap))
      this.setData({
        receipts,
        selectedReceiptIds: receipts.filter((receipt) => receipt.selected).map((receipt) => String(receipt.id)),
        historyLoading: false
      })
    } catch (error) {
      this.setData({ historyLoading: false })
      wx.showModal({
        title: '列表加载失败',
        content: error.message || '请确认后端账单列表接口可用。',
        showCancel: false
      })
    }
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
    this.loadReceipts()
  },

  onSourceFilterChange(event) {
    const values = ['', 'image', 'manual']
    this.setData({
      'receiptFilters.source_type': values[Number(event.detail.value)] || ''
    })
    this.loadReceipts()
  },

  applyReceiptFilters() {
    this.loadReceipts()
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
      },
      selectedReceiptIds: []
    })
    this.loadReceipts()
  },

  openReceipt(event) {
    const receiptId = event.currentTarget.dataset.id
    wx.navigateTo({
      url: `/pages/review/review?receipt_id=${receiptId}`
    })
  },

  openManual() {
    wx.navigateTo({
      url: '/pages/manual/manual'
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

  selectAllVisibleReceipts() {
    const allSelected = this.data.receipts.length > 0 && this.data.receipts.every((receipt) => receipt.selected)
    const selectedReceiptIds = allSelected ? [] : this.data.receipts.map((receipt) => String(receipt.id))
    const selectedMap = {}
    selectedReceiptIds.forEach((id) => {
      selectedMap[String(id)] = true
    })
    this.setData({
      selectedReceiptIds,
      receipts: this.data.receipts.map((receipt) => ({
        ...receipt,
        selected: Boolean(selectedMap[String(receipt.id)])
      }))
    })
  },

  async exportSelectedReceipts() {
    const selected = this.data.receipts.filter((receipt) => receipt.selected)
    if (!selected.length) {
      wx.showToast({ title: '请先选择账单', icon: 'none' })
      return
    }

    wx.showLoading({ title: '导出中' })
    try {
      const tempFilePath = await api.exportSelectedReceipts(selected.map((receipt) => receipt.id))
      wx.hideLoading()
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
      wx.showModal({
        title: '导出失败',
        content: error.message || '请稍后重试。',
        showCancel: false
      })
    }
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
          this.loadReceipts()
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
  }
})
