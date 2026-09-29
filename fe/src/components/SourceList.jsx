import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronUp, FileText, ExternalLink } from 'lucide-react'

export function SourceList({ sources = [] }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [selectedSource, setSelectedSource] = useState(null)

  if (!sources || sources.length === 0) return null

  return (
    <div className="source-list-container">
      {/* Nút thu gọn / mở rộng danh sách căn cứ */}
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="source-toggle-btn"
        aria-expanded={isExpanded}
      >
        <div className="flex items-center gap-2">
          <BookOpen size={15} className="text-amber-600 dark:text-amber-400" />
          <span className="font-semibold text-xs tracking-wide uppercase">
            Căn cứ pháp lý
          </span>
          <span className="source-count-badge">{sources.length}</span>
        </div>
        <div className="flex items-center text-xs opacity-75">
          <span className="mr-1">{isExpanded ? 'Thu gọn' : 'Xem chi tiết'}</span>
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {/* Nội dung danh sách khi mở rộng */}
      {isExpanded && (
        <div className="source-items-wrapper">
          <div className="source-items-grid">
            {sources.map((item, index) => {
              const isSelected = selectedSource === index
              return (
                <div
                  key={index}
                  className={`source-card ${isSelected ? 'source-card-active' : ''}`}
                >
                  <div className="source-card-header">
                    <div className="source-tags">
                      {item.article && (
                        <span className="source-tag-article">{item.article}</span>
                      )}
                      {item.clause && (
                        <span className="source-tag-clause">{item.clause}</span>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => setSelectedSource(isSelected ? null : index)}
                      className="source-view-text-btn"
                      title="Xem nội dung văn bản trích dẫn"
                    >
                      <FileText size={13} className="mr-1" />
                      <span>{isSelected ? 'Đóng trích dẫn' : 'Đoạn gốc'}</span>
                    </button>
                  </div>

                  <div className="source-doc-title">
                    <span className="font-medium text-xs text-neutral-800 dark:text-neutral-200">
                      {item.doc_title || 'Văn bản quy phạm pháp luật'}
                    </span>
                  </div>

                  {/* Hiển thị đoạn text trích dẫn gốc khi người dùng bấm xem */}
                  {isSelected && item.text && (
                    <div className="source-original-text">
                      <div className="source-original-text-label">Trích dẫn nguyên văn:</div>
                      <p className="source-original-text-content">{item.text}</p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
