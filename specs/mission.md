# Mission: AdverTest

> File này thuộc constitution của dự án. Mọi feature spec và mọi agent phải đọc file này trước khi viết code. Khi một quyết định ở cấp feature mâu thuẫn với file này, file này thắng. Muốn đổi thì cập nhật file này trước, có ghi lý do.

## 1. Sản phẩm là gì

AdverTest là công cụ kiểm thử độ bền vững (robustness) cho model perception của robot và xe tự hành. Công cụ áp dụng tấn công adversarial white-box và các phép biến đổi mô phỏng điều kiện thực tế (thời tiết, che khuất, patch) lên ảnh camera, chạy model detection trên ảnh gốc và ảnh đã biến đổi, rồi đo mức suy giảm hiệu năng.

Kết quả của mỗi lần kiểm thử phải **tái lập được**, **có chi phí biết trước**, và chỉ trở thành kết luận chính thức sau khi được **một kỹ sư độc lập duyệt**.

## 2. Vấn đề cần giải quyết

Model perception có thể bị đánh lừa bởi nhiễu rất nhỏ, thời tiết xấu, vật che khuất hoặc patch adversarial, gây rủi ro an toàn. Đội kỹ sư hiện thiếu một công cụ để:

- sinh các biến thể tấn công và biến đổi một cách có hệ thống,
- đo định lượng mức suy giảm (mAP, IoU, tỷ lệ tấn công thành công),
- tìm điểm yếu của model trước khi triển khai,
- ra quyết định có kiểm soát, có người chịu trách nhiệm và có dấu vết kiểm toán.

## 3. Người dùng và vai trò

| Role | Mục tiêu | Được làm | Không được làm |
|---|---|---|---|
| ML/perception engineer | Tìm điểm yếu của model | Cấu hình và chạy experiment, upload dataset, tạo slice, phân tích metric, gửi duyệt | Duyệt experiment, xuất report chính thức, sửa kết quả, sửa protocol |
| Safety/reviewer engineer | Kết luận model có đạt yêu cầu an toàn không | Tạo test protocol, review failure case, ghi verdict và mitigation, approve/yêu cầu sửa/từ chối, xuất report | Review experiment do chính mình tạo, sửa kết quả |
| Project administrator | Vận hành hệ thống | Duyệt tài khoản, gán role, quản lý model registry, attack catalog, compute target, quota, ngân sách, xem audit log | Duyệt experiment, sửa kết quả, sửa audit log |

Một người có thể có nhiều role. Khi đó họ có hợp các quyền, **trừ** luật không tự review experiment do mình tạo.

## 4. Nguyên tắc không được vi phạm

Các nguyên tắc dưới đây là lý do tồn tại của sản phẩm. Feature nào vi phạm một nguyên tắc thì feature đó sai, kể cả khi nó chạy được.

1. **Tách quyền.** Người chạy test không duyệt test. Chỉ reviewer (không phải người tạo experiment) được approve và xuất report. Luật này được kiểm tra ở backend, không dựa vào việc ẩn nút trên giao diện.
   *Lý do:* ngăn engineer tự xác nhận kết quả có lợi cho mình.

2. **Tiêu chí được chốt trước khi biết kết quả.** Mỗi experiment gắn với một test protocol do reviewer tạo trước, gồm attack bắt buộc, dải tham số, slice tối thiểu và ngưỡng đạt. Engineer không chạy dưới mức protocol yêu cầu.
   *Lý do:* ngăn việc chọn phép thử dễ để có kết quả đẹp.

3. **Kết quả là bất biến và truy vết được.** Chỉ worker (tài khoản hệ thống) được ghi kết quả. Run không bị xóa, chỉ được lưu trữ. Experiment bị khóa khi gửi duyệt. Model, dataset, slice, attack spec đều định danh bằng hash. Audit log chỉ được thêm, không sửa, không xóa.
   *Lý do:* report phải phản ánh đúng những gì đã chạy, kể cả các lần chạy thất bại.

4. **Tái lập được.** Mỗi run có fingerprint và manifest đủ để chạy lại. "Tái lập" nghĩa là metric nằm trong sai số đã định nghĩa, vì GPU không hoàn toàn tất định.
   *Lý do:* kết luận an toàn phải kiểm chứng lại được.

