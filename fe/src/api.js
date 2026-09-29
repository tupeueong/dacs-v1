/**
 * src/api.js
 * Quản lý toàn bộ lời gọi API của hệ thống "Trợ lý Luật Lao động".
 * Hỗ trợ chuyển đổi mượt mà giữa chế độ MOCK và BACKEND THỰC TẾ qua biến môi trường.
 */

const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true' || import.meta.env.VITE_USE_MOCK === true
const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '')

/**
 * Trợ giúp tạo độ trễ ngẫu nhiên (1.0s - 1.8s) để mô phỏng thời gian xử lý RAG chân thực
 */
const delay = (ms = 1200) => new Promise((resolve) => setTimeout(resolve, ms))

/**
 * Kho câu trả lời mẫu cho Mock Engine (theo đúng ngữ cảnh Luật Lao động Việt Nam)
 */
const MOCK_KNOWLEDGE_BASE = [
  {
    keywords: ['thử việc', 'thu viec', 'thoi gian thu viec', 'lương thử việc', 'luong thu viec'],
    answer: `### Căn cứ quy định về thời gian và tiền lương thử việc

Theo quy định của **Bộ luật Lao động 2019**, việc thử việc giữa người lao động và người sử dụng lao động tuân theo các nguyên tắc sau:

1. **Thời gian thử việc tối đa:**
   - **Không quá 180 ngày:** Đối với công việc của người quản lý doanh nghiệp theo quy định của Luật Doanh nghiệp.
   - **Không quá 60 ngày:** Đối với công việc có chức danh nghề nghiệp cần trình độ chuyên môn, kỹ thuật từ cao đẳng trở lên.
   - **Không quá 30 ngày:** Đối với công việc có chức danh nghề nghiệp cần trình độ chuyên môn, kỹ thuật trung cấp, công nhân kỹ thuật, nhân viên nghiệp vụ.
   - **Không quá 06 ngày làm việc:** Đối với công việc khác.

2. **Tiền lương trong thời gian thử việc:**
   - Tiền lương của người lao động trong thời gian thử việc do hai bên thỏa thuận nhưng **ít nhất phải bằng 85%** mức lương của công việc đó.

3. **Kết thúc thời gian thử việc:**
   - Khi kết thúc thời gian thử việc, người sử dụng lao động phải thông báo kết quả thử việc cho người lao động.
   - Trong thời gian thử việc, mỗi bên có quyền hủy bỏ hợp đồng thử việc hoặc hợp đồng lao động đã giao kết mà không cần báo trước và không phải bồi thường nếu việc làm thử không đạt yêu cầu.`,
    sources: [
      {
        doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
        article: 'Điều 25',
        clause: 'Khoản 1, 2',
        text: 'Thời gian thử việc do hai bên thỏa thuận căn cứ vào tính chất và mức độ phức tạp của công việc nhưng chỉ được thử việc một lần đối với một công việc và bảo đảm điều kiện: Không quá 180 ngày đối với công việc của người quản lý doanh nghiệp; Không quá 60 ngày đối với công việc cần trình độ từ cao đẳng trở lên; Không quá 30 ngày đối với trình độ trung cấp; Không quá 06 ngày làm việc đối với công việc khác.'
      },
      {
        doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
        article: 'Điều 26',
        clause: 'Điều 26',
        text: 'Tiền lương của người lao động trong thời gian thử việc do hai bên thỏa thuận nhưng ít nhất phải bằng 85% mức lương của công việc đó.'
      },
      {
        doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
        article: 'Điều 27',
        clause: 'Khoản 2',
        text: 'Trong thời gian thử việc, mỗi bên có quyền hủy bỏ hợp đồng thử việc hoặc hợp đồng lao động đã giao kết mà không cần báo trước và không phải bồi thường.'
      }
    ]
  },
  {
    keywords: ['nghỉ phép', 'nghi phep', 'phép năm', 'phep nam', 'nghỉ hàng năm'],
    answer: `### Quy định về chế độ nghỉ phép hằng năm (phép năm)

Theo **Điều 113 và Điều 114 Bộ luật Lao động 2019**, chế độ nghỉ phép hằng năm của người lao động được quy định như sau:

1. **Số ngày nghỉ phép hằng năm hưởng nguyên lương:**
   - **12 ngày làm việc:** Đối với người làm công việc trong điều kiện bình thường.
   - **14 ngày làm việc:** Đối với người lao động chưa thành niên, lao động là người khuyết tật, người làm nghề/công việc nặng nhọc, độc hại, nguy hiểm.
   - **16 ngày làm việc:** Đối với người làm nghề/công việc đặc biệt nặng nhọc, độc hại, nguy hiểm.
   - Người lao động làm việc chưa đủ 12 tháng thì số ngày nghỉ hằng năm theo tỷ lệ tương ứng với số tháng làm việc.

2. **Tăng ngày nghỉ theo thâm niên:**
   - Cứ đủ **05 năm làm việc** cho một người sử dụng lao động thì số ngày nghỉ hằng năm được tăng thêm tương ứng **01 ngày**.

3. **Thanh toán tiền lương cho ngày chưa nghỉ:**
   - Trường hợp do thôi việc, bị mất việc làm mà chưa nghỉ hằng năm hoặc chưa nghỉ hết số ngày nghỉ hằng năm thì được người sử dụng lao động thanh toán tiền lương cho những ngày chưa nghỉ.`,
    sources: [
      {
        doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
        article: 'Điều 113',
        clause: 'Khoản 1, 2, 6',
        text: 'Người lao động làm việc đủ 12 tháng cho một người sử dụng lao động thì được nghỉ hằng năm, hưởng nguyên lương theo hợp đồng lao động: 12 ngày làm việc đối với điều kiện bình thường; 14 ngày làm việc đối với lao động nặng nhọc, độc hại; 16 ngày làm việc đối với đặc biệt nặng nhọc, độc hại. Trường hợp do thôi việc, bị mất việc làm mà chưa nghỉ hết số ngày phép thì được thanh toán tiền lương cho những ngày chưa nghỉ.'
      },
      {
        doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
        article: 'Điều 114',
        clause: 'Điều 114',
        text: 'Cứ đủ 05 năm làm việc cho một người sử dụng lao động thì số ngày nghỉ hằng năm của người lao động theo quy định tại khoản 1 Điều 113 của Bộ luật này được tăng thêm tương ứng 01 ngày.'
      }
    ]
  },
  {
    keywords: ['chấm dứt', 'cham dut', 'đơn phương', 'don phuong', 'nghỉ việc', 'nghi viec', 'báo trước', 'bao truoc'],
    answer: `### Quyền đơn phương chấm dứt hợp đồng lao động của người lao động

Căn cứ **Điều 35 Bộ luật Lao động 2019**, người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải tuân thủ thời hạn báo trước như sau:

1. **Thời hạn báo trước thông thường:**
   - **Ít nhất 45 ngày:** Nếu làm việc theo hợp đồng lao động không xác định thời hạn.
   - **Ít nhất 30 ngày:** Nếu làm việc theo hợp đồng lao động xác định thời hạn từ 12 tháng đến 36 tháng.
   - **Ít nhất 03 ngày làm việc:** Nếu làm việc theo hợp đồng lao động xác định thời hạn dưới 12 tháng.
   - Đối với một số ngành, nghề, công việc đặc thù (như thuyền viên, lái máy bay, quản lý) thì thời hạn theo quy định của Chính phủ.

2. **Các trường hợp được nghỉ việc ngay KHÔNG CẦN báo trước:**
   - Không được bố trí đúng công việc, địa điểm làm việc hoặc không được bảo đảm điều kiện làm việc đã thỏa thuận.
   - Không được trả đủ lương hoặc trả lương không đúng thời hạn.
   - Bị người sử dụng lao động ngược đãi, đánh đập hoặc có lời nói, hành vi nhục mạ, hành vi làm ảnh hưởng đến sức khỏe, nhân phẩm.
   - Bị quấy rối tình dục tại nơi làm việc.
   - Lao động nữ mang thai phải nghỉ việc theo chỉ định của cơ sở khám chữa bệnh.
   - Đủ tuổi nghỉ hưu theo quy định, trừ trường hợp các bên có thỏa thuận khác.`,
    sources: [
      {
        doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
        article: 'Điều 35',
        clause: 'Khoản 1',
        text: 'Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước cho người sử dụng lao động: Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn; Ít nhất 30 ngày nếu làm việc theo hợp đồng lao động xác định thời hạn từ 12 tháng đến 36 tháng; Ít nhất 03 ngày làm việc nếu làm việc theo hợp đồng xác định thời hạn dưới 12 tháng.'
      },
      {
        doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
        article: 'Điều 35',
        clause: 'Khoản 2',
        text: 'Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước trong các trường hợp: Không được bố trí đúng công việc, địa điểm làm việc; không được trả đủ lương hoặc trả chậm; bị ngược đãi, quấy rối tình dục; lao động nữ mang thai phải nghỉ theo chỉ định y tế...'
      }
    ]
  },
  {
    keywords: ['bảo hiểm', 'bao hiem', 'bhxh', 'ốm đau', 'om dau', 'thai sản', 'thai san'],
    answer: `### Căn cứ chế độ bảo hiểm xã hội (BHXH) bắt buộc

Theo quy định pháp luật về Bảo hiểm xã hội và Bộ luật Lao động:

1. **Đối tượng tham gia BHXH bắt buộc:**
   - Người làm việc theo hợp đồng lao động không xác định thời hạn, hợp đồng lao động xác định thời hạn từ đủ 01 tháng trở lên.

2. **Chế độ ốm đau:**
   - Thời gian hưởng chế độ ốm đau trong năm: Tối đa từ 30 đến 60 ngày tùy theo điều kiện làm việc (bình thường hay nặng nhọc, độc hại) và thời gian đóng BHXH.
   - Mức hưởng: Bằng **75% mức tiền lương đóng BHXH** của tháng liền kề trước khi nghỉ việc.

3. **Chế độ thai sản:**
   - Lao động nữ sinh con được nghỉ việc hưởng chế độ thai sản trước và sau khi sinh con là **06 tháng**; trường hợp sinh đôi trở lên thì từ con thứ hai trở đi, cứ mỗi con, người mẹ được nghỉ thêm 01 tháng.
   - Mức trợ cấp một lần khi sinh con bằng **02 lần mức tham chiếu/lương cơ sở** cho mỗi con.`,
    sources: [
      {
        doc_title: 'Luật Bảo hiểm xã hội số 41/2024/QH15',
        article: 'Điều 42 & Điều 45',
        clause: 'Khoản 1',
        text: 'Người lao động nghỉ việc do ốm đau, tai nạn mà không phải tai nạn lao động có xác nhận của cơ sở khám bệnh, chữa bệnh có thẩm quyền thì được hưởng trợ cấp ốm đau bằng 75% mức tiền lương làm căn cứ đóng bảo hiểm xã hội.'
      },
      {
        doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
        article: 'Điều 139',
        clause: 'Khoản 1',
        text: 'Lao động nữ được nghỉ thai sản trước và sau khi sinh con là 06 tháng; thời gian nghỉ trước khi sinh không quá 02 tháng. Trường hợp lao động nữ sinh đôi trở lên thì tính từ con thứ 02 trở đi, cứ mỗi con, người mẹ được nghỉ thêm 01 tháng.'
      }
    ]
  }
]

