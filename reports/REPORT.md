# Lab 25B — Report

**Họ tên / nhóm:** Nguyễn Hải Long (202602471)  **Commit:** `2fb2ed5`  **Điểm tự động (`make grade`):** 84.0 / 88 (84/84 public test points)

> Mọi nhận định phải có số. Dán số từ `reports/gameday/*.json`, `reports/workflows.json`, `reports/slo.json`.

## 1. Kết quả Game Day (naive vs của bạn)

| Băng | Client | availability | p95 (s) | amplification | retry_ratio | cost/turn | recovery (s) | PASS? |
|---|---|---:|---:|---:|---:|---:|---:|:---:|
| G1 | naive | 0.7194 | 7.157 | 7.738 | 6.738 | 2.163 | 4.0 | FAIL |
| G1 | yours | 1.0000 | 4.786 | 1.064 | 0.001 | 2.101 | 0.0 | PASS |
| G2 | naive | 0.4560 | 15.034 | 9.904 | 8.904 | 4.627 | 155.0 | FAIL |
| G2 | yours | 1.0000 | 9.789 | 1.032 | 0.003 | 2.100 | 0.0 | PASS |
| G3 | naive | 1.0000 | 4.768 | 1.164 | 0.164 | 2.328 | 0.0 | FAIL |
| G3 | yours | 1.0000 | 4.714 | 1.036 | 0.016 | 2.110 | 0.0 | PASS |
| G4 | naive | 1.0000 | 13.764 | 1.004 | 0.004 | 2.008 | 0.0 | FAIL |
| G4 | yours | 1.0000 | 5.536 | 1.016 | 0.003 | 2.091 | 0.0 | PASS |
| G5 | naive | 0.3699 | 5.359 | 17.030 | 16.030 | 2.124 | N/A | FAIL |
| G5 | yours | 0.8108 | 5.578 | 1.003 | 0.002 | 2.521 | N/A | PASS |
| G6 | naive | 0.5170 | 4.836 | 12.344 | 11.344 | 2.009 | 0.0 | FAIL |
| G6 | yours | 1.0000 | 6.369 | 1.058 | 0.022 | 2.185 | 0.0 | PASS |

## 2. Cấu hình client và lý do

| Tham số | Giá trị | Vì sao (dựa trên băng nào, số liệu nào) |
|---|---:|---|
| attempt_timeout_s | 8.0 | Độ trễ trung vị của các provider là 1.2–1.8s. Ngưỡng 8.0s đủ cho p99 xử lý bình thường nhưng cắt đứt sớm các request treo (G6, G4), chừa đủ thời gian trong turn deadline 30s để failover sang provider tiếp theo. Ở thí nghiệm 30s (G6), availability sụt xuống 94.88% vì hết deadline người dùng. |
| max_attempts_per_provider | 2 | Cho phép 1 lần retry tại chỗ trên cùng provider khi gặp lỗi tạm thời (rate limit nhẹ, transient 503), nhưng lập tức failover ở lần lỗi thứ 2. Tránh dồn toàn bộ lượt thử vào một provider đang hỏng (G2, G6). |
| backoff_base_s / cap_s | 0.25 / 4.0 | Áp dụng Full Jitter Exponential Backoff $U(0, \min(cap, base \times 2^a))$. Base 0.25s giúp retry nhanh nếu lỗi thoáng qua, cap 4.0s giới hạn thời gian chờ để không vi phạm turn deadline 30s. Kết hợp tôn trọng triệt để `Retry-After`, giảm vi phạm `retry_after_violations` từ 36,027 (naive ở G1) về 0. |
| retry_budget_ratio | 0.1 | Khóa cứng tổng số lượt retry tối đa không vượt quá 10% lưu lượng ban đầu. Trong kịch bản G2 misconfigured breaker, cơ chế này chặn đứng retry storm, giữ availability 99.87% (so với 96.49% khi tắt budget) và triệt tiêu trễ hồi phục (0s vs 30s). |
| breaker.window_size / min_calls | 20 / 10 | Sliding window 20 calls với tối thiểu 10 calls để bắt đầu tính tỷ lệ lỗi, tránh ngắt mạch nhầm khi lưu lượng ban đầu quá nhỏ hoặc gặp 1-2 lỗi ngẫu nhiên, nhưng phản ứng đủ nhanh (dưới 2.5s ở tải 4 rps) khi có sự cố diện rộng. |
| breaker.failure_rate_threshold | 0.5 | Ngắt mạch khi tỷ lệ lỗi server/hạ tầng $\ge 50\%$. Ngưỡng này tách bạch lỗi ngẫu nhiên cá lẻ với sự cố hệ thống nghiêm trọng (như G2 75% GPU drop, G3 30% brownout không ngắt nhầm nhưng G2 ngắt dứt khoát). |
| breaker.slow_call_s | 5.0 | Bắt các cuộc gọi suy giảm hiệu năng không báo mã lỗi (G4 slow region: độ trễ tăng +5s lên ~6.2s > 5.0s). Kích hoạt ngắt mạch khi slow call rate > 0.6, chuyển tải sang `alpha-eu` và kéo p95 từ 13.76s xuống 5.54s. |
| breaker.open_duration_s | 10.0 | Khoảng thời gian ngắt mạch 10 giây cho phép provider có thời gian xả hàng đợi và hồi phục tài nguyên phần cứng (G2, G6) trước khi thử nghiệm thăm dò lại. |
| breaker.half_open_max_probes | 2 | Giới hạn tối đa 2 canary probes đồng thời ở trạng thái HALF_OPEN (`half_open_successes: 2`). Ngăn chặn thundering herd làm sập lại provider vừa mới hồi phục. |

