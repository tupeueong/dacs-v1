import { useState, useCallback } from 'react'
import Markdown from 'react-markdown'
import { Copy, Check, RotateCcw, AlertCircle, Scale, User } from 'lucide-react'
import { SourceList } from './SourceList'

export function MessageBubble({ message, onRetry, isLastAiMessage = false }) {
  const [copied, setCopied] = useState(false)
  const isUser = message.role === 'user'

  const handleCopy = useCallback(async () => {
    if (!message.content) return
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Không thể sao chép văn bản:', err)
    }
  }, [message.content])

  if (isUser) {
    return (
      <div className="message-row message-row-user">
        <div className="message-bubble message-bubble-user">
          <div className="message-user-content">{message.content}</div>
        </div>
      </div>
    )
  }

  // AI Message
  return (
    <div className="message-row message-row-assistant">
      <div className="message-assistant-avatar" title="Trợ lý Luật Lao động">
        <Scale size={16} />
      </div>

      <div className="message-assistant-body">
        {/* Trường hợp tin nhắn bị lỗi */}
        {message.error ? (
          <div className="message-error-card">
            <div className="flex items-start gap-2.5">
              <AlertCircle size={18} className="text-rose-500 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <div className="font-semibold text-sm text-rose-700 dark:text-rose-300">
                  Không thể hoàn thành câu trả lời
                </div>
                <div className="text-xs text-rose-600/90 dark:text-rose-400/90 mt-1 leading-relaxed">
                  {message.error.message || message.content || 'Đã xảy ra sự cố khi kết nối đến bộ máy AI.'}
                </div>
                {onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="message-retry-btn"
                  >
                    <RotateCcw size={13} className="mr-1.5" />
                    <span>Thử lại câu hỏi này</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="message-bubble message-bubble-assistant">
            {/* Nội dung Markdown */}
            <div className="markdown-prose">
              <Markdown>{message.content || ''}</Markdown>
            </div>

            {/* Thanh công cụ phụ (Sao chép + Timestamp) */}
            <div className="message-footer-bar">
              <button
                type="button"
                onClick={handleCopy}
                className="message-action-btn"
                title="Sao chép nội dung câu trả lời"
              >
                {copied ? (
                  <>
                    <Check size={13} className="text-emerald-500" />
                    <span className="text-emerald-500 font-medium">Đã sao chép</span>
                  </>
                ) : (
                  <>
                    <Copy size={13} />
                    <span>Sao chép</span>
                  </>
                )}
              </button>
            </div>

            {/* Căn cứ pháp lý RAG */}
            {message.sources && message.sources.length > 0 && (
              <SourceList sources={message.sources} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