/**
 * Trả lời mặc định cho Mock khi câu hỏi không khớp từ khóa đặc biệt
 */
const DEFAULT_MOCK_ANSWER = (query) => ({
  answer: `### Căn cứ tư vấn pháp lý về: "${query}"

Sau khi đối soát với cơ sở dữ liệu pháp luật lao động hiện hành (Bộ luật Lao động 2019 cùng các Nghị định, Thông tư hướng dẫn), chúng tôi xin đưa ra các điểm lưu ý pháp lý:

1. **Nguyên tắc áp dụng pháp luật:**
   - Mọi thỏa thuận trong hợp đồng lao động, thỏa ước lao động tập thể hoặc nội quy lao động không được trái với các quy định bảo vệ tối thiểu cho người lao động theo pháp luật lao động Việt Nam.
   - Trường hợp có nội dung mâu thuẫn hoặc chưa rõ, ưu tiên áp dụng văn bản có hiệu lực pháp lý cao hơn hoặc văn bản chuyên ngành có lợi hơn cho người lao động.

2. **Trách nhiệm của các bên:**
   - Người sử dụng lao động có nghĩa vụ ban hành quy chế rõ ràng, tham khảo ý kiến của tổ chức đại diện người lao động tại cơ sở khi sửa đổi quy định nội bộ.
   - Người lao động có quyền khiếu nại hoặc yêu cầu hòa giải viên lao động can thiệp nếu quyền và lợi ích hợp pháp bị xâm phạm.

*Lưu ý: Để có phương án soạn thảo văn bản hoặc giải quyết tranh chấp cụ thể, đề nghị đối chiếu trực tiếp các điều khoản tương ứng bên dưới.*`,
  sources: [
    {
      doc_title: 'Bộ luật Lao động 2019 (Luật số 45/2019/QH14)',
      article: 'Điều 7',
      clause: 'Khoản 1',
      text: 'Quan hệ lao động giữa người lao động, người sử dụng lao động được xác lập qua đối thoại, thương lượng, thỏa thuận theo nguyên tắc tự nguyện, thiện chí, bình đẳng, hợp tác, tôn trọng quyền và lợi ích hợp pháp của nhau.'
    },
    {
      doc_title: 'Nghị định số 145/2020/NĐ-CP của Chính phủ',
      article: 'Điều 69',
      clause: 'Khoản 2',
      text: 'Nội quy lao động phải được thông báo đến người lao động và niêm yết ở những nơi cần thiết tại nơi làm việc. Nội quy lao động không được trái với pháp luật về lao động và quy định của pháp luật có liên quan.'
    }
  ]
})

