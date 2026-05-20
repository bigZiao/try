const api = require('../../utils/api')
const fmt = require('../../utils/format')

Page({
  data: {
    form: {
      supplier: '',
      receipt_date: '',
      total_quantity: '',
      total_amount: '',
      items: [fmt.emptyItem()]
    },
    saving: false
  },

  onHeaderInput(event) {
    const field = event.currentTarget.dataset.field
    this.setData({
      [`form.${field}`]: event.detail.value
    })
  },

  onItemInput(event) {
    const index = event.currentTarget.dataset.index
    const field = event.currentTarget.dataset.field
    this.setData({
      [`form.items[${index}].${field}`]: event.detail.value
    })
  },

  addItem() {
    const items = this.data.form.items.slice()
    items.push(fmt.emptyItem())
    this.setData({ 'form.items': items })
  },

  removeItem(event) {
    const index = event.currentTarget.dataset.index
    const items = this.data.form.items.slice()
    if (items.length <= 1) return
    items.splice(index, 1)
    this.setData({ 'form.items': items })
  },

  async submit() {
    if (this.data.saving) return
    const payload = fmt.cleanManualPayload(this.data.form)
    if (!payload.items.length) {
      wx.showModal({
        title: '缺少商品',
        content: '至少录入一行商品，商品名称或款号不能全空。',
        showCancel: false
      })
      return
    }

    this.setData({ saving: true })
    wx.showLoading({ title: '保存中' })
    try {
      const receipt = await api.createManualReceipt(payload)
      wx.hideLoading()
      this.setData({ saving: false })
      wx.redirectTo({
        url: `/pages/review/review?receipt_id=${receipt.id}`
      })
    } catch (error) {
      wx.hideLoading()
      this.setData({ saving: false })
      wx.showModal({
        title: '保存失败',
        content: error.message || '请检查录入内容。',
        showCancel: false
      })
    }
  }
})
