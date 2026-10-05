# Giải thích các tham số của Protocol

Trong AdverTest, protocol là một “hợp đồng kiểm thử”: quy định tối thiểu experiment phải chạy
những gì, dữ liệu phải đủ lớn ra sao và kết quả thế nào được xem là đạt. Protocol không phải toàn
bộ cấu hình chạy; engineer vẫn có thể thêm level hoặc attack nếu cấu hình cuối cùng vẫn tuân thủ
protocol.

## 1. Thông tin chung

| Trường | Ý nghĩa |
|---|---|
| Tên protocol | Tên định danh, ví dụ `kitti-demo` hoặc `production-yolo-policy`. Tối đa 200 ký tự. |
| Mục đích | Giải thích protocol dùng để kiểm tra gì. Bắt buộc, tối đa 4.000 ký tự. |
| Kích thước slice tối thiểu | Số ảnh tối thiểu trong tập đánh giá. Experiment phải chọn slice có số ảnh bằng hoặc lớn hơn giá trị này. |
| Số case bắt buộc review mỗi attack | Số failure case nghiêm trọng nhất của mỗi attack bắt buộc mà reviewer phải ghi verdict. |
| Không chấp nhận run chạy từ code chưa commit | Nếu bật, experiment có run với `git_dirty=true` sẽ không đủ điều kiện gửi duyệt. |

Giá trị mặc định trên giao diện:

- `min_slice_size = 300`;
- `cases_to_review_per_attack = 5`;
- `forbid_dirty_runs = true`.

### Kích thước slice tối thiểu

Đây là kích thước của slice đánh giá, không phải training slice. Ví dụ protocol yêu cầu `300`:

- slice 250 ảnh: không tuân thủ;
- slice 300 hoặc 500 ảnh: tuân thủ.

### Số case bắt buộc review mỗi attack

Hệ thống chọn tối đa N failure case có `severity_score` cao nhất trên tất cả run của từng attack
bắt buộc.

Ví dụ protocol có `fgsm`, `pgd_linf` và `cases_to_review_per_attack = 5`: reviewer có thể phải
review tối đa 5 case FGSM và 5 case PGD. Nếu một attack chỉ sinh ra 3 failure case thì chỉ có 3
case của attack đó phải review.

## 2. Attack bắt buộc

Mỗi attack trong protocol có các trường:

| Trường | Ý nghĩa |
|---|---|
| Attack | Loại attack trong catalog, ví dụ `fgsm`, `pgd_linf`. |
| Version/spec | Giao diện tự chốt `spec_sha256`, bảo đảm experiment dùng đúng phiên bản thuật toán và tham số cố định. |
| Chế độ | `Quét lưới` (`grid`) hoặc `Tìm ngưỡng` (`search`). |
| Tham số phụ | Phụ thuộc chế độ được chọn. |

Một protocol không được khai báo cùng một attack hai lần. Nếu muốn đánh giá nhiều mức của một
attack, nhập nhiều level trong cùng attack.

Nếu attack bắt buộc cần gradient thì model được chọn cũng phải hỗ trợ gradient.

## 3. Chế độ Quét lưới (Grid)

Quét lưới nghĩa là chạy attack tại từng level đã chỉ định. Ví dụ với FGSM:

```text
Level bắt buộc: 2, 4, 8
```

FGSM có tham số chính `eps`, đơn vị `1/255`, nên hệ thống sẽ chạy:

```text
eps = 2/255
eps = 4/255
eps = 8/255
```

Các level trong protocol là mức tối thiểu phải có:

- experiment chạy `2, 4, 8`: tuân thủ;
- experiment chạy `1, 2, 4, 8, 16`: vẫn tuân thủ;
- experiment chạy `2, 8`: không tuân thủ vì thiếu level `4`.

Ràng buộc:

- phải có ít nhất một level;
- level không được trùng;
- level phải nằm trong dải của attack spec;
- tối đa 12 level cho mỗi attack;
- tổng số run ước tính của toàn protocol không quá 50.