Sơ đồ quyết định của `on_error` (ASCII hoặc bảng: loại lỗi → ghi breaker? → retry? → failover? → cooldown?):

```
                       [Nhận ProviderError]
                                 │
                                 ▼
                     [Phân loại lỗi: errors.py]
                                 │
         ┌───────────────────────┴───────────────────────┐
         │                                               │
   [Non-retryable]                                  [Retryable]
(BAD_REQUEST, AUTH,                              (RATE_LIMIT, OVERLOADED,
 NOT_FOUND, MALFORMED)                            SERVER_ERROR, TIMEOUT, UNKNOWN)
         │                                               │
         ├─ Breaker: KHÔNG ghi nhận                      ├─ Breaker: GHI NHẬN thất bại
         ├─ Failover: KHÔNG (lỗi do client)              ├─ Breaker trip -> OPEN?
         ├─ Retry: KHÔNG                                 │
         └─ Trả về GiveUp(error_kind.value)              ├─ Cập nhật cooldown_until[provider]
                                                         │  (nếu có Retry-After hoặc Quota)
                                                         │
                                                         ▼
                                       [Kiểm tra điều kiện Retry tại chỗ]
                                       • attempts < max_attempts_per_provider?
                                       • cooldown <= 5.0s?
                                       • time_left >= min_time_left_s?
                                                         │
                                    ┌────────────────────┴────────────────────┐
                                   ĐỦ                                       KHÔNG
                                    │                                         │
                             [Kiểm tra Token]                         [Failover sang Provider]
                           RetryBudget.try_acquire()                  kế tiếp trong ladder
                                    │                                         │
                         ┌──────────┴──────────┐                              │
                        CÓ                   HẾT                              │
                         │                     │                              │
                  [Gửi lại Send]        [Hết quota retry]                     │
                  với Full Jitter       chuyển sang failover                  │
                  trên cùng provider           │                              │
                                               └──────────────────────────────┘
                                                              │
                                                              ▼
                                                 Tìm provider khả dụng tiếp
                                                 theo: _route() & Breaker.allow()
                                                              │
                                                       ┌──────┴──────┐
                                                    Tìm thấy      Hết ladder
                                                       │             │
                                                  [Gửi Send]     [GiveUp]
```

## 3. Ba thí nghiệm (mỗi cái 3–5 câu + số)

1. **Retry budget là lớp phòng thủ cuối.** Giả lập breaker cấu hình sai (`breaker.min_calls: 1000000000`) và đặt `max_attempts_per_provider: 5`. Chạy G2, G3 hai lần: (a) giữ retry budget; (b) tắt budget (`retry_budget_ratio: 100`, `retry_budget_max_tokens: 1.0e9`, `retry_budget_min_per_s: 1.0e6`).
   - **Số liệu G2:**
     - (a) Giữ budget: availability = 0.9987, p95 = 19.049s, amplification = 1.383, retry_ratio = 0.058, recovery_s = 0.0s, cost/turn = 2.356 USD.
     - (b) Tắt budget: availability = 0.9649, p95 = 22.122s, amplification = 1.672, retry_ratio = 0.491, recovery_s = 30.0s, cost/turn = 2.474 USD.
   - **Số liệu G3:**
     - (a) Giữ budget: retry_ratio = 0.068, amplification = 1.136.
     - (b) Tắt budget: retry_ratio = 0.162, amplification = 1.163.
   - **Phân tích:** Khi breaker bị tê liệt do ngưỡng `min_calls` quá lớn, Retry Budget trở thành chốt chặn sinh tử duy nhất kìm hãm tỷ lệ retry ở mức $\le 10\%$ token rate, ngăn chặn hiện tượng tự khuếch đại tải và đưa recovery time từ 30s về 0s. Khi breaker hoạt động đúng, Retry Budget vẫn tối quan trọng vì Breaker hoạt động cục bộ theo từng node/provider (cần tích lũy đủ window size mới trip), còn Retry Budget là hạn mức bảo vệ toàn cục (global circuit defense), đảm bảo rằng dù có hàng trăm client đồng loạt gặp lỗi ngắn hạn thì tổng lưu lượng retry toàn mạng không bao giờ được vượt quá ngưỡng an toàn của hệ thống.

