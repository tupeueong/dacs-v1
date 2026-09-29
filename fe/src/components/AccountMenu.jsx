import { useState, useRef, useEffect } from 'react'
import { User, Settings, Trash2, Database, MoreVertical, ChevronUp } from 'lucide-react'

export function AccountMenu({
  userName,
  onChangeName,
  onClearHistory,
  onOpenIndexInfo
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const menuRef = useRef(null)

  // Đóng popover khi bấm ra ngoài
  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setIsOpen(false)
        setShowClearConfirm(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Lấy chữ cái đầu làm avatar
  const initial = (userName || 'N').trim().charAt(0).toUpperCase()

  const handleClearHistory = () => {
    onClearHistory()
    setShowClearConfirm(false)
    setIsOpen(false)
  }

  return (
    <div className="account-menu-container" ref={menuRef}>
      {/* Khối tài khoản ở thanh đáy sidebar */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="account-menu-btn"
        aria-expanded={isOpen}
      >
        <div className="account-avatar">{initial}</div>
        <div className="account-info truncate">
          <span className="account-name truncate">
            {userName || 'Chưa đặt tên'}
          </span>
          <span className="account-role">Người dùng pháp lý</span>
        </div>
        <ChevronUp size={16} className={`account-chevron ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Popover menu */}
      {isOpen && (
        <div className="account-popover">
          {!showClearConfirm ? (
            <div className="account-popover-list">
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false)
                  onChangeName()
                }}
                className="account-popover-item"
              >
                <User size={15} className="mr-2.5 text-neutral-500" />
                <span>Đổi tên hiển thị</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setIsOpen(false)
                  onOpenIndexInfo()
                }}
                className="account-popover-item"
              >
                <Database size={15} className="mr-2.5 text-neutral-500" />
                <span>Thông tin index RAG</span>
              </button>

              <div className="account-popover-divider" />

              <button
                type="button"
                onClick={() => setShowClearConfirm(true)}
                className="account-popover-item text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40"
              >
                <Trash2 size={15} className="mr-2.5" />
                <span>Xóa toàn bộ lịch sử</span>
              </button>
            </div>
          ) : (
            <div className="account-confirm-box">
              <div className="font-semibold text-xs text-rose-600 dark:text-rose-400 mb-1">
                Xác nhận xóa toàn bộ lịch sử?
              </div>
              <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mb-2.5 leading-snug">
                Thao tác này sẽ xóa tất cả các cuộc trò chuyện đã lưu trên trình duyệt của bạn.
              </p>
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowClearConfirm(false)}
                  className="px-2.5 py-1 text-xs font-medium rounded text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  Hủy
                </button>
                <button
                  type="button"
                  onClick={handleClearHistory}
                  className="px-2.5 py-1 text-xs font-medium rounded bg-rose-600 text-white hover:bg-rose-700 shadow-sm"
                >
                  Xác nhận xóa
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
