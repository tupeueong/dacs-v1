import { useState, useEffect, useCallback, useMemo } from 'react'

const STORAGE_KEY = 'law_rag_conversations_v1'
const USER_KEY = 'law_rag_user_name_v1'

/**
 * Trợ giúp sinh ID duy nhất cho cuộc trò chuyện
 */
export function generateConversationId() {
  return 'conv_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9)
}

/**
 * Làm sạch và chuẩn hóa tiêu đề cuộc trò chuyện từ câu hỏi đầu tiên của người dùng:
 * - Loại bỏ các ký tự markdown (#, *, `, >, -, _, ~, [, ], (, ), ...)
 * - Chuẩn hóa khoảng trắng thừa
 * - Giới hạn ~40 ký tự kèm dấu "..."
 */
export function sanitizeTitle(rawText) {
  if (!rawText || typeof rawText !== 'string') return 'Cuộc trò chuyện mới'
  const cleaned = rawText
    .replace(/[#*`>_~\[\]()\-+]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return 'Cuộc trò chuyện mới'
  return cleaned.length > 40 ? cleaned.substring(0, 40).trim() + '...' : cleaned
}

/**
 * Đọc an toàn từ LocalStorage với try/catch
 */
function loadFromStorage(key, fallbackValue) {
  try {
    const item = window.localStorage.getItem(key)
    return item ? JSON.parse(item) : fallbackValue
  } catch (err) {
    console.error(`Lỗi đọc localStorage [${key}]:`, err)
    return fallbackValue
  }
}

/**
 * Ghi an toàn vào LocalStorage với try/catch
 */
function saveToStorage(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch (err) {
    console.error(`Lỗi ghi localStorage [${key}]:`, err)
  }
}

/**
 * Đọc và làm sạch dữ liệu cuộc trò chuyện từ LocalStorage:
 * - Loại bỏ các cuộc rỗng hoặc các cuộc bị lỗi không có tin nhắn nào của user
 * - Chuẩn hóa tiêu đề nếu trước đó từng bị dính ký tự markdown
 */
function loadAndCleanConversations() {
  const rawList = loadFromStorage(STORAGE_KEY, [])
  if (!Array.isArray(rawList)) return []

  return rawList
    .filter((conv) => {
      if (!conv || !conv.id || !Array.isArray(conv.messages) || conv.messages.length === 0) {
        return false
      }
      // Bắt buộc phải có ít nhất 1 tin nhắn của người dùng
      return conv.messages.some((m) => m.role === 'user')
    })
    .map((conv) => {
      const firstUserMsg = conv.messages.find((m) => m.role === 'user')
      return {
        ...conv,
        title: sanitizeTitle(firstUserMsg ? firstUserMsg.content : conv.title)
      }
    })
}

/**
 * Hook quản lý trạng thái các cuộc trò chuyện và đồng bộ LocalStorage
 */
export function useConversations() {
  const [conversations, setConversations] = useState(() => {
    return loadAndCleanConversations()
  })

  // ID của cuộc trò chuyện đang được chọn. 'draft' nghĩa là phiên chat mới chưa gửi tin
  const [activeId, setActiveId] = useState('draft')

  // Tên hiển thị của người dùng
  const [userName, setUserName] = useState(() => {
    return loadFromStorage(USER_KEY, '')
  })

  // Đồng bộ danh sách conversations vào localStorage mỗi khi thay đổi
  useEffect(() => {
    saveToStorage(STORAGE_KEY, conversations)
  }, [conversations])

  // Lưu tên hiển thị vào localStorage
  const updateUserName = useCallback((name) => {
    const trimmed = name.trim()
    setUserName(trimmed)
    saveToStorage(USER_KEY, trimmed)
  }, [])

  // Bắt đầu một cuộc trò chuyện mới (ở trạng thái draft)
  const createNewConversation = useCallback(() => {
    setActiveId('draft')
  }, [])

  // Chọn cuộc trò chuyện theo ID
  const selectConversation = useCallback((id) => {
    setActiveId(id)
  }, [])

  // Cuộc trò chuyện hiện tại đang mở
  const currentConversation = useMemo(() => {
    if (activeId === 'draft') {
      return {
        id: 'draft',
        title: 'Cuộc trò chuyện mới',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: []
      }
    }
    return (
      conversations.find((c) => c.id === activeId) || {
        id: 'draft',
        title: 'Cuộc trò chuyện mới',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: []
      }
    )
  }, [conversations, activeId])

  /**
   * Thêm tin nhắn của NGƯỜI DÙNG vào cuộc trò chuyện có ID cụ thể:
   * - Nếu cuộc trò chuyện chưa tồn tại trong danh sách, TẠO MỚI ngay với convId truyền vào
   * - Tiêu đề ĐƯỢC THIẾT LẬP DUY NHẤT một lần từ nội dung câu hỏi đầu tiên của người dùng
   * - Cập nhật dạng functional setConversations(prev => ...) an toàn tuyệt đối
   */
  const addUserMessage = useCallback((convId, content) => {
    const now = new Date().toISOString()
    const userMsg = {
      role: 'user',
      content,
      sources: [],
      error: null,
      createdAt: now
    }

    setConversations((prevList) => {
      const existingIndex = prevList.findIndex((c) => c.id === convId)

      if (existingIndex === -1) {
        // Cuộc trò chuyện mới: đặt tiêu đề từ câu hỏi đầu tiên đã được làm sạch
        const newConversation = {
          id: convId,
          title: sanitizeTitle(content),
          createdAt: now,
          updatedAt: now,
          messages: [userMsg]
        }
        return [newConversation, ...prevList]
      }

      // Cuộc trò chuyện đã tồn tại: thêm tin nhắn vào
      return prevList.map((conv) => {
        if (conv.id === convId) {
          return {
            ...conv,
            updatedAt: now,
            messages: [...conv.messages, userMsg]
          }
        }
        return conv
      })
    })
  }, [])

  /**
   * Thêm tin nhắn của TRỢ LÝ AI vào cuộc trò chuyện có ID cụ thể:
   * - Tuyệt đối KHÔNG tạo cuộc trò chuyện mới nếu không tìm thấy convId
   * - Không bao giờ sửa tiêu đề cuộc trò chuyện
   * - Cập nhật dạng functional setConversations(prev => ...)
   */
  const addAssistantMessage = useCallback((convId, content, sources = [], error = null) => {
    const now = new Date().toISOString()
    const assistantMsg = {
      role: 'assistant',
      content: content || '',
      sources: Array.isArray(sources) ? sources : [],
      error: error || null,
      createdAt: now
    }

    setConversations((prevList) => {
      const existingIndex = prevList.findIndex((c) => c.id === convId)
      if (existingIndex === -1) {
        console.warn(`[addAssistantMessage] Không tìm thấy cuộc trò chuyện id="${convId}". Tuyệt đối không tạo cuộc mới.`);
        return prevList
      }

      return prevList.map((conv) => {
        if (conv.id === convId) {
          return {
            ...conv,
            updatedAt: now,
            messages: [...conv.messages, assistantMsg]
          }
        }
        return conv
      })
    })
  }, [])

  /**
   * Xóa tin nhắn cuối cùng (dùng khi thử lại câu hỏi bị lỗi)
   */
  const removeLastMessage = useCallback((convId) => {
    const now = new Date().toISOString()
    setConversations((prevList) => {
      return prevList.map((conv) => {
        if (conv.id === convId && conv.messages.length > 0) {
          return {
            ...conv,
            updatedAt: now,
            messages: conv.messages.slice(0, -1)
          }
        }
        return conv
      })
    })
  }, [])

  /**
   * Đổi tên cuộc trò chuyện
   */
  const renameConversation = useCallback((id, newTitle) => {
    const trimmed = newTitle.trim()
    if (!trimmed) return
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title: trimmed, updatedAt: new Date().toISOString() } : c))
    )
  }, [])

  /**
   * Xóa một cuộc trò chuyện
   */
  const deleteConversation = useCallback(
    (id) => {
      setConversations((prev) => {
        const nextList = prev.filter((c) => c.id !== id)
        if (activeId === id) {
          if (nextList.length > 0) {
            setActiveId(nextList[0].id)
          } else {
            setActiveId('draft')
          }
        }
        return nextList
      })
    },
    [activeId]
  )

  /**
   * Xóa toàn bộ lịch sử
   */
  const clearAllConversations = useCallback(() => {
    setConversations([])
    setActiveId('draft')
    try {
      window.localStorage.removeItem(STORAGE_KEY)
    } catch (err) {
      console.error('Lỗi khi xóa lịch sử trong localStorage:', err)
    }
  }, [])

  return {
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
  }
}
