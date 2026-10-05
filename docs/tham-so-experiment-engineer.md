# Giải thích các tham số Experiment dành cho Engineer

Tài liệu này giải thích wizard **Tạo experiment** của AdverTest dưới góc nhìn engineer: mỗi lựa
chọn có ý nghĩa gì, trường nào bị protocol khóa, các ràng buộc giữa model, dataset và attack, cũng
như cách đọc phần ước lượng trước khi chạy.

Protocol quy định mức kiểm thử tối thiểu. Experiment là cấu hình chạy cụ thể đáp ứng protocol đó.
Engineer có thể bổ sung attack hoặc level ngoài yêu cầu, nhưng không thể bỏ hay làm yếu những yêu
cầu đã được protocol chốt.

Wizard gồm sáu bước:

1. Protocol.
2. Model.
3. Dataset và slice.
4. Attack.
5. Máy chạy và giới hạn.
6. Xác nhận.

## 1. Chọn Protocol

Protocol quyết định các điều kiện tối thiểu mà experiment phải tuân thủ:

- attack và đúng version attack bắt buộc;
- chế độ Grid hoặc Search của từng attack bắt buộc;
- các level Grid không được bỏ;
- ngưỡng Search, class áp dụng và độ chính xác tối thiểu;
- kích thước slice tối thiểu;
- yêu cầu model hỗ trợ gradient;
- chính sách đối với code chưa commit;
- số failure case reviewer phải xem.

Khi chọn protocol, wizard tự thêm các attack bắt buộc và đánh dấu **Theo protocol**. Engineer
không thể:

- bỏ chọn attack đó;
- đổi chế độ chạy;
- xóa level bắt buộc;
- đổi loại ngưỡng, giá trị ngưỡng hoặc class của Search.

Engineer vẫn có thể:

- thêm attack không bắt buộc;
- thêm level ngoài các level bắt buộc;
- mở rộng dải Search;
- giảm `tol` để tìm chính xác hơn;
- tăng số mẫu bootstrap.

### Protocol chính thức và `dev-open`

- Protocol `active`: dùng cho experiment có thể gửi vào quy trình review chính thức.
- Protocol `dev-open`: dùng để thử nghiệm tự do, không có yêu cầu tuân thủ nhưng experiment không
  thể gửi duyệt.
- Protocol `retired`: không dùng để tạo experiment mới; experiment cũ đã gắn protocol này vẫn giữ
  nguyên tham chiếu.

Xem thêm [Giải thích các tham số của Protocol](tham-so-protocol.md).

## 2. Chọn Model

Mỗi lựa chọn model hiển thị:

| Thông tin | Ý nghĩa |
|---|---|
| Tên | Tên của model version đã đăng ký. |
| Framework | Framework dùng để chạy model. |
| Số class | Số class đầu ra mà model nhận diện. |
| Kích thước ảnh | Kích thước đầu vào của model. |
| Hỗ trợ gradient | Model có cung cấp gradient cho white-box attack hay không. |

Model được chọn là một version cụ thể, không chỉ là tên dòng model. Điều này giúp experiment có
thể tái lập và report xác định chính xác weights đã dùng.

### Quan hệ giữa model và attack

Một số attack, chẳng hạn FGSM hoặc PGD, cần gradient. Nếu model không hỗ trợ gradient:

- wizard hiển thị cảnh báo;
- run của attack cần gradient có thể bị `skipped` với lý do `incompatible`;
- nếu attack đó là yêu cầu bắt buộc của protocol, cấu hình không tuân thủ và không thể tạo
  experiment chính thức.

Khi đổi model, class mapping cũ được xóa khỏi bản nháp vì mapping phụ thuộc vào model version.

## 3. Dataset version, Slice và Class mapping

### Dataset version

Dataset version là một bản dữ liệu bất biến được nhận diện bằng manifest hash. Giao diện hiển thị:

- tên dataset;
- số ảnh của version;
- phần đầu của `manifest_sha256`;
- trạng thái ẩn danh.

Nếu dataset chưa được đánh dấu ẩn danh, ảnh failure case sẽ được làm mờ mặt và biển số trước khi
hiển thị.

### Slice đánh giá

Slice là tập con ảnh thực sự được dùng để đánh giá model. Mỗi slice có:

- tên;
- số ảnh;
- seed dùng khi tạo slice.

Wizard ẩn các slice nhỏ hơn `min_slice_size` của protocol. Ví dụ protocol yêu cầu ít nhất 300 ảnh
thì slice 100 ảnh sẽ không xuất hiện trong danh sách lựa chọn.

