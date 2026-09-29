import { useState, useEffect } from 'react'
import { User, X, Check } from 'lucide-react'

export function UserNameModal({ isOpen, initialName = '', onSave, onClose, isRequired = false }) {
  const [name, setName] = useState(initialName)

  useEffect(() => {
    setName(initialName)
  }, [initialName, isOpen])

  if (!isOpen) return null

  const handleSubmit = (e) => {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed && isRequired) return
    onSave(trimmed || 'Người dùng')
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div
        className="modal-card modal-card-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div className="flex items-center gap-2">
            <div className="modal-icon-wrap">
              <User size={18} className="text-neutral-700 dark:text-neutral-300" />
            </div>
            <div>
              <h3 className="modal-title">
                {isRequired ? 'Chào mừng bạn đến với Trợ lý Pháp lý' : 'Đổi tên hiển thị'}
              </h3>
              <p className="modal-subtitle">
                {isRequired
                  ? 'Vui lòng nhập tên của bạn để cá nhân hóa trải nghiệm hội thoại'
                  : 'Cập nhật tên gọi hiển thị trong hệ thống'}
              </p>
            </div>
          </div>
          {!isRequired && (
            <button
              type="button"
              onClick={onClose}
              className="modal-close-btn"
              aria-label="Đóng"
            >
              <X size={18} />
            </button>
          )}
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <label className="modal-form-label" htmlFor="user-name-input">
              Họ và tên hoặc tên xưng hô:
            </label>
            <input
              id="user-name-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ví dụ: Luật sư Tuấn, Chuyên viên Linh..."
              className="modal-form-input"
              autoFocus
              required={isRequired}
            />
          </div>

          <div className="modal-footer">
            {!isRequired && (
              <button
                type="button"
                onClick={onClose}
                className="modal-btn-secondary"
              >
                Hủy
              </button>
            )}
            <button
              type="submit"
              disabled={isRequired && !name.trim()}
              className="modal-btn-primary"
            >
              <Check size={15} className="mr-1.5" />
              <span>{isRequired ? 'Bắt đầu sử dụng' : 'Lưu thay đổi'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