2. **`attempt_timeout_s: 30`.** Chạy G4, G6. Chuyện gì xảy ra với p95 và availability? Timeout "đúng" nên dựa vào đâu?
   - **Số liệu G4 (`slow_region`):**
     - Timeout 8.0s: availability = 1.0000, p95 = 5.604s, amplification = 1.016, cost/turn = 2.076 USD.
     - Timeout 30.0s: availability = 1.0000, p95 = 5.683s, amplification = 1.014, cost/turn = 2.077 USD.
   - **Số liệu G6 (`provider_outage`):**
     - Timeout 8.0s: availability = 1.0000, p95 = 6.016s, amplification = 1.056, cost/turn = 2.219 USD.
     - Timeout 30.0s: availability = 0.9488 (FAIL!), p95 = 5.306s, amplification = 1.032, cost/turn = 2.235 USD.
   - **Phân tích:** Ở kịch bản G6 khi provider chính (`alpha`) bị sập hoàn toàn và treo kết nối, timeout 30s khiến client bị giam giữ chờ đợi trên provider chết cho đến khi chạm trần `turn_deadline_s: 30` của người dùng, dẫn đến 5.12% lượt dùng bị hủy bỏ (availability rơi xuống 94.88%). Ngược lại, timeout 8.0s giúp fail-fast trong vòng 8 giây, chừa đủ 22 giây để chuyển hướng sang `alpha-eu` và `beta`, bảo toàn tuyệt đối 100% availability. Do đó, timeout "đúng" không được đặt theo deadline của người dùng, mà phải dựa trên p99 latency của dịch vụ lúc khỏe mạnh cộng thêm một khoảng đệm nhỏ ($p99 + \Delta$), đảm bảo công thức: $(\text{timeout} \times \text{max\_attempts}) < \text{turn\_deadline}$.

3. **Bỏ lọc tool calling khỏi `ladder()`.** Chạy G6. Giải thích con số `incompatible_routes` bằng ngôn ngữ của một product manager.
   - **Số liệu G6 khi bỏ lọc tool calling:**
     - `incompatible_routes` = 258 lỗi định tuyến không tương thích.
     - Availability sụt giảm nghiêm trọng từ 1.0000 (100%) xuống còn 0.8918 (89.18%).
     - Có 464 requests bị chuyển hướng sai sang `gamma-mini`.
   - **Giải thích góc nhìn Product Manager:** "Trong đợt sự cố sập nhà cung cấp chính G6, hệ thống định tuyến của chúng ta đã mắc sai lầm nghiêm trọng khi giao 258 tác vụ tra cứu nghiệp vụ phức tạp (yêu cầu gọi tool/function để đọc database đơn hàng) cho một mô hình giá rẻ, cấp thấp là `gamma-mini` — một mô hình vốn dĩ không có năng lực thực thi công cụ. Hậu quả là 258 khách hàng nhận trực tiếp thông báo lỗi hệ thống hoặc câu trả lời rác, khiến tỷ lệ thành công của ứng dụng sụt giảm hơn 10% và trải nghiệm người dùng bị phá vỡ hoàn toàn. Bài học sản phẩm rút ra là: việc tối ưu hóa chi phí và tính sẵn sàng không bao giờ được phép hy sinh điều kiện tiên quyết về năng lực cốt lõi của tính năng."

## 4. Workflow hoàn tiền

| Executor | completion | crashes | duplicate refunds | duplicate emails | lost refunds | overpaid | wasted LLM / crash |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive | 1.00 | 81 | 128 | 81 | 0 | 1574200 | 1.123 |
| yours | 1.00 | 66 | 0 | 0 | 0 | 0 | 0.303 |

