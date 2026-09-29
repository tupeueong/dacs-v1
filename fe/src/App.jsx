import { useState, useEffect, useCallback } from 'react'
import { useConversations } from './hooks/useConversations'
import { sendChatMessage } from './api'
import { Sidebar } from './components/Sidebar'
import { ChatWindow } from './components/ChatWindow'
import { IndexInfoModal } from './components/IndexInfoModal'
import { UserNameModal } from './components/UserNameModal'

export default function App() {
  const {
    conversations,
    currentConversation,
    activeId,
    setActiveId,
    userName,
    updateUserName,
    createNewConversation,
    selectConversation,
    generateConversationId,
    addUserMessage,
    addAssistantMessage,
    removeLastMessage,
    renameConversation,
    deleteConversation,
    clearAllConversations
  } = useConversations()

  const [isLoading, setIsLoading] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [isMobile, setIsMobile] = useState(false)
  const [isIndexInfoOpen, setIsIndexInfoOpen] = useState(false)
  const [isNameModalOpen, setIsNameModalOpen] = useState(false)

  // Quản lý theme Sáng / Tối (hỗ trợ theo hệ thống hoặc người dùng chọn)
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem('law_rag_theme')
      if (saved) return saved
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    } catch {
      return 'light'
    }
  })

  // Áp dụng theme lên class HTML root
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
    try {
      localStorage.setItem('law_rag_theme', theme)
    } catch (e) {
      console.error(e)
    }
  }, [theme])

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))
  }

  // Theo dõi kích thước màn hình để tự động điều chỉnh Sidebar thành Drawer
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768
      setIsMobile(mobile)
      if (mobile) {
        setIsSidebarOpen(false)
      } else {
        setIsSidebarOpen(true)
      }
    }

    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Mở modal nhập tên nếu là lần đầu truy cập và chưa có tên lưu
  useEffect(() => {
    if (!userName) {
      setIsNameModalOpen(true)
    }
  }, [userName])

  /**
   * Xử lý gửi câu hỏi:
   * - Xác định convId ĐỒNG BỘ ngay từ đầu (biến cục bộ convId)
   * - Ghi nhận cả tin nhắn user và AI vào đúng convId này, bất kể người dùng chuyển cuộc trò chuyện
   */
  const handleSendMessage = useCallback(
    async (text, existingConvId = null) => {
      const trimmedText = text?.trim()
      if (!trimmedText || isLoading) return

      // 1. Xác định convId đồng bộ
      const isNew = !existingConvId && activeId === 'draft'
      const convId = existingConvId || (isNew ? generateConversationId() : activeId)

      // 2. Thêm tin nhắn người dùng vào đúng convId
      addUserMessage(convId, trimmedText)

      // Nếu là cuộc trò chuyện mới, chuyển activeId sang convId ngay lập tức
      if (isNew) {
        setActiveId(convId)
      }

      setIsLoading(true)

      try {
        // Lấy lịch sử hội thoại của đúng cuộc trò chuyện convId nếu cần
        const targetConv = conversations.find((c) => c.id === convId)
        const history = targetConv ? targetConv.messages : []

        const res = await sendChatMessage(trimmedText, history)

        // 3. Luôn ghi câu trả lời AI vào đúng convId đã gửi
        addAssistantMessage(convId, res.answer, res.sources || [])
      } catch (err) {
        console.error('Lỗi khi truy vấn trợ lý pháp lý:', err)
        // 4. Luôn ghi lỗi AI vào đúng convId đã gửi
        addAssistantMessage(convId, '', [], {
          status: err.status || 500,
          message:
            err.detail?.message ||
            err.message ||
            'Đã xảy ra sự cố khi xử lý câu hỏi pháp lý'
        })
      } finally {
        setIsLoading(false)
      }
    },
    [
      activeId,
      conversations,
      isLoading,
      generateConversationId,
      addUserMessage,
      addAssistantMessage,
      setActiveId
    ]
  )

  /**
   * Xử lý nút "Thử lại" khi gặp lỗi:
   * - Xác định chính xác cuộc trò chuyện hiện tại
   * - Xóa tin nhắn lỗi cũ và gửi lại vào đúng cuộc trò chuyện đó, không tạo cuộc mới
   */
  const handleRetryLastMessage = useCallback(() => {
    const targetConvId = activeId
    if (!targetConvId || targetConvId === 'draft') return

    const targetConv = conversations.find((c) => c.id === targetConvId)
    if (!targetConv) return

    const msgs = targetConv.messages || []
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'user') {
        const question = msgs[i].content
        // Xóa tin nhắn lỗi trợ lý trước khi thử lại
        removeLastMessage(targetConvId)
        // Gửi lại câu hỏi vào đúng targetConvId
        handleSendMessage(question, targetConvId)
        break
      }
    }
  }, [activeId, conversations, handleSendMessage, removeLastMessage])

  return (
    <div className="app-container">
      {/* Thanh bên trái */}
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        userName={userName}
        onNewChat={createNewConversation}
        onSelectConversation={selectConversation}
        onRenameConversation={renameConversation}
        onDeleteConversation={deleteConversation}
        onClearAllHistory={clearAllConversations}
        onChangeUserName={() => setIsNameModalOpen(true)}
        onOpenIndexInfo={() => setIsIndexInfoOpen(true)}
        isOpen={isSidebarOpen}
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        isMobile={isMobile}
      />

      {/* Vùng chat chính bên phải */}
      <ChatWindow
        conversation={currentConversation}
        userName={userName}
        onSendMessage={handleSendMessage}
        onRetryLastMessage={handleRetryLastMessage}
        isLoading={isLoading}
        onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        isSidebarOpen={isSidebarOpen}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      {/* Modal thông tin Index RAG */}
      <IndexInfoModal
        isOpen={isIndexInfoOpen}
        onClose={() => setIsIndexInfoOpen(false)}
      />

      {/* Modal hỏi / đổi tên hiển thị */}
      <UserNameModal
        isOpen={isNameModalOpen}
        initialName={userName}
        onSave={(name) => {
          updateUserName(name)
          setIsNameModalOpen(false)
        }}
        onClose={() => setIsNameModalOpen(false)}
        isRequired={!userName}
      />
    </div>
  )
}