/**
 * Helper chuẩn hóa lỗi từ backend format { detail: { message } } hoặc các biến thể
 */
function extractErrorMessage(errorData, fallbackText = 'Đã xảy ra lỗi không xác định') {
  if (!errorData) return fallbackText
  if (typeof errorData === 'string') return errorData
  if (errorData.detail) {
    if (typeof errorData.detail === 'object' && errorData.detail.message) {
      return errorData.detail.message
    }
    if (typeof errorData.detail === 'string') {
      return errorData.detail
    }
  }
  if (errorData.message) return errorData.message
  return fallbackText
}

/**
 * 1. API: Kiểm tra trạng thái Backend
 * GET /api/health
 * Trả về: { status: "ok" | "error", checks: { [key: string]: boolean } }
 */
export async function checkHealth() {
  if (USE_MOCK) {
    await delay(350)
    // Mock health response
    return {
      status: 'ok',
      service: 'labor-law-rag-agent',
      checks: {
        database: true,
        vector_index: true,
        gemini_api: true,
        retriever: true
      },
      message: 'Hệ thống sẵn sàng phục vụ tra cứu'
    }
  }

  try {
    const res = await fetch(`${API_URL}/api/health`, {
      method: 'GET',
      headers: {
        Accept: 'application/json'
      }
    })

    if (!res.ok) {
      const errorJson = await res.json().catch(() => null)
      const message = extractErrorMessage(errorJson, `Lỗi kiểm tra dịch vụ (${res.status})`)
      return {
        status: 'error',
        checks: errorJson?.checks || { backend: false },
        message
      }
    }

    const data = await res.json()
    return {
      status: data.status || 'ok',
      checks: data.checks || { backend: true, vector_index: true },
      message: data.message || 'Hệ thống hoạt động tốt'
    }
  } catch (err) {
    return {
      status: 'error',
      checks: { network: false },
      message: err.message || 'Không thể kết nối đến máy chủ backend'
    }
  }
}