**Trả lời:**
- **Vì sao chỉ idempotency key là chưa đủ, và chỉ checkpoint cũng chưa đủ?**
  - *Chỉ Idempotency Key chưa đủ:* Idempotency key bảo vệ từng dịch vụ biên độc lập (như Payment Service) không bị xử lý lặp lại nếu nhận cùng một request retry. Nhưng nếu worker bị sập giữa chừng trong một quy trình nhiều bước (ví dụ: đã trừ tiền xong nhưng crash trước khi gửi email), khi worker mới khởi động lại mà không có Checkpoint lưu vết trạng thái, nó sẽ buộc phải chạy lại từ đầu. Việc này gây lãng phí gọi lại LLM (wasted LLM calls tăng vọt lên 1.123 / crash), và nếu một bước trung gian không hỗ trợ idempotency key, toàn bộ tính nhất quán của workflow sẽ bị phá vỡ.
  - *Chỉ Checkpoint chưa đủ:* Checkpoint ghi nhớ tiến độ vào cơ sở dữ liệu bền vững (`DurableStore`). Tuy nhiên, mạng phân tán luôn có rủi ro: worker gửi lệnh `payments.refund()` thành công, cổng thanh toán đã chuyển tiền, nhưng gói tin mạng phản hồi bị đứt hoặc worker bị kill ngay trước khi kịp ghi nhận checkpoint. Khi worker mới restart, đọc checkpoint cũ thấy bước thanh toán chưa xong, nó sẽ gọi lại `payments.refund()`. Nếu không có Idempotency Key, cổng thanh toán sẽ hoàn tiền lần thứ 2 (dẫn tới 128 duplicate refunds và thất thoát 15,742 USD như ở naive executor).
- **Điều gì xảy ra nếu ghi checkpoint TRƯỚC khi gọi payment?**
  - Nếu ghi checkpoint hoàn thành *trước* khi thực sự gọi payment, và ngay khoảnh khắc đó tiến trình worker bị crash (mất điện, out of memory, kill signal) trước khi lệnh gọi thanh toán kịp gửi đi:
  - Khi worker khởi động lại, nó đọc thấy checkpoint đánh dấu bước thanh toán là `COMPLETED`, dẫn đến việc worker nhảy cóc qua bước này và chuyển sang gửi email xác nhận.
  - Hậu quả: Khách hàng nhận được email thông báo hoàn tiền thành công nhưng tài khoản thực tế **không bao giờ nhận được tiền** (`lost_refunds > 0`). Đây là thảm họa vi phạm cam kết tài chính nghiêm trọng nhất trong hệ thống giao dịch. Do đó, quy tắc phân tán bắt buộc là: **Luôn thực thi hành động trước (với Idempotency Key), rồi mới ghi Checkpoint sau**.

## 5. Alerting & error budget

| Sự cố | Mong đợi | Naive alerter | Burn-rate alerter | Độ trễ phát hiện |
|---|---|---|---|---:|
| checkout_bug | page | page (`error_ratio_5m`) | page (`fast_burn_2pct_1h`) | 27 min |
| provider_outage | page | page (`error_ratio_5m`) | page (`fast_burn_2pct_1h`) | 4 min |
| deploy_blip | none | page (Báo động giả!) | none (Chính xác) | N/A |
| slow_leak | ticket | none (Bỏ lọt sự cố!) | ticket (`budget_leak_10pct_3d`) | 1337 min |
| degraded_evening | page | page (`error_ratio_5m`) | page (`slow_burn_5pct_6h`) | 291 min |
| night_spike | none | page (Báo động giả!) | none (Chính xác) | N/A |
| small_bump | none | page (Báo động giả!) | none (Chính xác) | N/A |

**Phân tích Error budget 30 ngày:**
- Tổng số requests: 25,901,755 requests. Số lỗi cho phép (SLO 99.5%): 129,508.8 requests.
- Số lỗi thực tế: 55,618 requests. Độ sẵn sàng thực tế đạt: **99.785%**.
- Error budget 30 ngày: đã tiêu **42.95%**, còn lại **57.05%**.
- Có đóng băng release không? **KHÔNG** (`freeze_releases: false`), vì ngân sách lỗi còn dư hơn một nửa (57.05%), hệ thống vẫn nằm trong giới hạn cam kết SLO.
- **Vì sao `small_bump` (20 phút ở 12% lỗi) KHÔNG nên đánh thức ai lúc 11 giờ trưa?**
  - Trong 20 phút với tỷ lệ lỗi 12%, tổng số request lỗi phát sinh chỉ chiếm chưa đầy 0.3% ngân sách lỗi của cả tháng. Sự cố này tự hết sau 20 phút mà hoàn toàn không đe dọa đến cam kết SLO tháng.
  - Naive Alerter chỉ nhìn vào ngưỡng tĩnh 5 phút ngắn ngủi ($> 5\%$), thấy 12% lập tức kích hoạt Page đánh thức kỹ sư on-call, tạo ra cảnh báo giả (Alert Fatigue).
  - Ngược lại, Multi-Window Multi-Burn-Rate Alerter đòi hỏi sự cố phải đốt cháy ngân sách ở tốc độ cao (ví dụ: thiêu hủy $\ge 2\%$ budget trong 1 giờ, tương ứng burn rate 14.4x) trên cả 2 cửa sổ kiểm chứng ngắn và dài. `small_bump` kết thúc trước khi kịp chạm ngưỡng thiêu hủy 2%, do đó hệ thống không báo động giả, giữ vững sự tập trung cho đội ngũ vận hành.

## 6. Postmortem — Băng G2 với client naive (blameless)