Khi đổi dataset version hoặc slice đánh giá, mọi lựa chọn slice huấn luyện của patch attack được
xóa để tránh giữ lại một tập huấn luyện không còn tương thích.

### Class mapping

Class mapping ánh xạ nhãn gốc của dataset sang class đầu ra của model.

Ví dụ:

```text
dataset `automobile` -> model `car`
dataset `pedestrian` -> model `person`
dataset `tram`       -> null (không đánh giá)
```

Mapping phải đồng thời:

- thuộc đúng model version đã chọn;
- thuộc đúng dataset version chứa slice đánh giá.

Nếu chỉ có một mapping hợp lệ, wizard tự chọn. Nếu chưa có mapping, admin phải đăng ký dữ liệu
trước khi engineer có thể tạo experiment.

Class mapping cũng quyết định danh sách class có thể chọn trong cấu hình Search.

## 4. Chọn và cấu hình Attack

Catalog chia các phép kiểm thử thành ba nhóm:

| Nhóm | Ý nghĩa |
|---|---|
| Tấn công | Adversarial attack như FGSM, PGD hoặc patch. |
| Biến đổi điều kiện | Corruption mô phỏng thay đổi môi trường hoặc chất lượng ảnh. |
| Che khuất | Phép biến đổi che một phần nội dung ảnh. |

Mỗi attack trong experiment lưu cả `attack_spec_id` và `spec_sha256`. Hai trường này được wizard
điền tự động để chốt đúng version của thuật toán, dải tham số và các tham số cố định.

Một experiment không được chứa cùng một attack hai lần. Muốn chạy nhiều cường độ, thêm nhiều
level vào cùng attack.

Nút **Toàn bộ catalog** chọn tất cả attack với bộ level gợi ý. Nên xem kỹ ước lượng thời gian vì
preset này có thể tạo nhiều run.

### Seed

Mọi attack tạo từ wizard hiện dùng seed cố định:

```text
seed = 0
```

Engineer không chỉnh seed trên giao diện. Seed cố định giúp kết quả có thể tái lập và tăng khả
năng dùng lại run hoặc patch đã có trong cache.

## 5. Chế độ Quét lưới (Grid)

Grid chạy attack tại từng level được chọn. Mỗi cặp `(attack, level)` tạo một run.

Ví dụ FGSM có tham số chính `eps`, đơn vị `1/255`:

```text
Level: 2, 4, 8
```

tương ứng với ba run:

```text
FGSM eps = 2/255
FGSM eps = 4/255
FGSM eps = 8/255
```

### Level

Level là giá trị của `primary_param` trong attack spec. Ý nghĩa và đơn vị phụ thuộc attack:

- FGSM/PGD có thể dùng `eps`, đơn vị `1/255`;
- corruption có thể dùng severity rời rạc;
- patch có thể dùng tỷ lệ diện tích.

Với tham số liên tục, engineer nhập level rồi chọn **Thêm**. Với tham số rời rạc, giao diện chỉ
cho chọn các giá trị hợp lệ.

Ràng buộc:

- mỗi attack Grid cần ít nhất một level;
- level phải nằm trong dải của spec;
- level không được trùng;
- tối đa 12 level mỗi attack;
- level bắt buộc theo protocol không thể bị xóa;
- tổng số run tối đa của experiment là 50, tính cả số điểm tối đa của Search.

Nút **Dùng bộ gợi ý** chọn một bộ level mặc định:

- tham số rời rạc: các giá trị hợp lệ của spec;
- tham số liên tục: thường là các lũy thừa của 2 nằm trong dải;
- patch attack: ưu tiên `0.1` và `0.25` nếu nằm trong dải.

### Dừng sớm khi model đã sụp

`early_stop` mặc định được bật cho mọi attack Grid.

Khi mAP@0.5 sau biến đổi còn không quá 5% mAP sạch, các level lớn hơn của cùng attack được bỏ qua.
Điều này tránh tốn thời gian chạy tiếp khi model đã gần như mất khả năng dự đoán.

Ví dụ:

```text
Level: 2, 4, 8, 16
Model sụp tại level 8
```

Run level 16 có thể được đánh dấu `skipped` do dừng sớm. Kết quả đã có tại các level trước vẫn
được giữ.

Dừng sớm chỉ áp dụng cho Grid, không áp dụng cho Search.

## 6. Slice huấn luyện cho Patch attack

Attack có `requires_training=true` phải train một patch trước khi đánh giá. Khi chọn loại attack
này, engineer bắt buộc chọn một **Slice huấn luyện**.

Slice huấn luyện phải:

- cùng dataset version với slice đánh giá;
- không có ảnh giao với slice đánh giá;
- không vượt quá `max_training_images` của attack spec;
- đã được đăng ký vào hệ thống.

Mỗi level train một patch riêng trên slice đã chọn. Ví dụ hai mức diện tích `0.1` và `0.25` có thể
cần hai patch. Nếu patch tương ứng đã tồn tại trong cache thì worker dùng lại và không train lại.

Search hiện không hỗ trợ patch attack vì mỗi điểm thử có thể yêu cầu train một patch mới, làm chi
phí tăng quá lớn. Patch attack chỉ dùng chế độ Grid.

## 7. Chế độ Tự tìm ngưỡng (Search)

Search tìm level nhỏ nhất mà một đại lượng suy giảm đạt hoặc vượt ngưỡng đã chọn. Thay vì chạy một
danh sách level cố định, worker quét thô rồi thu hẹp khoảng điểm gãy.

Các giai đoạn có thể gồm:

1. Quét thô trên tập con.
2. Chia đôi khoảng trên tập con.
3. Xác nhận trên toàn slice.
4. Chia đôi trên toàn slice đến khi khoảng đủ hẹp.

Nếu slice không lớn hơn `subset_size`, giai đoạn tập con có thể được bỏ qua.

### Loại ngưỡng

| Loại | Không chọn class | Khi chọn class |
|---|---|---|
| Mức sụt tương đối | `(mAP sạch - mAP bị attack) / mAP sạch` | Dùng AP@0.5 của class |
| Mức sụt tuyệt đối | `mAP sạch - mAP bị attack` | Hiệu AP@0.5 của class |
| Tỷ lệ tấn công thành công | ASR trên mọi object | ASR trên object của class |

### Ngưỡng (%)

Ngưỡng nằm trong `(0, 100%]`. Giao diện hiển thị phần trăm nhưng API lưu dưới dạng số từ 0 đến 1.

Ví dụ:

```text
Loại: Mức sụt tương đối
Ngưỡng: 20%
```

Worker tìm level đầu tiên khiến mAP giảm ít nhất 20% so với ảnh sạch.

Với mức sụt tuyệt đối, ngưỡng không thể lớn hơn mAP@0.5 sạch nếu hệ thống đã biết clean metric
của tổ hợp model, slice và mapping này.

### Class áp dụng

- **Mọi class**: dùng metric tổng thể.
- Một class cụ thể: dùng AP hoặc ASR riêng của class đích đó.

Danh sách chỉ gồm các class đích có trong class mapping. Class được protocol quy định sẽ bị khóa.

### Từ (`lo`) và Đến (`hi`)

Đây là dải level cần tìm kiếm:

```text
lo < điểm gãy <= hi
```

Hai cận phải nằm trong dải `primary_param` của attack. Với tham số rời rạc, chúng phải là giá trị
có trong danh sách của spec.

Nếu protocol yêu cầu một dải, engineer chỉ được giữ nguyên hoặc mở rộng dải đó:

```text
experiment.lo <= protocol.lo
experiment.hi >= protocol.hi
```

### Độ chính xác (`tol`)

Với tham số liên tục, `tol` là độ rộng tối đa của khoảng điểm gãy khi thuật toán dừng:

```text
điểm gãy nằm trong (a, b]
b - a <= tol
```

Mặc định:

```text
tol = (hi - lo) / 256
```

Giá trị phải lớn hơn 0 và nhỏ hơn `hi - lo`. `tol` càng nhỏ thì kết quả càng chính xác nhưng số
run tối đa càng tăng.

Nếu protocol quy định `max_tol`, engineer chỉ được dùng:

```text
tol <= protocol.max_tol
```

Tham số rời rạc không hiển thị ô `tol`; thuật toán chia theo chỉ số của danh sách giá trị.

### Số điểm quét thô (`coarse_n`)

Số level ban đầu dùng để tìm khu vực có điểm gãy:

- giá trị hợp lệ: từ 3 đến 8;
- mặc định: 4.

Giá trị lớn hơn có thể xác định vùng điểm gãy tốt hơn, nhưng cần thêm run ở giai đoạn đầu.

### Kích thước tập con (`subset_size`)

Số ảnh dùng trong giai đoạn tìm kiếm nhanh trước khi xác nhận trên toàn slice:

- tối thiểu 2 ảnh;
- không được lớn hơn số ảnh của slice;
- mặc định `min(100, số ảnh của slice)`, nhưng không thấp hơn 2.

