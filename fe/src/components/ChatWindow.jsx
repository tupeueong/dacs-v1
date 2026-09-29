import { useEffect, useRef } from 'react'
import {
  PanelLeft,
  Moon,
  Sun,
  Scale,
  Sparkles,
  ShieldCheck,
  Clock,
  Briefcase,
  HelpCircle
} from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import { MessageBubble } from './MessageBubble'
import { Composer } from './Composer'

const SUGGESTED_PROMPTS = [
  {
    icon: Clock,
    title: 'Thời gian & Lương thử việc',
    text: 'Thời gian thử việc tối đa theo luật là bao lâu và tiền lương thử việc được tính thế nào?'
  },
  {
    icon: Briefcase,
    title: 'Chế độ nghỉ phép năm',
    text: 'Quy định về số ngày nghỉ phép hằng năm và cách tăng thêm ngày phép theo thâm niên làm việc?'
  },
  {
    icon: ShieldCheck,
    title: 'Chế độ ốm đau & BHXH',
    text: 'Thời gian và mức hưởng trợ cấp ốm đau theo quy định của Luật Bảo hiểm xã hội hiện hành?'
  },
  {
    icon: HelpCircle,
    title: 'Đơn phương chấm dứt HĐLĐ',
    text: 'Người lao động muốn đơn phương chấm dứt hợp đồng thì cần báo trước bao nhiêu ngày?'
  }
]

export function ChatWindow({
  conversation,
  userName,
  onSendMessage,
  onRetryLastMessage,
  isLoading,
  onToggleSidebar,
  isSidebarOpen,
  theme,
  onToggleTheme
}) {
  const messagesEndRef = useRef(null)
  const messages = conversation?.messages || []

  // Tự động cuộn xuống cuối khi có tin nhắn mới hoặc khi đang sinh câu trả lời
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handlePromptClick = (text) => {
    if (isLoading) return
    onSendMessage(text)
  }

  return (
    <main className="chat-window-root">
      {/* Header mỏng trên cùng */}
      <header className="chat-header">
        <div className="flex items-center gap-2 overflow-hidden flex-1 mr-2">
          {!isSidebarOpen && (
            <button
              type="button"
              onClick={onToggleSidebar}
              className="chat-header-btn"
              title="Mở thanh bên"
              aria-label="Mở thanh bên"
            >
              <PanelLeft size={18} />
            </button>
          )}
          <div className="chat-header-title-wrap truncate">
            <h1 className="chat-header-title truncate">
              {conversation?.title || 'Cuộc trò chuyện mới'}
            </h1>
          </div>
        </div>

        <div className="chat-header-actions">
          {/* Badge trạng thái backend */}
          <StatusBadge />

          {/* Nút đổi giao diện Sáng / Tối */}
          <button
            type="button"
            onClick={onToggleTheme}
            className="chat-header-btn"
            title={theme === 'dark' ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối'}
            aria-label="Chuyển chế độ giao diện"
          >
            {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        </div>
      </header>

      {/* Vùng hiển thị nội dung tin nhắn */}
      <div className="chat-messages-container">
        <div className="chat-messages-inner">
          {messages.length === 0 ? (
            /* Cuộc trò chuyện trống: Lời chào và gợi ý */
            <div className="chat-empty-state">
              <div className="chat-empty-icon">
                <Scale size={28} />
              </div>
              <h2 className="chat-empty-greeting">
                Xin chào, {userName ? userName : 'Quý khách'}!
              </h2>
              <p className="chat-empty-desc">
                Tôi là <strong>Trợ lý Luật Lao động</strong> ứng dụng công nghệ RAG. Tôi có thể
                hỗ trợ tra cứu quy định pháp luật, soạn thảo điều khoản hợp đồng và giải đáp
                chế độ người lao động chính xác kèm trích dẫn văn bản gốc.
              </p>

              <div className="chat-suggestions-grid">
                {SUGGESTED_PROMPTS.map((item, idx) => {
                  const Icon = item.icon
                  return (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handlePromptClick(item.text)}
                      className="chat-suggestion-card"
                    >
                      <div className="chat-suggestion-header">
                        <Icon size={16} className="text-amber-600 dark:text-amber-400" />
                        <span className="chat-suggestion-title">{item.title}</span>
                      </div>
                      <p className="chat-suggestion-text">{item.text}</p>
                    </button>
                  )
                })}
              </div>
            </div>
          ) : (
            /* Danh sách các bong bóng tin nhắn */
            <div className="chat-messages-stream">
              {messages.map((msg, index) => {
                const isLastAi =
                  msg.role === 'assistant' && index === messages.length - 1
                return (
                  <MessageBubble
                    key={index}
                    message={msg}
                    onRetry={isLastAi && msg.error ? onRetryLastMessage : undefined}
                    isLastAiMessage={isLastAi}
                  />
                )
              })}

              {/* Hiệu ứng 3 chấm nhảy khi AI đang tra cứu & sinh câu trả lời */}
              {isLoading && (
                <div className="message-row message-row-assistant">
                  <div className="message-assistant-avatar">
                    <Scale size={16} />
                  </div>
                  <div className="message-assistant-body">
                    <div className="typing-indicator-card">
                      <div className="typing-dots">
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                      </div>
                      <span className="typing-label">
                        Trợ lý đang đối soát cơ sở dữ liệu luật...
                      </span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Ô nhập câu hỏi dưới cùng */}
      <footer className="chat-footer-wrapper">
        <Composer onSend={onSendMessage} isLoading={isLoading} />
      </footer>
    </main>
  )
}