*Dùng `make plot` (hình `reports/gameday/G2_overload_storm.png`) và CSV `reports/gameday/naive_G2_overload_storm_timeseries.csv`.*

**Tóm tắt (3 câu):** Vào giây ảo t=120s của kịch bản G2, cụm máy chủ chính `alpha` bị mất 75% năng lực GPU, kích hoạt một đợt retry bão hòa từ client naive do thiếu các cơ chế backoff có jitter, circuit breaker và retry budget. Lượng yêu cầu gửi tới alpha bị khuếch đại lên 9.9 lần (đạt đỉnh gần 184 attempts/s), làm nghẽn hoàn toàn hàng đợi của nhà cung cấp và kéo tỷ lệ sẵn sàng xuống 45.60%. Hệ thống rơi vào trạng thái lỗi siêu bền (metastable failure), khiến tình trạng gián đoạn kéo dài thêm 155 giây sau khi hạ tầng phần cứng của alpha đã hồi phục 100%.

**Ảnh hưởng:**
- Tổng số lượt tương tác người dùng thất bại: **1,285 turns** thất bại trên tổng số 2,362 turns (tỷ lệ thành công chỉ đạt **45.60%**, chỉ có 1,077 good turns).
- Thời gian gián đoạn kéo dài: **335 giây** liên tục (từ t=120s đến t=455s).
- Tiêu tốn Error Budget: Với SLO 99.5%, trong khoảng thời gian diễn ra kịch bản 600s chỉ cho phép tối đa 12 turns lỗi; sự cố làm hỏng 1,285 turns, tương đương thiêu hủy **10,708%** (gấp 107 lần) ngân sách lỗi của phiên chạy, và ngốn đứt **2.48%** tổng ngân sách lỗi của cả một tháng 30 ngày (51,840 lỗi cho phép) chỉ trong chưa đầy 6 phút.
- Chi phí tổn thất: Chi phí trung bình cho mỗi lượt thành công tăng từ 2.10 USD lên 4.63 USD/turn (gấp 2.2 lần) do lãng phí 34,475 attempts vô ích.

**Timeline** (giây ảo — lấy từ CSV `naive_G2_overload_storm_timeseries.csv`):

| t (s) | Sự kiện | Bằng chứng (số) |
|---:|---|---|
| 119 | Trạng thái bình thường trước sự cố | `attempts_alpha` = 9, `calls_ok` = 7, `success_ratio` = 1.000 |
| 120 | alpha mất 75% năng lực GPU (`capacity_factor: 0.25`) | `attempts_alpha` = 5, hàng đợi server bắt đầu tích lũy |
| 150 | Quá tải bắt đầu bùng nổ, client retry ồ ạt | `attempts_alpha` = 163 attempts/s, `calls_ok` = 0, `success_ratio` = 0.000 |
| 200 | Cơn bão retry storm dâng cao đỉnh điểm | `attempts_alpha` = 135 attempts/s, 26,298 lỗi rate limit tích tụ, `success_ratio` = 0.000 |
| 250 | Đỉnh điểm quá tải hàng đợi | `attempts_alpha` = 184 attempts/s, 655 user kiệt sức retry, `success_ratio` = 0.000 |
| 300 | alpha hồi phục hoàn toàn năng lực phần cứng | `attempts_alpha` = 115 attempts/s, `calls_ok` = 0, `success_ratio` = 0.000 |
| 350 | Hạ tầng đã khỏe nhưng hệ thống vẫn sập | `attempts_alpha` = 17 attempts/s, `calls_ok` = 0, `success_ratio` = 0.000 |
| 450 | Hàng đợi cạn dần do các request quá hạn bị hủy | `attempts_alpha` = 16 attempts/s, `calls_ok` = 0, `success_ratio` = 0.000 |
| 455 | Bắt đầu có phản hồi thành công đầu tiên | `attempts_alpha` = 13 attempts/s, `calls_ok` = 4, `calls_done` = 5, `success_ratio` = 0.800 |
| 456 | Hệ thống hồi phục hoàn toàn (trễ hồi phục 155s) | `attempts_alpha` = 15 attempts/s, `calls_ok` = 8, `calls_done` = 8, `success_ratio` = 1.000 |

**Trigger vs root cause:**
- **Trigger:** Nhà cung cấp `alpha` bị mất 75% số lượng GPU khả dụng trong vòng 180 giây (t=120 đến t=300).
- **Root cause:** Thiết kế client naive thiếu hoàn toàn các cơ chế phục hồi phân tán:
  1. Không có Circuit Breaker để cô lập alpha và chuyển hướng lưu lượng sang các provider thay thế (`alpha-eu`, `beta`).
  2. Không có Retry Budget để giới hạn tỷ lệ retry (dẫn đến retry amplification lên tới 9.9x).
  3. Sử dụng fixed retry interval không jitter và phớt lờ hoàn toàn chỉ dẫn `Retry-After` (gây ra 28,381 vi phạm retry_after).