5. **Chi phí biết trước và có giới hạn.** Trước khi chạy, người dùng thấy thời gian ước lượng, và với máy thuê thì thấy thêm chi phí tối đa. Mọi experiment có giới hạn (tiền với máy thuê, thời gian với máy local). Chạm giới hạn thì dừng và giữ kết quả một phần.
   *Lý do:* GPU thuê chạy bằng kinh phí được cấp; GPU local là tài nguyên dùng chung.

6. **Trạng thái luôn rõ ràng.** Hệ thống luôn nói rõ run nào hoàn thành, thất bại, bị bỏ qua, dừng do giới hạn hay bị hủy, và vì sao. Không có trạng thái "xong" chung chung.

7. **Con người quyết định.** Hệ thống đo lường và gợi ý; kỹ sư review failure case và quyết định biện pháp khắc phục (human-in-the-loop).

8. **Chỉ là môi trường kiểm thử.** Công cụ chỉ chạy trên dữ liệu và mô phỏng. Kết quả không được dùng làm căn cứ triển khai thật khi chưa được validate bằng quy trình khác. Report phải ghi rõ điều này.

9. **Tôn trọng quyền riêng tư.** Mặt người và biển số không được hiển thị rõ trên giao diện hay trong report. Việc làm mờ thực hiện ở tầng hiển thị/xuất, không thay đổi dữ liệu đưa vào model.

## 5. Phạm vi hiện tại

**Trong phạm vi:**
- Model detection 2D trên ảnh camera (YOLO; Faster R-CNN là phương án dự phòng).
- Dataset KITTI và dataset riêng của người dùng (YOLO, COCO, KITTI format).
- Tấn công white-box: FGSM, PGD, patch attack.
- Biến đổi mô phỏng: thời tiết (fog, snow, frost, ...), motion blur, contrast, occlusion theo bounding box.
- Hai chế độ chạy: quét lưới và tự tìm ngưỡng (điểm gãy).
- Máy chạy local (không tính phí) và máy thuê (tính phí theo giờ).
- Ba role, đăng ký cần admin duyệt.
- Report PDF/JSON có mã hash và trang xác minh.
- Giao diện responsive (điện thoại, tablet, desktop).

**Ngoài phạm vi (có thể làm sau):**
- Tấn công black-box.
- Segmentation (SAM2) và 3D detection (MMDetection3D, point cloud).
- Tìm kiếm nhiều tham số cùng lúc.
- Tự động bật/tắt máy thuê qua API nhà cung cấp.
- PWA và push notification.
- Fine-tune hoặc phòng thủ (adversarial training) cho model.

## 6. Tiêu chí thành công

**Mức cơ bản** (phải đạt):
- Áp dụng được ít nhất một phép biến đổi và một attack white-box lên ảnh mẫu, chạy model và báo cáo mAP/IoU trước và sau.
- Có ít nhất hai role hoạt động đúng quyền (engineer chạy, reviewer duyệt).
- Report chỉ được xuất sau khi reviewer duyệt.

**Mức nâng cao:**
- Quét nhiều loại tấn công theo mức độ, tự động lập bảng robustness.
- Tự tìm điểm gãy theo ngưỡng suy giảm cho từng attack.
- Benchmark định lượng giữa các model hoặc các lần chạy.
- Quản lý và tối ưu chi phí GPU (ước lượng trước, giới hạn, cache kết quả).

**Tiêu chí kỹ thuật:**
- Chạy lại một run từ manifest cho metric nằm trong sai số cho phép.
- Toàn bộ luật ở mục 4 có test nghiệm thu tự động tương ứng.
- Luồng tạo → chạy → gửi duyệt → review → approve → xuất report chạy trọn vẹn trên cả desktop và điện thoại.

## 7. Câu hỏi còn mở

- [ ] Deadline chính xác: 3 hay 4 tuần.
- [ ] Nhà cung cấp GPU thuê, loại GPU, giá mỗi giờ, tổng kinh phí.
- [ ] Protocol mặc định: attack bắt buộc, ngưỡng sụt, dải tham số.
- [ ] Định dạng dataset riêng hiện có và có nhãn hay không.
- [ ] Nơi triển khai sản phẩm cuối.
