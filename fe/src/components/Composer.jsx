import { useState, useRef, useEffect, useCallback } from 'react'
import { ArrowUp, CornerDownLeft, Sparkles } from 'lucide-react'

export function Composer({ onSend, isLoading }) {
  const [input, setInput] = useState('')
  const textareaRef = useRef(null)

  // Tự động co giãn chiều cao textarea theo nội dung nhập
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const newHeight = Math.min(el.scrollHeight, 200) // Tối đa 200px
    el.style.height = `${Math.max(newHeight, 44)}px`
  }, [input])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (e.nativeEvent?.isComposing) return
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed)
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = '44px'
    }
  }, [input, isLoading, onSend])

  return (
    <div className="composer-container">
      <div className="composer-box">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Hỏi về quy định lao động, điều khoản hợp đồng, BHXH... (Enter để gửi)"
          rows={1}
          className="composer-textarea"
          disabled={isLoading}
          aria-label="Khung nhập câu hỏi pháp lý"
        />

        <div className="composer-actions">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!input.trim() || isLoading}
            className="composer-send-btn"
            title={isLoading ? 'Đang phân tích...' : 'Gửi câu hỏi (Enter)'}
            aria-label="Gửi câu hỏi"
          >
            {isLoading ? (
              <span className="composer-spinner" />
            ) : (
              <ArrowUp size={18} strokeWidth={2.4} />
            )}
          </button>
        </div>
      </div>

      <div className="composer-footer">
        <span className="composer-disclaimer">
          Nội dung mang tính tham khảo, không thay thế tư vấn pháp lý.
        </span>
      </div>
    </div>
  )
}