- **Vì sao provider đã hồi phục mà hệ thống vẫn sập (Metastable Failure Loop)?**
  - Đây là cơ chế tự duy trì quá tải kinh điển: Khi alpha chậm lại $\rightarrow$ các client timeout $\rightarrow$ client lập tức gửi thêm retry đè lên $\rightarrow$ hàng đợi của alpha phình to vượt quá khả năng xử lý $\rightarrow$ alpha tiêu tốn hầu hết CPU/GPU chỉ để nhận diện và từ chối các kết nối quá tải thay vì tính toán sinh token $\rightarrow$ các request mới tiếp tục bị chậm/timeout $\rightarrow$ sinh ra thêm các đợt retry mới. Vòng lặp này tự duy trì ngay cả sau t=300s khi 100% GPU đã trở lại, cho đến tận t=455s khi lượng lớn request chạm trần 30s deadline và bị client hủy bỏ thì hàng đợi mới giải tỏa xong.

**Điều gì giúp / điều gì làm tệ hơn:**
- *Làm tệ hơn:* Client tiếp tục retry không ngừng vào một provider duy nhất; phớt lờ header `Retry-After`; thiếu độ trễ ngẫu nhiên (jitter) khiến các gói tin retry đập vào máy chủ theo từng nhịp sóng đồng pha.
- *Điều gì giúp (thể hiện ở Resilient Client):*
  1. Circuit Breaker phát hiện tỷ lệ lỗi/chậm vượt ngưỡng lập tức chuyển sang `OPEN`, chặn đứng toàn bộ luồng request đổ vào alpha trong 10 giây.
  2. Tự động chuyển hướng lưu lượng (failover) thông minh sang `alpha-eu` và `beta`.
  3. Khi alpha hồi phục tại t=300s, trạng thái `HALF_OPEN` chỉ cho phép đúng 2 canary probe thử nghiệm, xác nhận thành công mới mở lại lưu lượng, giúp độ trễ hồi phục đạt mức hoàn hảo: **0.0 giây**.

**Action items** (cụ thể, có owner, đo được):

| # | Hành động | Loại (prevent / detect / mitigate) | Owner | Cách kiểm chứng |
|---|---|---|---|---|
| 1 | Chuẩn hóa Circuit Breaker đa trạng thái (Closed/Open/Half-Open) tích hợp trong bộ SDK gọi model tập trung | Prevent | Nguyễn Hải Long (Platform Lead) | Kiểm thử Game Day G2/G4: unneeded_failovers = 0, availability $\ge 99\%$ |
| 2 | Áp dụng Token-bucket Retry Budget (trần 10%) và Full Jitter Exponential Backoff tuân thủ nghiêm ngặt `Retry-After` | Mitigate | Client SDK Team | Tape G1/G2: retry_after_violations = 0, amplification $\le 1.1$ |
| 3 | Triển khai hệ thống cảnh báo đa cửa sổ Multi-Window Multi-Burn-Rate dựa trên Error Budget 30 ngày | Detect | SRE / Observability Team | Replay 30 ngày dữ liệu SLO: 0 cảnh báo giả (false pages = 0), phát hiện outage $\le 5$ phút |

## 7. Một điểm yếu còn lại

**Tình huống client xử lý kém:**
Trong kịch bản G2 hoặc khi provider chính `alpha` gặp sự cố kéo dài, mặc dù `ResilientClient` bảo toàn được 100% availability, **p95 latency bị đẩy vọt lên 9.789s** (so với 4.786s ở G1), và chi phí tăng lên khi phải đẩy tải sang `beta` (giá 1.4 USD/call so với 1.0 USD của alpha). Nguyên nhân cốt lõi là chiến lược failover hiện tại là **chờ lỗi tuần tự (sequential failover)**: client phải chờ request đầu tiên ở `alpha` chạy hết timeout (8.0s) hoặc nhận lỗi 529 rồi mới bắt đầu thử sang `alpha-eu` hay `beta`. Nếu gặp trường hợp cả 4 provider cùng bị suy giảm mạng nhẹ (chậm thêm 4-5s), việc thử tuần tự $8s + 8s$ sẽ dễ dàng vượt quá deadline 30s của người dùng.

**Giải pháp khắc phục:**
1. **Hedged Requests (Yêu cầu phòng ngừa suy giảm trễ):**
   Thay vì chờ đợi hết 8.0s timeout, nếu sau một ngưỡng thời gian p95 bình thường (ví dụ 2.5s) mà `alpha` chưa trả về token đầu tiên, client sẽ tự động phát một bản sao request dự phòng sang `alpha-eu`. Bản ghi nào phản hồi trước sẽ được sử dụng, bản ghi còn lại lập tức bị hủy (`cancel`). Giải pháp này giúp cắt bỏ hoàn toàn đuôi độ trễ dài (tail latency), kéo p95 của G2 từ 9.789s xuống dưới 4.5s với mức tăng chi phí không đáng kể.
