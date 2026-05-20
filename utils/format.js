const ACTIVE_STATUSES = ['uploaded', 'queued', 'ocr_processing', 'llm_structuring', 'processing']
const DONE_STATUSES = ['ready_for_review', 'need_review', 'confirmed', 'failed']

const STATUS_TEXT = {
  uploaded: '已上传',
  queued: '排队中',
  ocr_processing: 'OCR识别中',
  llm_structuring: '结构化中',
  processing: '处理中',
  ready_for_review: '待审核',
  need_review: '需修改',
  confirmed: '已确认',
  failed: '失败',
  partial_failed: '部分失败',
  empty: '空批次'
}

function statusText(status) {
  return STATUS_TEXT[status] || status || '未知'
}

function statusTone(status) {
  if (status === 'confirmed' || status === 'ready_for_review') return 'ok'
  if (status === 'failed' || status === 'partial_failed') return 'error'
  if (status === 'need_review') return 'warn'
  return ''
}

function isActiveStatus(status) {
  return ACTIVE_STATUSES.indexOf(status) >= 0
}

function isDoneStatus(status) {
  return DONE_STATUSES.indexOf(status) >= 0
}

function toText(value) {
  if (value === null || value === undefined) return ''
  return String(value)
}

function toNumber(value) {
  if (value === '' || value === null || value === undefined) return null
  const normalized = Number(String(value).replace(/,/g, ''))
  return Number.isFinite(normalized) ? normalized : null
}

function toInteger(value) {
  const normalized = toNumber(value)
  if (normalized === null) return null
  return Math.trunc(normalized)
}

function emptyItem() {
  return {
    style_no: '',
    product_name: '',
    color: '',
    size: '',
    quantity: '',
    unit_price: '',
    amount: ''
  }
}

function normalizeFormSource(receipt) {
  const source = (receipt && (receipt.final_json || receipt.corrected_json || receipt.structured_json)) || {}
  const items = Array.isArray(source.items) && source.items.length ? source.items : [emptyItem()]
  return {
    ticket_no: toText(source.ticket_no),
    receipt_date: toText(source.receipt_date || source.order_date),
    supplier: toText(source.supplier || source.merchant_name),
    customer: toText(source.customer || source.customer_name),
    total_quantity: toText(source.total_quantity !== undefined ? source.total_quantity : (source.summary || {}).total_quantity),
    total_amount: toText(source.total_amount !== undefined ? source.total_amount : (source.summary || {}).total_amount),
    notes: toText(source.notes),
    items: items.map((item) => ({
      style_no: toText(item.style_no),
      product_name: toText(item.product_name),
      color: toText(item.color),
      size: toText(item.size),
      quantity: toText(item.quantity),
      unit_price: toText(item.unit_price),
      amount: toText(item.amount !== undefined ? item.amount : item.subtotal)
    }))
  }
}

function sourceItemCount(receipt) {
  const source = (receipt && (receipt.final_json || receipt.corrected_json || receipt.structured_json)) || {}
  return Array.isArray(source.items) ? source.items.length : 0
}

function cleanReviewFields(form) {
  return {
    ticket_no: toText(form.ticket_no).trim() || null,
    receipt_date: toText(form.receipt_date).trim() || null,
    order_date: toText(form.receipt_date).trim() || null,
    supplier: toText(form.supplier).trim() || null,
    merchant_name: toText(form.supplier).trim() || null,
    customer: toText(form.customer).trim() || null,
    customer_name: toText(form.customer).trim() || null,
    notes: toText(form.notes).trim() || null
  }
}

function cleanReviewSummary(form) {
  return {
    total_quantity: toInteger(form.total_quantity),
    total_amount: toNumber(form.total_amount)
  }
}

function cleanReviewItem(item) {
  return {
    style_no: toText(item.style_no).trim() || null,
    product_name: toText(item.product_name).trim() || null,
    color: toText(item.color).trim() || null,
    size: toText(item.size).trim() || null,
    quantity: toInteger(item.quantity),
    unit_price: toNumber(item.unit_price),
    subtotal: toNumber(item.amount)
  }
}

function itemHasValue(item) {
  const cleaned = cleanReviewItem(item)
  return Boolean(
    cleaned.style_no ||
    cleaned.product_name ||
    cleaned.color ||
    cleaned.size ||
    cleaned.quantity ||
    cleaned.unit_price ||
    cleaned.subtotal
  )
}

function cleanForm(form) {
  const items = (form.items || []).map((item) => {
    const cleaned = cleanReviewItem(item)
    return {
      style_no: cleaned.style_no,
      product_name: cleaned.product_name,
      color: cleaned.color,
      size: cleaned.size,
      quantity: cleaned.quantity || 0,
      unit_price: cleaned.unit_price || 0,
      amount: cleaned.subtotal || 0
    }
  }).filter((item) => (
    item.style_no ||
    item.product_name ||
    item.color ||
    item.size ||
    item.quantity ||
    item.unit_price ||
    item.amount
  ))

  return Object.assign({}, cleanReviewFields(form), cleanReviewSummary(form), { items })
}

function cleanManualPayload(form) {
  const items = (form.items || [])
    .filter((item) => itemHasValue(item))
    .map((item) => cleanReviewItem(item))
  return {
    merchant_name: toText(form.supplier).trim() || null,
    order_date: toText(form.receipt_date).trim() || null,
    items,
    summary: cleanReviewSummary(form)
  }
}

function countsList(counts) {
  return Object.keys(counts || {}).map((key) => ({
    key,
    text: statusText(key),
    value: counts[key],
    tone: statusTone(key)
  }))
}

function progressCounts(batch) {
  return [
    { key: 'processing', text: '处理中', value: batch.processing_count || 0, tone: '' },
    { key: 'ready', text: '待审核', value: batch.ready_for_review_count || 0, tone: 'ok' },
    { key: 'need', text: '需修改', value: batch.need_review_count || 0, tone: 'warn' },
    { key: 'confirmed', text: '已确认', value: batch.confirmed_count || 0, tone: 'ok' },
    { key: 'failed', text: '失败', value: batch.failed_count || 0, tone: 'error' },
    { key: 'completed', text: '已完成', value: batch.completed_count || 0, tone: 'ok' }
  ]
}

module.exports = {
  ACTIVE_STATUSES,
  DONE_STATUSES,
  statusText,
  statusTone,
  isActiveStatus,
  isDoneStatus,
  emptyItem,
  normalizeFormSource,
  sourceItemCount,
  cleanReviewFields,
  cleanReviewSummary,
  cleanReviewItem,
  itemHasValue,
  cleanForm,
  cleanManualPayload,
  countsList,
  progressCounts
}