FGSM hiện có dải `0–32`, đơn vị `1/255`.

## 4. Chế độ Tìm ngưỡng (Search)

Chế độ này tìm “điểm gãy”: level nhỏ nhất mà mức suy giảm đạt tới một ngưỡng nhất định.

Ví dụ:

```text
Loại ngưỡng: Mức sụt tương đối
Ngưỡng: 20%
lo: 0
hi: 16
max_tol: 0.25
```

Ý nghĩa: tìm giá trị attack trong dải `[0, 16]` nơi hiệu năng model bắt đầu giảm ít nhất 20%, với
khoảng điểm gãy cuối cùng có độ rộng không quá `0.25`.

### Loại ngưỡng

| Loại | Không chọn class | Khi chọn class |
|---|---|---|
| Mức sụt tương đối (`relative_drop`) | `(mAP sạch - mAP bị attack) / mAP sạch` | Tính bằng AP@0.5 của class |
| Mức sụt tuyệt đối (`absolute_drop`) | `mAP sạch - mAP bị attack` | Hiệu AP@0.5 của class |
| Tỷ lệ tấn công thành công (`attack_success_rate`) | ASR trên mọi object | ASR chỉ trên object thuộc class |

Ví dụ mAP sạch là `0.8`, sau attack còn `0.6`:

- sụt tuyệt đối: `0.8 - 0.6 = 0.2`, tức 20 điểm phần trăm;
- sụt tương đối: `(0.8 - 0.6) / 0.8 = 0.25`, tức 25%.

Giao diện nhập theo phần trăm. Nhập `20` được lưu thành `0.2`.

### Class

Trường này không bắt buộc:

- để trống: tính trên toàn bộ dataset;
- nhập `car`: chỉ tính AP hoặc ASR của class `car`.

Class phải tồn tại trong class mapping của experiment. Nếu không có dữ liệu cần thiết cho class,
kết quả có thể là `inconclusive` hoặc quá trình tìm ngưỡng có thể kết thúc với `failed`.

### Cận dưới `lo` và cận trên `hi`

Hai giá trị xác định dải cường độ attack cần tìm kiếm:

```text
lo < điểm gãy <= hi
```

Chúng phải thỏa các điều kiện:

- `lo < hi`;
- nằm trong dải của tham số chính của attack;
- với tham số rời rạc, phải là giá trị attack cho phép.

### Sai số tối đa `max_tol`

Đây là độ rộng tối đa của khoảng điểm gãy khi thuật toán dừng chia đôi:

```text
điểm gãy nằm trong (a, b]
b - a <= max_tol
```

`max_tol` dùng cùng đơn vị với level của attack, không phải phần trăm thống kê. Giá trị càng nhỏ
thì kết quả càng chính xác nhưng có thể cần nhiều run hơn.

Ví dụ với FGSM:

```text
lo = 0
hi = 16
max_tol = 0.25
```

Kết quả có thể là `điểm gãy trong (5.75, 6.0]`.

`max_tol` phải lớn hơn 0 và nhỏ hơn `hi - lo`.

### Số mẫu bootstrap tối thiểu

Đây là số lần bootstrap tối thiểu để ước lượng khoảng tin cậy cho điểm gãy:

- `200`: giá trị mặc định;
- giá trị lớn hơn: khoảng tin cậy ổn định hơn nhưng tính toán nhiều hơn;
- `0`: không tính khoảng tin cậy;
- giá trị hợp lệ: từ `0` đến `1000`.

Protocol đặt mức tối thiểu. Nếu protocol yêu cầu 200, experiment dùng 500 vẫn tuân thủ.

## 5. Tiêu chí đạt

Protocol bắt buộc có ít nhất một tiêu chí. Tiêu chí đánh giá kết quả sau khi experiment chạy;
khác với “Attack bắt buộc”, vốn kiểm tra cấu hình trước khi chạy.

### Mức sụt tối đa tại một level

Chỉ dùng với attack chạy chế độ Grid.

Ví dụ:

```text
Attack: fgsm
Level: 4
Loại ngưỡng: Mức sụt tương đối
Mức sụt tối đa: 20%
Class: để trống
```

Ý nghĩa: khi chạy FGSM tại `eps = 4/255`, mAP@0.5 không được giảm quá 20% so với kết quả sạch.

```text
relative_drop <= 0.20  -> pass
relative_drop > 0.20   -> fail
```

Level của tiêu chí phải nằm trong danh sách level bắt buộc của attack. Nếu chọn một class, hệ
thống so sánh AP@0.5 riêng của class đó thay vì mAP toàn dataset.

### Điểm gãy tối thiểu

Chỉ dùng với attack chạy chế độ Search.

Ví dụ search được cấu hình với ngưỡng suy giảm 20% trên dải `[0, 16]`, còn tiêu chí yêu cầu điểm
gãy tối thiểu là `6`. Model chỉ được xem là đạt nếu phải dùng attack level từ 6 trở lên mới làm
hiệu năng suy giảm 20%.

```text
điểm gãy >= 6  -> pass
điểm gãy < 6   -> fail
```

Loại ngưỡng, giá trị ngưỡng và class của tiêu chí này được lấy từ cấu hình Search; chúng không
được khác với attack.

Do tìm kiếm trả về một khoảng `(a, b]`, kết quả có thể là:

- `pass`: toàn bộ điểm gãy đủ lớn;
- `fail`: điểm gãy thấp hơn mức yêu cầu;
- `inconclusive`: khoảng tìm được chứa mức yêu cầu, nằm sát ngưỡng, hoặc khoảng tin cậy giao với
  mức yêu cầu.

## 6. Quan hệ giữa Attack và Tiêu chí

Ví dụ:

```text
Attack bắt buộc:
  FGSM grid: 2, 4, 8

Tiêu chí:
  Tại level 4, mức sụt tương đối tối đa 20%
  Tại level 8, mức sụt tương đối tối đa 40%
```

Cấu hình này quy định đồng thời:

1. Experiment bắt buộc chạy FGSM tại 2, 4 và 8.
2. Kết quả tại level 4 không được sụt quá 20%.
3. Kết quả tại level 8 không được sụt quá 40%.

Engineer có thể thêm level 16 nhưng không thể bỏ 2, 4 hoặc 8. Một attack có thể có nhiều tiêu
chí. Không bắt buộc mỗi attack phải có tiêu chí riêng, nhưng toàn protocol phải có ít nhất một
tiêu chí.

## 7. Version và trạng thái

Protocol sau khi tạo là bất biến:

- `active`: dùng để tạo experiment mới;
- `retired`: không dùng để tạo experiment mới, nhưng experiment cũ vẫn giữ nguyên protocol này;
- `dev`: protocol đặc biệt `dev-open`, không có yêu cầu tuân thủ và không dùng cho quy trình review
  chính thức.

Muốn thay đổi tham số, reviewer phải tạo version mới. Version cũ chuyển sang `retired`; version
mới giữ nguyên tên và tăng số version.

`body_sha256` là hash toàn bộ nội dung protocol, dùng để xác định chính xác experiment và report
đã áp dụng phiên bản tiêu chí nào.

## 8. Cấu hình khởi đầu cho demo

Với fixture demo 5 ảnh:

```text
Tên: kitti-demo
Kích thước slice tối thiểu: 5
Số case review mỗi attack: 2
Không chấp nhận code chưa commit: bật

Attack:
  fgsm
  Quét lưới
  Level: 2, 4

Tiêu chí:
  Mức sụt tối đa tại một level
  Attack: fgsm
  Level: 4
  Loại ngưỡng: Mức sụt tương đối
  Mức sụt tối đa: 60%
```

Đối với đánh giá thực tế, nên tăng slice lên khoảng `300` ảnh trở lên, chọn các level phù hợp với
attack và đặt ngưỡng dựa trên baseline thực tế của model. Mức 60% trong ví dụ chủ yếu nhằm giúp
luồng demo dễ hoàn thành.