2. **Dynamic P2C Load Balancing (Power of Two Choices theo độ trễ và chi phí):**
   Thay thế danh sách fallback cứng tĩnh `[alpha, alpha-eu, beta, gamma-mini]` bằng bộ định tuyến động theo dõi Moving Average p95 và tỷ lệ lỗi thời gian thực. Khi thấy alpha có dấu hiệu tăng hàng đợi, bộ điều phối sẽ chủ động chuyển bớt 20-30% lưu lượng sang `alpha-eu` trước khi alpha bị sập hẳn, ngăn ngừa hiện tượng giật cục độ trễ khi chuyển mạch.

## 8. Cache (Part G)

Số từ `reports/cache/*.json` (`make cache`).

| Client | availability | faq_availability | cache_hit_ratio | stale_served | wrong_answers | outdated_answers | cost/turn | PASS? |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| resilient (không cache) | 0.8373 | 0.8424 | 0.000 | 0 | 0 | 0 | 1.386 | FAIL |
| cached (của bạn) | 0.9124 | 0.9645 | 0.652 | 157 | 0 | 3 | 0.915 | PASS |

| Tham số `cache:` | Giá trị | Vì sao (số liệu nào) |
|---|---:|---|
| similarity_threshold | 0.92 | Cấu hình mặc định 0.80 trả lời sai tới 157 câu (`wrong_answers: 157` do ghép nhầm `other_question`). Nâng lên 0.92 triệt tiêu 100% câu trả lời sai (`wrong_answers = 0`), trong khi vẫn duy trì tỷ lệ trúng cache cao 65.2% (so với 58.1% ở ngưỡng khắt khe 0.97). |
| ttl_s | 60.0 | Cấu hình mặc định 600s khiến 80 câu trả lời bị lỗi thời khi cước vận chuyển cập nhật tại t=480s. Giảm xuống 60.0s khống chế `outdated_answers` chỉ còn 3 (đạt chuẩn check $\le 15$), đồng thời giữ vững chi phí thấp (0.915 USD/turn). |
| max_stale_s | 300.0 | Phục vụ 157 lượt cache cũ an toàn trong đợt sập toàn bộ provider (t=240–360s), nâng `faq_availability` từ 87.33% lên 96.45% (vượt xa mức sàn cam kết 93.0%). |

Thí nghiệm (mỗi cái 2–4 câu + số):

1. **Ngưỡng.** Chạy C1 với `similarity_threshold` = 0,80 / giá trị của bạn (0.92) / 0.97. Ghi hit ratio, `wrong_answers`, cost.
   - **Số liệu:**
     - Ngưỡng 0.80: hit_ratio = 0.666, wrong_answers = 157 (`wrong_answers_by_reason: {'other_question': 157}`), outdated = 1, cost/turn = 0.965 USD.
     - Ngưỡng 0.92: hit_ratio = 0.652, wrong_answers = 0, outdated = 3, cost/turn = 0.915 USD.
     - Ngưỡng 0.97: hit_ratio = 0.581, wrong_answers = 0, outdated = 4, cost/turn = 0.964 USD.
   - **Phân tích:** Ở ngưỡng 0.80, khoảng cách cosine quá lỏng lẻo khiến hệ thống ghép nhầm các câu hỏi có từ khóa tương đồng nhưng khác biệt bản chất ngữ nghĩa (ví dụ: "chính sách hoàn hàng điện tử" bị nhầm sang "chính sách hoàn hàng thời trang", hoặc "hủy đơn hàng đã thanh toán" bị nhầm sang "đổi địa chỉ giao hàng"). Ngưỡng 0.92 là điểm ngọt tối ưu: loại bỏ hoàn toàn câu trả lời sai mà không làm suy giảm hit ratio như ngưỡng 0.97.

2. **TTL.** Chạy với `ttl_s` = 30 / 60 / 300. Vì sao webhook không giúp được gì cho `outdated_answers`, và TTL là thứ duy nhất giới hạn nó?
   - **Số liệu:**
     - TTL = 30s: outdated_answers = 2, hit_ratio = 0.592, cost/turn = 0.955 USD.
     - TTL = 60s: outdated_answers = 3, hit_ratio = 0.652, cost/turn = 0.915 USD.
     - TTL = 300s: outdated_answers = 95 (FAIL check $\le 15$), hit_ratio = 0.731, cost/turn = 0.863 USD.
   - **Phân tích:** Webhook chỉ kích hoạt khi có sự kiện thay đổi dữ liệu cấu trúc nội bộ trên các entity ID cụ thể (ví dụ `order_id`). Trong khi đó, Semantic Cache lưu trữ câu trả lời cho văn bản tự nhiên phi cấu trúc (unstructured text queries), không có khóa định danh rõ ràng. Các thay đổi chính sách từ bên thứ ba (như đối tác vận chuyển âm thầm đổi bảng cước, biến động tỷ giá) xảy ra âm thầm ngoài luồng hệ thống mà không có webhook nào bắn tới; hoặc dù có webhook chung thì hệ thống cũng không thể biết vector embedding nào trong không gian đa chiều cần phải xóa. Do đó, TTL là cơ chế toán học duy nhất đặt trần giới hạn thời gian tồn tại tối đa cho thông tin cũ.

