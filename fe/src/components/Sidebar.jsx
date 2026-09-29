import { useState } from 'react'
import { Plus, Search, PanelLeftClose, Scale, X } from 'lucide-react'
import { ConversationList } from './ConversationList'
import { AccountMenu } from './AccountMenu'

export function Sidebar({
  conversations = [],
  activeId,
  userName,
  onNewChat,
  onSelectConversation,
  onRenameConversation,
  onDeleteConversation,
  onClearAllHistory,
  onChangeUserName,
  onOpenIndexInfo,
  isOpen,
  onToggleSidebar,
  isMobile
}) {
  const [searchQuery, setSearchQuery] = useState('')

  return (
    <>
      {/* Lớp phủ mờ (Backdrop) khi mở sidebar trên thiết bị di động */}
      {isMobile && isOpen && (
        <div
          className="sidebar-mobile-backdrop"
          onClick={onToggleSidebar}
          aria-hidden="true"
        />
      )}

      <aside
        className={`sidebar-root ${isOpen ? 'sidebar-open' : 'sidebar-closed'} ${
          isMobile ? 'sidebar-mobile' : ''
        }`}
        aria-label="Thanh điều hướng lịch sử trò chuyện"
      >
        {/* Phần đầu Sidebar */}
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="sidebar-brand-icon">
              <Scale size={18} />
            </div>
            <div className="sidebar-brand-text truncate">
              <span className="sidebar-title">Trợ lý Luật Lao động</span>
              <span className="sidebar-subtitle">Hệ thống RAG Pháp lý</span>
            </div>
          </div>

          {/* Nút đóng sidebar */}
          <button
            type="button"
            onClick={onToggleSidebar}
            className="sidebar-close-btn"
            title="Thu gọn thanh bên"
            aria-label="Thu gọn thanh bên"
          >
            {isMobile ? <X size={18} /> : <PanelLeftClose size={18} />}
          </button>
        </div>

        {/* Nút tạo cuộc trò chuyện mới */}
        <div className="sidebar-action-wrap">
          <button
            type="button"
            onClick={() => {
              onNewChat()
              if (isMobile) onToggleSidebar()
            }}
            className="sidebar-new-chat-btn"
          >
            <Plus size={16} strokeWidth={2.2} className="mr-2" />
            <span>Cuộc trò chuyện mới</span>
          </button>
        </div>

        {/* Ô tìm kiếm lịch sử cuộc trò chuyện */}
        {conversations.length > 0 && (
          <div className="sidebar-search-wrap">
            <div className="sidebar-search-box">
              <Search size={14} className="text-neutral-400 mr-2 flex-shrink-0" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm kiếm lịch sử..."
                className="sidebar-search-input"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="sidebar-search-clear"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          </div>
        )}

        {/* Danh sách các cuộc trò chuyện phân nhóm thời gian */}
        <div className="sidebar-content">
          <ConversationList
            conversations={conversations}
            activeId={activeId}
            onSelect={onSelectConversation}
            onRename={onRenameConversation}
            onDelete={onDeleteConversation}
            searchQuery={searchQuery}
            onCloseMobileDrawer={isMobile ? onToggleSidebar : undefined}
          />
        </div>

        {/* Khối tài khoản người dùng dưới cùng */}
        <div className="sidebar-footer">
          <AccountMenu
            userName={userName}
            onChangeName={onChangeUserName}
            onClearHistory={onClearAllHistory}
            onOpenIndexInfo={onOpenIndexInfo}
          />
        </div>
      </aside>
    </>
  )
}