Tập con nhỏ giúp chạy nhanh nhưng điểm gãy ước lượng có thể lệch nhiều so với toàn slice. Giao
diện cảnh báo khi chọn dưới 20 ảnh.

### Số mẫu bootstrap (`bootstrap_samples`)

Số mẫu bootstrap dùng để ước lượng khoảng tin cậy của điểm gãy:

- từ 0 đến 1000;
- mặc định 200;
- `0` nghĩa là không tính khoảng tin cậy.

Nếu protocol đặt `min_bootstrap_samples`, experiment phải dùng giá trị bằng hoặc lớn hơn mức đó.

### Giá trị mặc định của Search

| Trường | Mặc định |
|---|---|
| Loại ngưỡng | Mức sụt tương đối |
| Ngưỡng | 20% |
| Class | Mọi class |
| Dải | Toàn bộ dải của attack spec |
| `tol` | `(hi - lo) / 256` |
| `coarse_n` | 4 |
| `subset_size` | Tối đa 100 ảnh, không vượt kích thước slice |
| `bootstrap_samples` | 200 |

## 8. Máy chạy

Compute target là máy hoặc worker queue sẽ thực hiện experiment. Giao diện hiển thị:

- tên target;
- loại GPU hoặc **Chỉ CPU**;
- trạng thái online/offline;
- số job đang chờ;
- ước lượng thời gian với cấu hình hiện tại.

Phiên bản hiện tại chỉ cho chọn target loại `local`. Wizard ưu tiên tự chọn target local đang
online; nếu không có, nó chọn target local đầu tiên.

Target offline vẫn có thể nhận experiment vào hàng đợi, nhưng experiment sẽ không chạy cho tới khi
worker của target kết nối lại.

## 9. Giới hạn thời gian

Engineer nhập giới hạn theo phút. API lưu dưới dạng giây với:

```text
limit.kind = time
```

Giới hạn phải:

- lớn hơn 0;
- không vượt `max_time_limit_s` của compute target.

Khi đổi target, wizard đặt lại giới hạn về `default_time_limit_s` của target mới.

Giới hạn thời gian không phải thời gian chờ trong queue. Đây là mức tài nguyên thực thi của
experiment. Khi chạm giới hạn:

- worker dừng phần chưa chạy;
- kết quả đã hoàn thành được giữ lại;
- run hoặc Search chưa hoàn thành có thể mang trạng thái `stopped_limit`;
- kết quả tiêu chí có thể trở thành `inconclusive`.

Ước lượng vượt giới hạn chỉ tạo cảnh báo, không tự động tăng giới hạn và không luôn chặn tạo
experiment.

## 10. Ước lượng thời gian và hàng đợi

Đối với Grid, thời gian một run được ước lượng gần đúng bằng:

```text
số ảnh × số giây mỗi ảnh × 1.2
```

Hệ số `1.2` là khoảng đệm an toàn. Với patch attack, thời gian train patch được cộng riêng nếu
patch chưa có trong cache.

Với Search, giao diện hiển thị chi phí tối đa dựa trên:

- số điểm tối đa trên tập con;
- số điểm tối đa trên toàn slice;
- `subset_size`;
- kích thước toàn slice;
- cost profile của model, attack và compute target.

Search thường dừng trước mức tối đa khi khoảng điểm gãy đã đủ hẹp.

Nếu thiếu cost profile, giao diện báo chưa thể ước lượng tổng thời gian. Worker vẫn có thể chạy và
tự đo tốc độ để tạo profile cho các lần sau.

Phần hàng đợi hiển thị:

- vị trí dự kiến của experiment mới;
- tổng thời gian ước lượng của các experiment đứng trước.

Mỗi engineer được có tối đa 3 experiment ở trạng thái `queued`. Khi đã có đủ 3, phải chờ ít nhất
một experiment bắt đầu chạy trước khi tạo thêm.

## 11. Tên experiment

Tên là trường không bắt buộc, tối đa 200 ký tự.

Nếu để trống, server đặt tên theo mẫu:

```text
<model> · <slice> · <ngày UTC>
```

Nên đặt tên thể hiện mục tiêu hoặc thay đổi đang kiểm tra, ví dụ:

```text
yolov8n-kitti-fgsm-baseline
yolov8n-after-augmentation-v2
patch-robustness-release-2026-10
```

Tên không ảnh hưởng đến hash cấu hình và không làm thay đổi ước lượng.

## 12. Bảng tuân thủ Protocol

Ở phần tóm tắt, wizard gọi API ước lượng và hiển thị từng điều kiện:

| Điều kiện | Ý nghĩa |
|---|---|
| Protocol đang dùng được | Protocol còn ở trạng thái `active`. |
| Có attack bắt buộc | Cấu hình không thiếu attack protocol yêu cầu. |
| Đúng version attack | `spec_sha256` khớp version được protocol chốt. |
| Đúng chế độ | Grid/Search giống protocol. |
| Đủ level bắt buộc | Grid chứa mọi level protocol yêu cầu. |
| Đúng ngưỡng tìm kiếm | Loại ngưỡng, ngưỡng và class của Search khớp. |
| Dải tìm kiếm đủ rộng | Dải experiment bao phủ dải protocol. |
| Độ chính xác đủ nhỏ | `tol` không lớn hơn `max_tol`. |
| Đủ mẫu bootstrap | Số mẫu không thấp hơn protocol yêu cầu. |
| Slice đủ lớn | Số ảnh đạt `min_slice_size`. |
| Model hỗ trợ gradient | Model đáp ứng các attack bắt buộc cần gradient. |

Experiment chính thức chỉ được tạo khi tất cả mục tuân thủ đều đạt. Giao diện khóa các trường quan
trọng để giảm sai sót, nhưng backend vẫn kiểm tra lại toàn bộ cấu hình.

## 13. Xác nhận trước khi chạy

Bước cuối hiển thị:

- protocol;
- model;
- slice;
- compute target;
- giới hạn thời gian;
- seed;
- danh sách attack và chế độ;
- ước lượng từng run;
- thời gian train patch;
- chi phí tối đa của Search;
- vị trí hàng đợi;
- bảng tuân thủ protocol;
- các cảnh báo thiếu profile hoặc vượt giới hạn.

Khi bấm **Chạy experiment**, experiment được tạo trực tiếp ở trạng thái `queued`; đây không chỉ là
lưu cấu hình nháp. Bản nháp wizard trong trình duyệt được xóa sau khi tạo thành công.

## 14. Nhân bản experiment

Khi dùng **Nhân bản để sửa**, wizard điền lại cấu hình của experiment gốc và mở ở bước xác nhận.
Trường `cloned_from` lưu liên kết tới experiment gốc.

Nếu attack spec đã có version mới, cấu hình nhân bản được nâng lên version hiện hành và giao diện
hiển thị cảnh báo. Engineer nên quay lại bước Attack để kiểm tra dải, level và hành vi mới trước khi
chạy.

Nhân bản tạo experiment mới; nó không sửa experiment cũ.

## 15. Ví dụ cấu hình Grid cho demo

```text
Protocol: kitti-demo
Model: yolov8n-coco
Dataset version: KITTI đã import
Slice: fixture 5 ảnh hoặc slice thật >= 300 ảnh
Class mapping: mapping tương ứng giữa KITTI và COCO

Attack:
  fgsm v1
  Chế độ: Quét lưới
  Level: 2, 4
  Dừng sớm: bật
  Seed: 0

Máy chạy: local-dev
Giới hạn: theo mặc định của target
Tên: kitti-fgsm-demo
```

Nếu `fgsm` và các level được protocol yêu cầu, chúng xuất hiện sẵn với nhãn **Theo protocol**.

## 16. Ví dụ cấu hình Search

```text
Attack: fgsm
Chế độ: Tự tìm ngưỡng

Loại ngưỡng: Mức sụt tương đối
Ngưỡng: 20%
Class: Mọi class
Từ: 0
Đến: 32
Độ chính xác: 0.125

Nâng cao:
  Số điểm quét thô: 4
  Kích thước tập con: 100 ảnh
  Số mẫu bootstrap: 200
```

Cấu hình này tìm mức `eps` nhỏ nhất của FGSM làm mAP@0.5 giảm ít nhất 20%, trong dải từ 0 đến
32/255, với khoảng điểm gãy cuối cùng rộng không quá 0.125.

## 17. Checklist nhanh cho Engineer

Trước khi chạy, kiểm tra:

- protocol đúng mục tiêu và không phải `dev-open` nếu cần gửi duyệt;
- model hỗ trợ gradient nếu attack bắt buộc cần gradient;
- slice đủ lớn theo protocol;
- class mapping đúng model và dataset;
- mọi attack bắt buộc có nhãn **Theo protocol**;
- Grid có đủ level, Search có dải và độ chính xác hợp lý;
- patch attack đã chọn slice huấn luyện không giao với slice đánh giá;
- tổng số run và thời gian ước lượng phù hợp;
- giới hạn thời gian đủ để hoàn thành;
- bảng tuân thủ không còn mục lỗi;
- tên experiment giúp phân biệt mục đích của lần chạy.

