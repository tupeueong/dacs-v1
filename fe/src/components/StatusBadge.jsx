import { useState, useEffect, useCallback, useRef } from 'react'
import { checkHealth } from '../api'
import { Activity, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react'

export function StatusBadge() {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [isOpen, setIsOpen] = useState(false)
  const popoverRef = useRef(null)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    try {
      const data = await checkHealth()
      setHealth(data)
    } catch {
      setHealth({
        status: 'error',
        checks: { backend: false },
        message: 'Không thể kết nối tới dịch vụ'
      })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    // Tự động kiểm tra lại sau mỗi 60 giây
    const timer = setInterval(fetchStatus, 60000)
    return () => clearInterval(timer)
  }, [fetchStatus])

  // Đóng popover khi click ra ngoài
  useEffect(() => {
    function handleClickOutside(e) {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const isOk = health?.status === 'ok'
  const checks = health?.checks || {}
  const checkEntries = Object.entries(checks)
  const failedChecks = checkEntries.filter(([, ok]) => !ok)

  return (
    <div className="relative inline-block" ref={popoverRef}>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="status-badge-btn"
        title="Trạng thái kết nối máy chủ AI"
        aria-label="Trạng thái kết nối máy chủ AI"
      >
        <span
          className={`status-dot ${
            loading ? 'status-dot-loading' : isOk ? 'status-dot-ok' : 'status-dot-error'
          }`}
        />
        <span className="status-label">
          {loading ? 'Đang kiểm tra...' : isOk ? 'Backend sẵn sàng' : 'Mất kết nối'}
        </span>
      </button>

      {/* Popover hiển thị chi tiết kiểm tra */}
      {isOpen && (
        <div className="status-popover">
          <div className="status-popover-header">
            <div className="status-popover-title">
              <Activity size={15} className="mr-1.5" />
              <span>Kiểm tra hệ thống (/api/health)</span>
            </div>
            <button
              type="button"
              onClick={fetchStatus}
              className="status-refresh-btn"
              title="Kiểm tra lại"
              disabled={loading}
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>

          <div className="status-popover-body">
            <div className="status-summary">
              {isOk ? (
                <div className="flex items-center text-emerald-600 dark:text-emerald-400 font-medium">
                  <CheckCircle2 size={15} className="mr-1.5 flex-shrink-0" />
                  <span>Tất cả dịch vụ hoạt động bình thường</span>
                </div>
              ) : (
                <div className="flex items-center text-rose-600 dark:text-rose-400 font-medium">
                  <AlertTriangle size={15} className="mr-1.5 flex-shrink-0" />
                  <span>{health?.message || 'Có dịch vụ gặp sự cố'}</span>
                </div>
              )}
            </div>

            {checkEntries.length > 0 && (
              <div className="status-checklist">
                {checkEntries.map(([name, ok]) => (
                  <div key={name} className="status-check-row">
                    <span className="status-check-name">{translateCheckName(name)}</span>
                    <span
                      className={`status-check-tag ${
                        ok ? 'status-tag-ok' : 'status-tag-fail'
                      }`}
                    >
                      {ok ? 'Đạt' : 'Lỗi'}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {!isOk && failedChecks.length > 0 && (
              <div className="status-fail-hint">
                Lưu ý: Nếu đang dùng backend thật, hãy kiểm tra tiến trình tại <code>VITE_API_URL</code>.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function translateCheckName(key) {
  const map = {
    database: 'Cơ sở dữ liệu văn bản',
    vector_index: 'Chỉ mục vector RAG',
    gemini_api: 'API sinh câu trả lời',
    retriever: 'Bộ máy truy hồi dữ liệu',
    backend: 'Máy chủ API',
    network: 'Kết nối mạng'
  }
  return map[key] || key
}
