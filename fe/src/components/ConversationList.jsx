import { useState, useMemo, useRef, useEffect } from 'react'
import {
  MessageSquare,
  MoreHorizontal,
  Edit2,
  Trash2,
  Search,
  X,
  Check
} from 'lucide-react'

function getGroupKey(dateStr) {
  if (!dateStr) return 'Cũ hơn'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return 'Cũ hơn'

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const sevenDaysAgo = new Date(today)
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7)

  const targetDate = new Date(date.getFullYear(), date.getMonth(), date.getDate())

  if (targetDate.getTime() >= today.getTime()) {
    return 'Hôm nay'
  }
  if (targetDate.getTime() >= yesterday.getTime()) {
    return 'Hôm qua'
  }
  if (targetDate.getTime() >= sevenDaysAgo.getTime()) {
    return '7 ngày trước'
  }
  return 'Cũ hơn'
}

export function ConversationList({
  conversations = [],
  activeId,
  onSelect,
  onRename,
  onDelete,
  searchQuery = '',
  onCloseMobileDrawer
}) {
  const [menuOpenId, setMenuOpenId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editTitle, setEditTitle] = useState('')
  const [deleteConfirmId, setDeleteConfirmId] = useState(null)
  const menuRef = useRef(null)

  // Đóng popover menu khi nhấp ra ngoài
  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpenId(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Lọc theo từ khóa tìm kiếm
  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return conversations
    return conversations.filter((c) => (c.title || '').toLowerCase().includes(q))
  }, [conversations, searchQuery])

  // Nhóm theo các mốc thời gian
  const grouped = useMemo(() => {
    const groups = {
      'Hôm nay': [],
      'Hôm qua': [],
      '7 ngày trước': [],
      'Cũ hơn': []
    }

    for (const conv of filtered) {
      const groupKey = getGroupKey(conv.updatedAt || conv.createdAt)
      if (!groups[groupKey]) {
        groups[groupKey] = []
      }
      groups[groupKey].push(conv)
    }

    return groups
  }, [filtered])

  const handleStartRename = (conv, e) => {
    e.stopPropagation()
    setEditingId(conv.id)
    setEditTitle(conv.title)
    setMenuOpenId(null)
  }

  const handleSaveRename = (id, e) => {
    e?.stopPropagation()
    if (editTitle.trim()) {
      onRename(id, editTitle.trim())
    }
    setEditingId(null)
  }

  const handleCancelRename = (e) => {
    e?.stopPropagation()
    setEditingId(null)
  }

  const handlePromptDelete = (id, e) => {
    e.stopPropagation()
    setDeleteConfirmId(id)
    setMenuOpenId(null)
  }

  const handleConfirmDelete = (id, e) => {
    e.stopPropagation()
    onDelete(id)
    setDeleteConfirmId(null)
  }

  const handleCancelDelete = (e) => {
    e.stopPropagation()
    setDeleteConfirmId(null)
  }

  const groupOrder = ['Hôm nay', 'Hôm qua', '7 ngày trước', 'Cũ hơn']

  if (conversations.length === 0) {
    return (
      <div className="conversation-empty-list">
        <p>Chưa có lịch sử hội thoại</p>
        <span>Gửi câu hỏi đầu tiên để lưu phiên trò chuyện</span>
      </div>
    )
  }

  if (filtered.length === 0) {
    return (
      <div className="conversation-empty-list">
        <p>Không tìm thấy kết quả</p>
        <span>Thử với từ khóa khác</span>
      </div>
    )
  }

  return (
    <div className="conversation-list-container">
      {groupOrder.map((groupName) => {
        const items = grouped[groupName] || []
        if (items.length === 0) return null

        return (
          <div key={groupName} className="conversation-group">
            <div className="conversation-group-header">{groupName}</div>
            <div className="conversation-group-items">
              {items.map((conv) => {
                const isActive = conv.id === activeId
                const isMenuOpen = menuOpenId === conv.id
                const isEditing = editingId === conv.id
                const isDeleting = deleteConfirmId === conv.id

                if (isEditing) {
                  return (
                    <div
                      key={conv.id}
                      className="conversation-item-editing"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveRename(conv.id, e)
                          if (e.key === 'Escape') handleCancelRename(e)
                        }}
                        autoFocus
                        className="conversation-rename-input"
                      />
                      <button
                        type="button"
                        onClick={(e) => handleSaveRename(conv.id, e)}
                        className="conversation-btn-save"
                        title="Lưu"
                      >
                        <Check size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={handleCancelRename}
                        className="conversation-btn-cancel"
                        title="Hủy"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  )
                }

                if (isDeleting) {
                  return (
                    <div
                      key={conv.id}
                      className="conversation-item-deleting"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <span className="text-xs text-rose-600 dark:text-rose-400 font-medium">
                        Xác nhận xóa?
                      </span>
                      <div className="flex items-center gap-1.5 ml-auto">
                        <button
                          type="button"
                          onClick={(e) => handleConfirmDelete(conv.id, e)}
                          className="conversation-delete-confirm-btn"
                          title="Xóa vĩnh viễn"
                        >
                          Xóa
                        </button>
                        <button
                          type="button"
                          onClick={handleCancelDelete}
                          className="conversation-delete-cancel-btn"
                          title="Giữ lại"
                        >
                          Hủy
                        </button>
                      </div>
                    </div>
                  )
                }

                return (
                  <div
                    key={conv.id}
                    onClick={() => {
                      onSelect(conv.id)
                      if (onCloseMobileDrawer) onCloseMobileDrawer()
                    }}
                    className={`conversation-item ${
                      isActive ? 'conversation-item-active' : ''
                    }`}
                    title={conv.title}
                  >
                    <MessageSquare size={15} className="conversation-icon flex-shrink-0" />
                    <span className="conversation-title truncate flex-1">
                      {conv.title || 'Cuộc trò chuyện'}
                    </span>

                    {/* Nút 3 chấm mở action menu */}
                    <div className="conversation-item-actions">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          setMenuOpenId(isMenuOpen ? null : conv.id)
                        }}
                        className="conversation-more-btn"
                        title="Tùy chọn"
                        aria-label="Tùy chọn cuộc trò chuyện"
                      >
                        <MoreHorizontal size={14} />
                      </button>

                      {isMenuOpen && (
                        <div className="conversation-dropdown-menu" ref={menuRef}>
                          <button
                            type="button"
                            onClick={(e) => handleStartRename(conv, e)}
                            className="conversation-menu-action"
                          >
                            <Edit2 size={13} className="mr-2" />
                            <span>Đổi tên</span>
                          </button>
                          <button
                            type="button"
                            onClick={(e) => handlePromptDelete(conv.id, e)}
                            className="conversation-menu-action text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                          >
                            <Trash2 size={13} className="mr-2" />
                            <span>Xóa</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