3. **Stale-if-error.** Chạy với `max_stale_s: 0`. `faq_availability` thay đổi thế nào?
   - **Số liệu:**
     - `max_stale_s: 0` (Tắt stale fallback): faq_availability = 0.8733 (87.33% - FAIL check $\ge 93\%$), overall availability = 0.8565, stale_served = 0, hit_ratio = 0.561.
     - `max_stale_s: 300` (Bật stale fallback): faq_availability = 0.9645 (96.45% - PASS!), overall availability = 0.9124, stale_served = 157, hit_ratio = 0.652.
   - **Phân tích:** Khi toàn bộ nhà cung cấp LLM đồng loạt ngừng hoạt động từ t=240s đến t=360s, việc cho phép phục vụ 157 phản hồi FAQ đã hết hạn TTL nhưng vẫn trong cửa sổ 300s đã cứu vãn tỷ lệ sẵn sàng của dịch vụ FAQ tăng thêm tới **+9.12%**, biến thời gian ngừng trệ backend thành trải nghiệm tra cứu liền mạch cho người dùng.

**Trả lời:**

- **Vì sao câu hỏi cá nhân ("Đơn #48213 của tôi đang ở đâu?") KHÔNG được cache, kể cả khi cache theo từng user?**
  1. *Tính biến động dữ liệu theo thời gian thực (Real-time Volatility):* Trạng thái đơn hàng thay đổi liên tục theo từng phút (đang đóng gói $\rightarrow$ đã giao cho shipper $\rightarrow$ đang giao đến cửa). Việc cache lại câu trả lời sẽ khiến khách hàng nhận thông tin cũ, gây khiếu nại và hiểu nhầm trầm trọng.
  2. *Rủi ro rò rỉ dữ liệu cá nhân nhạy cảm (PII & Security Leakage):* Câu hỏi cá nhân luôn gắn liền với thông tin cá nhân (địa chỉ, số điện thoại, giá trị đơn). Lưu trữ vào semantic cache tiềm ẩn nguy cơ rò rỉ dữ liệu chéo giữa các phiên người dùng nếu thuật toán embedding đo nhầm độ tương đồng ngữ nghĩa.
  3. *Không có giá trị tái sử dụng (Zero Cache Value):* Câu hỏi về một mã đơn hàng cụ thể chỉ phát sinh 1–2 lần trong vòng đời đơn hàng, việc lưu vào cache chỉ làm phân mảnh bộ nhớ và chiếm dụng chỗ (LRU eviction) của các câu hỏi FAQ chung có tần suất truy vấn cao.

- **Trong lúc mọi provider sập, dashboard vẫn xanh nhờ cache. Bạn sẽ alert dựa trên số nào để on-call vẫn biết có sự cố?**
  - Nếu chỉ quan sát chỉ số ở tầng rìa ngoài mạng (`edge_availability` hoặc `http_200_rate`), dashboard sẽ "xanh giả tạo" vì Semantic Cache đang gánh tải trả về câu trả lời stale.
  - Để kỹ sư on-call phát hiện ngay sự cố ngầm của hệ thống backend, cần thiết lập cảnh báo dựa trên các chỉ số nội tại:
    1. **Tỷ lệ lỗi của nhà cung cấp thượng nguồn (Upstream / Provider Error Rate):** Đo trực tiếp tỷ lệ lỗi hoặc số lượng request thất bại khi client gọi tới các API LLM (`upstream_error_rate = errors / attempts`).
    2. **Tốc độ phục vụ Cache cũ (`stale_served_rate`):** Theo dõi số lượng câu trả lời stale được kích hoạt trong mỗi phút. Ở trạng thái bình thường con số này bằng 0; khi `stale_served > 0` tăng đột biến, đó là bằng chứng trực tiếp cho thấy upstream đang sập và cache đang phải kích hoạt cơ chế phòng vệ khẩn cấp.
    3. **Trạng thái Circuit Breaker (`breaker_state`):** Bắn cảnh báo ngay khi Circuit Breaker của provider chính chuyển sang trạng thái `OPEN` (`breaker_open{provider="alpha"} == 1`).
