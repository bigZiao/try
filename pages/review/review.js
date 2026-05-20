const api = require('../../utils/api')
const fmt = require('../../utils/format')

Page({
  data: {
    receiptId: '',
    batchId: '',
    receipt: {},
    imageUrl: '',
    keyImageUrl: '',
    reviewImageUrl: '',
    reviewImageLabel: '',
    ocrOverlay: null,
    ocrBlocks: [],
    showOcrOverlay: false,
    ocrOverlayLoading: false,
    form: fmt.normalizeFormSource({}),
    previewItems: [],
    initialItemCount: 0,
    statusText: '加载中',
    statusTone: '',
    validationErrors: [],
    hasImage: true,
    isLocked: false,
    loading: false,
    saving: false,
    confirming: false,
    retrying: false
  },

  pollTimer: null,

  onLoad(options) {
    this.setData({
      receiptId: options.receipt_id || options.id || '',
      batchId: options.batch_id || ''
    })
    this.loadReceipt()
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

  async loadReceipt() {
    if (!this.data.receiptId) return
    this.setData({ loading: true })
    try {
      const receipt = await api.getReceipt(this.data.receiptId)
      const form = fmt.normalizeFormSource(receipt)
      let imageUrl = ''
      let keyImageUrl = ''
      let reviewImageUrl = ''
      let reviewImageLabel = ''
      let hasImage = receipt.source_type !== 'manual'
      if (hasImage) {
        const keyImageVersion = Date.now()
        try {
          keyImageUrl = await api.downloadReceiptKeyImage(this.data.receiptId, keyImageVersion)
          reviewImageUrl = keyImageUrl
          reviewImageLabel = '关键区域图'
        } catch (ignore) {
          keyImageUrl = ''
          this.setData({ ocrOverlay: null, ocrBlocks: [] })
        }
        try {
          imageUrl = await api.downloadReceiptImage(this.data.receiptId)
          if (!reviewImageUrl) {
            reviewImageUrl = imageUrl
            reviewImageLabel = '完整原图'
            this.setData({ ocrOverlay: null, ocrBlocks: [] })
          }
        } catch (ignore) {
          if (!reviewImageUrl) hasImage = false
        }
      }
      this.setData({
        receipt,
        imageUrl,
        keyImageUrl,
        reviewImageUrl,
        reviewImageLabel,
        ocrOverlay: null,
        ocrBlocks: [],
        showOcrOverlay: false,
        ocrOverlayLoading: false,
        hasImage,
        form,
        previewItems: this.buildPreviewItems(form.items),
        initialItemCount: fmt.sourceItemCount(receipt),
        statusText: fmt.statusText(receipt.status),
        statusTone: fmt.statusTone(receipt.status),
        validationErrors: this.formatValidationErrors(receipt.validation_errors),
        isLocked: false,
        loading: false
      })
      this.schedulePoll(receipt)
    } catch (error) {
      this.setData({ loading: false })
      wx.showModal({
        title: '加载失败',
        content: error.message || '请确认后端服务已启动。',
        showCancel: false
      })
    }
  },

  onReviewImageLoad() {
    if (this.data.showOcrOverlay) {
      this.updateOcrBlocks()
    }
  },

  updateOcrBlocks() {
    const overlay = this.data.ocrOverlay
    if (!this.data.showOcrOverlay || !overlay || !overlay.image_width || !Array.isArray(overlay.blocks) || !this.data.keyImageUrl || this.data.reviewImageUrl !== this.data.keyImageUrl) {
      this.setData({ ocrBlocks: [] })
      return
    }
    wx.createSelectorQuery()
      .in(this)
      .select('.key-image-frame')
      .boundingClientRect((rect) => {
        if (!rect || !rect.width) return
        const scale = rect.width / overlay.image_width
        const blocks = overlay.blocks.map((block) => ({
          ...block,
          style: [
            `left:${Math.round((block.left || 0) * scale)}px`,
            `top:${Math.round((block.top || 0) * scale)}px`,
            `width:${Math.round((block.width || 0) * scale)}px`,
            `height:${Math.round((block.height || 0) * scale)}px`
          ].join(';')
        }))
        this.setData({ ocrBlocks: blocks })
      })
      .exec()
  },

  async toggleOcrOverlay() {
    if (!this.data.keyImageUrl || this.data.reviewImageUrl !== this.data.keyImageUrl) {
      wx.showToast({ title: '暂无关键图', icon: 'none' })
      return
    }
    if (this.data.showOcrOverlay) {
      this.setData({
        showOcrOverlay: false,
        ocrBlocks: []
      })
      return
    }
    if (this.data.ocrOverlay) {
      this.setData({ showOcrOverlay: true })
      this.updateOcrBlocks()
      return
    }
    this.setData({ ocrOverlayLoading: true })
    try {
      const ocrOverlay = await api.getOcrOverlay(this.data.receiptId, 'key')
      this.setData({
        ocrOverlay,
        showOcrOverlay: true,
        ocrOverlayLoading: false
      })
      this.updateOcrBlocks()
    } catch (error) {
      this.setData({
        ocrOverlay: null,
        ocrBlocks: [],
        showOcrOverlay: false,
        ocrOverlayLoading: false
      })
      wx.showModal({
        title: '加载失败',
        content: error.message || '暂时无法加载 OCR 位置。',
        showCancel: false
      })
    }
  },

  buildPreviewItems(items) {
    return (items || []).map((item, index) => ({
      index: index + 1,
      name: item.product_name || item.style_no || '未命名商品',
      style: item.style_no || '-',
      color: item.color || '-',
      size: item.size || '-',
      quantity: item.quantity || '0',
      unit_price: item.unit_price || '0',
      amount: item.amount || '0'
    }))
  },

  schedulePoll(receipt) {
    this.clearPoll()
    if (!fmt.isActiveStatus(receipt.status)) return
    this.pollTimer = setTimeout(() => {
      this.loadReceipt()
    }, 2500)
  },

  formatValidationErrors(errors) {
    if (!Array.isArray(errors)) return []
    return errors.map((error) => {
      if (typeof error === 'string') return error
      try {
        return JSON.stringify(error)
      } catch (ignore) {
        return String(error)
      }
    })
  },

  previewOriginal() {
    if (!this.data.imageUrl) return
    wx.previewImage({
      urls: [this.data.imageUrl],
      current: this.data.imageUrl
    })
  },

  previewKeyImage() {
    if (!this.data.reviewImageUrl) return
    wx.previewImage({
      urls: [this.data.reviewImageUrl],
      current: this.data.reviewImageUrl
    })
  },

  onHeaderInput(event) {
    if (this.data.isLocked) return
    const field = event.currentTarget.dataset.field
    this.setData({
      [`form.${field}`]: event.detail.value
    })
    this.setData({
      previewItems: this.buildPreviewItems(this.data.form.items)
    })
  },

  onItemInput(event) {
    if (this.data.isLocked) return
    const index = event.currentTarget.dataset.index
    const field = event.currentTarget.dataset.field
    this.setData({
      [`form.items[${index}].${field}`]: event.detail.value
    })
    this.setData({
      previewItems: this.buildPreviewItems(this.data.form.items)
    })
  },

  addItem() {
    if (this.data.isLocked) return
    const items = this.data.form.items.slice()
    items.push(fmt.emptyItem())
    this.setData({
      'form.items': items
    })
    this.setData({
      previewItems: this.buildPreviewItems(items)
    })
  },

  removeItem(event) {
    if (this.data.isLocked) return
    const index = event.currentTarget.dataset.index
    const items = this.data.form.items.slice()
    if (items.length <= 1) return
    items.splice(index, 1)
    this.setData({
      'form.items': items
    })
    this.setData({
      previewItems: this.buildPreviewItems(items)
    })
  },

  async saveDraft(options) {
    const receiptId = this.data.receiptId
    const form = this.data.form
    let receipt = await api.updateReviewFields(
      receiptId,
      fmt.cleanReviewFields(form),
      fmt.cleanReviewSummary(form)
    )

    const items = (form.items || []).filter((item) => fmt.itemHasValue(item))
    const initialItemCount = this.data.initialItemCount || 0
    const patchCount = Math.min(initialItemCount, items.length)

    for (let index = 0; index < patchCount; index += 1) {
      receipt = await api.updateReviewItem(receiptId, index, fmt.cleanReviewItem(items[index]))
    }

    for (let index = initialItemCount; index < items.length; index += 1) {
      receipt = await api.addReviewItem(receiptId, fmt.cleanReviewItem(items[index]))
    }

    for (let index = initialItemCount - 1; index >= items.length; index -= 1) {
      receipt = await api.deleteReviewItem(receiptId, index)
    }

    const nextForm = fmt.normalizeFormSource(receipt)
    this.setData({
      receipt,
      form: nextForm,
      previewItems: this.buildPreviewItems(nextForm.items),
      initialItemCount: fmt.sourceItemCount(receipt),
      statusText: fmt.statusText(receipt.status),
      statusTone: fmt.statusTone(receipt.status),
      validationErrors: this.formatValidationErrors(receipt.validation_errors),
      isLocked: false
    })

    if (!options || !options.silent) {
      wx.showToast({ title: '已保存', icon: 'success' })
    }
    return receipt
  },

  async saveOnly() {
    if (this.data.saving) return
    this.setData({ saving: true })
    wx.showLoading({ title: '保存中' })
    try {
      await this.saveDraft()
      wx.hideLoading()
      this.setData({ saving: false })
    } catch (error) {
      wx.hideLoading()
      this.setData({ saving: false })
      this.showEditError(error)
    }
  },

  async confirm() {
    if (this.data.confirming) return
    this.setData({ confirming: true })
    wx.showLoading({ title: '确认中' })
    try {
      await this.saveDraft({ silent: true })
      const finalJson = fmt.cleanForm(this.data.form)
      const receipt = await api.confirmReceipt(this.data.receiptId, finalJson)
      wx.hideLoading()
      const form = fmt.normalizeFormSource(receipt)
      this.setData({
        receipt,
        form,
        previewItems: this.buildPreviewItems(form.items),
        initialItemCount: fmt.sourceItemCount(receipt),
        statusText: fmt.statusText(receipt.status),
        statusTone: fmt.statusTone(receipt.status),
        validationErrors: this.formatValidationErrors(receipt.validation_errors),
        isLocked: false,
        confirming: false
      })
      if (receipt.status === 'confirmed') {
        wx.showToast({ title: '已确认', icon: 'success' })
      } else {
        wx.showModal({
          title: '仍需修改',
          content: '后端校验未通过，请根据提示继续调整。',
          showCancel: false
        })
      }
    } catch (error) {
      wx.hideLoading()
      this.setData({ confirming: false })
      this.showEditError(error)
    }
  },

  showEditError(error) {
    const locked = error && error.statusCode === 409
    wx.showModal({
      title: locked ? '票据已锁定' : '保存失败',
      content: error.message || '请检查表单内容。',
      showCancel: false
    })
    if (locked) {
      this.loadReceipt()
    }
  },

  async retry() {
    if (this.data.retrying) return
    this.setData({ retrying: true })
    wx.showLoading({ title: '重试中' })
    try {
      await api.retryReceipt(this.data.receiptId)
      wx.hideLoading()
      this.setData({ retrying: false })
      wx.showToast({ title: '已提交重试', icon: 'success' })
      if (this.data.batchId) {
        wx.navigateBack()
      } else {
        this.loadReceipt()
      }
    } catch (error) {
      wx.hideLoading()
      this.setData({ retrying: false })
      wx.showModal({
        title: '重试失败',
        content: error.message || '重复票据、已锁定票据或不存在的票据不能重试。',
        showCancel: false
      })
    }
  }
})