/**
 * 2. API: Lấy thông tin RAG Vector Index
 * GET /api/index-info
 * Trả về: { chunk_count, article_count, embedding_dimension, distance_metric, ... }
 */
export async function getIndexInfo() {
  if (USE_MOCK) {
    await delay(500)
    return {
      status: 'ready',
      corpus_name: 'Dữ liệu pháp điển & Luật Lao động Việt Nam',
      article_count: 1662,
      chunk_count: 3301,
      embedding_dimension: 768,
      distance_metric: 'cosine',
      embedding_model: 'truro7/vn-law-embedding',
      rerank_model: 'BAAI/bge-reranker-v2-m3',
      generator_model: 'gemini-3.5-flash-lite',
      active_pointer: 'legal_data/vectorstore_versions/current.json',
      retrieval_accuracy: '100% (8/8 in-domain)',
      last_updated: '2026-09-28T08:30:00+07:00'
    }
  }

  try {
    const res = await fetch(`${API_URL}/api/index-info`, {
      method: 'GET',
      headers: {
        Accept: 'application/json'
      }
    })

    if (!res.ok) {
      const errorJson = await res.json().catch(() => null)
      const message = extractErrorMessage(errorJson, `Không thể lấy thông tin index (${res.status})`)
      throw new Error(message)
    }

    return await res.json()
  } catch (err) {
    throw new Error(err.message || 'Lỗi khi truy vấn thông tin chỉ mục RAG')
  }
}

/**
 * 3. API: Gửi câu hỏi pháp lý và nhận câu trả lời RAG
 * POST /api/chat
 * Payload gửi đi: { message: string }
 * (CHÚ Ý: Hiện tại hợp đồng chỉ nhận một câu hỏi mới nhất.
 *  Khi backend hỗ trợ hội thoại nhiều lượt (multi-turn), ta sẽ mở rộng payload thành:
 *  { message: string, history: messages.map(m => ({ role: m.role, content: m.content })) }
 * )
 *
 * Trả về: { answer: string, sources: Array<{ doc_title, article, clause, text }> }
 */
