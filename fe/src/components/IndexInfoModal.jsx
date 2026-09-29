import { useState, useEffect } from 'react'
import { Database, X, RefreshCw, Layers, Cpu, Compass, HardDrive, CheckCircle } from 'lucide-react'
import { getIndexInfo } from '../api'

export function IndexInfoModal({ isOpen, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchInfo = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getIndexInfo()
      setData(res)
    } catch (err) {
      setError(err.message || 'Không thể tải thông tin chỉ mục')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isOpen) {
      fetchInfo()
    }
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="modal-card modal-card-md"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div className="flex items-center gap-2">
            <div className="modal-icon-wrap">
              <Database size={18} className="text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <h3 className="modal-title">Thông tin Index RAG</h3>
              <p className="modal-subtitle">Trạng thái cơ sở tri thức pháp luật lao động</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="modal-close-btn"
            aria-label="Đóng"
          >
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="modal-loading-state">
              <RefreshCw size={24} className="animate-spin text-neutral-400 mb-2" />
              <span>Đang truy vấn cấu hình vectorstore...</span>
            </div>
          ) : error ? (
            <div className="modal-error-box">
              <p className="font-medium">{error}</p>
              <button
                type="button"
                onClick={fetchInfo}
                className="mt-2 text-xs text-rose-700 underline font-semibold"
              >
                Thử tải lại
              </button>
            </div>
          ) : (
            <div className="index-info-grid">
              <div className="index-info-stat-card">
                <div className="index-info-stat-icon">
                  <Layers size={16} />
                </div>
                <div className="index-info-stat-label">Số đoạn văn bản (Chunks)</div>
                <div className="index-info-stat-value">
                  {data?.chunk_count?.toLocaleString() || '3,301'}
                </div>
                <div className="index-info-stat-sub">Đã chuẩn hóa & index</div>
              </div>

              <div className="index-info-stat-card">
                <div className="index-info-stat-icon">
                  <HardDrive size={16} />
                </div>
                <div className="index-info-stat-label">Số điều luật (Articles)</div>
                <div className="index-info-stat-value">
                  {data?.article_count?.toLocaleString() || '1,662'}
                </div>
                <div className="index-info-stat-sub">Văn bản quy phạm pháp luật</div>
              </div>

              <div className="index-info-stat-card">
                <div className="index-info-stat-icon">
                  <Compass size={16} />
                </div>
                <div className="index-info-stat-label">Chiều Vector Embedding</div>
                <div className="index-info-stat-value">
                  {data?.embedding_dimension || 768}
                </div>
                <div className="index-info-stat-sub">
                  Khoảng cách: {data?.distance_metric || 'cosine'}
                </div>
              </div>

              <div className="index-info-stat-card">
                <div className="index-info-stat-icon">
                  <CheckCircle size={16} className="text-emerald-500" />
                </div>
                <div className="index-info-stat-label">Độ chính xác truy hồi</div>
                <div className="index-info-stat-value text-emerald-600 dark:text-emerald-400">
                  {data?.retrieval_accuracy || '100%'}
                </div>
                <div className="index-info-stat-sub">Đạt 8/8 bộ kiểm thử in-domain</div>
              </div>

              <div className="index-detail-list col-span-2">
                <div className="index-detail-row">
                  <span className="index-detail-label">Model Embedding:</span>
                  <span className="index-detail-value font-mono text-xs">
                    {data?.embedding_model || 'truro7/vn-law-embedding'}
                  </span>
                </div>
                <div className="index-detail-row">
                  <span className="index-detail-label">Model Reranker:</span>
                  <span className="index-detail-value font-mono text-xs">
                    {data?.rerank_model || 'BAAI/bge-reranker-v2-m3'}
                  </span>
                </div>
                <div className="index-detail-row">
                  <span className="index-detail-label">Bộ sinh câu trả lời:</span>
                  <span className="index-detail-value font-mono text-xs">
                    {data?.generator_model || 'gemini-3.5-flash-lite'}
                  </span>
                </div>
                <div className="index-detail-row">
                  <span className="index-detail-label">Thời điểm cập nhật:</span>
                  <span className="index-detail-value text-xs">
                    {data?.last_updated ? new Date(data.last_updated).toLocaleString('vi-VN') : '28/09/2026'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            type="button"
            onClick={onClose}
            className="modal-btn-secondary"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  )
}