export async function sendChatMessage(question, conversationHistory = []) {
  const trimmed = question?.trim() || ''

  // === MÔ PHỎNG LỖI MOCK (Error simulation trigger) ===
  // Người dùng có thể gõ các lệnh sau vào ô chat để test giao diện lỗi:
  // /lỗi502, /lỗi503, /lỗi400, /lỗi429, /lỗi500, /error
  if (USE_MOCK) {
    await delay(1200)

    const lower = trimmed.toLowerCase()
    if (lower === '/lỗi502' || lower === '/error502') {
      const err = new Error('Máy chủ upstream quá tải hoặc gặp sự cố Gateway (502 Bad Gateway)')
      err.status = 502
      err.detail = { message: 'Máy chủ upstream quá tải hoặc gặp sự cố Gateway (502 Bad Gateway)' }
      throw err
    }
    if (lower === '/lỗi503' || lower === '/error503') {
      const err = new Error('Dịch vụ RAG AI đang bảo trì đột xuất, vui lòng thử lại sau vài phút (503 Service Unavailable)')
      err.status = 503
      err.detail = { message: 'Dịch vụ RAG AI đang bảo trì đột xuất, vui lòng thử lại sau vài phút (503 Service Unavailable)' }
      throw err
    }
    if (lower === '/lỗi400' || lower === '/error400') {
      const err = new Error('Yêu cầu không hợp lệ hoặc câu hỏi vi phạm chính sách kiểm duyệt (400 Bad Request)')
      err.status = 400
      err.detail = { message: 'Yêu cầu không hợp lệ hoặc câu hỏi vi phạm chính sách kiểm duyệt (400 Bad Request)' }
      throw err
    }
    if (lower === '/lỗi429' || lower === '/error429') {
      const err = new Error('Hệ thống đang tiếp nhận quá nhiều yêu cầu đồng thời, vui lòng chờ trong giây lát (429 Too Many Requests)')
      err.status = 429
      err.detail = { message: 'Hệ thống đang tiếp nhận quá nhiều yêu cầu đồng thời, vui lòng chờ trong giây lát (429 Too Many Requests)' }
      throw err
    }
    if (lower === '/lỗi500' || lower === '/error' || lower === '/loi') {
      const err = new Error('Lỗi nội bộ khi khởi tạo pipeline truy hồi RAG (500 Internal Server Error)')
      err.status = 500
      err.detail = { message: 'Lỗi nội bộ khi khởi tạo pipeline truy hồi RAG (500 Internal Server Error)' }
      throw err
    }

    // Tìm câu trả lời mock phù hợp theo từ khóa
    const matched = MOCK_KNOWLEDGE_BASE.find((item) =>
      item.keywords.some((kw) => lower.includes(kw))
    )

    if (matched) {
      return {
        answer: matched.answer,
        sources: matched.sources
      }
    }

    return DEFAULT_MOCK_ANSWER(trimmed)
  }

  // === GỌI BACKEND THẬT ===
  try {
    // CHÚ Ý MỞ RỘNG KHI HỖ TRỢ MULTI-TURN:
    // const bodyPayload = {
    //   message: trimmed,
    //   history: conversationHistory.map(m => ({ role: m.role, content: m.content }))
    // }
    const bodyPayload = {
      message: trimmed
    }

    const res = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify(bodyPayload)
    })

    if (!res.ok) {
      const errorJson = await res.json().catch(() => null)
      const errorMsg = extractErrorMessage(errorJson, `Lỗi máy chủ (${res.status} ${res.statusText})`)
      const err = new Error(errorMsg)
      err.status = res.status
      err.detail = errorJson?.detail || { message: errorMsg }
      throw err
    }

    const data = await res.json()
    // Chuẩn hóa cấu trúc trả về theo đúng hợp đồng: { answer, sources }
    return {
      answer: data.answer || data.content || data.response || 'Không nhận được nội dung trả lời từ AI.',
      sources: Array.isArray(data.sources) ? data.sources : []
    }
  } catch (err) {
    if (err.detail) throw err
    const friendlyError = new Error(err.message || 'Không thể kết nối đến máy chủ API')
    friendlyError.status = err.status || 500
    friendlyError.detail = { message: friendlyError.message }
    throw friendlyError
  }
}
