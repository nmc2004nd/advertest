---
name: contract-proposal
description: Viết đề xuất thay đổi contract của AdverTest (schema, enum, OpenAPI, ma trận quyền, seed catalog, DB schema dùng chung) thay vì tự sửa, rồi dừng lại chờ người duyệt. Dùng skill này ngay khi một agent nhận ra cần thêm, đổi hoặc bỏ bất kỳ trường, schema, enum, endpoint, permission hay attack spec nào trong contracts/, hoặc khi người dùng yêu cầu "đề xuất đổi contract", kể cả khi đang giữa lúc implement một group.
---

# Đề xuất thay đổi contract

`contracts/` là thỏa thuận giữa các agent làm song song. Nếu một agent tự sửa, các agent khác đang code theo bản cũ sẽ lệch mà không biết. Vì vậy agent không sửa contract; agent viết đề xuất để người duyệt quyết định và cập nhật ở Group 0.

## 1. Dừng công việc đang làm

Commit phần việc đang dở (nếu ở trạng thái chạy được) với message `phaseNN(<agent>): wip trước đề xuất contract`. Không commit code phụ thuộc vào contract chưa được duyệt.

## 2. Viết file đề xuất

Đường dẫn: `specs/<thư mục phase hiện tại>/contract-proposals/NNN-<slug>.md`, với `NNN` là số thứ tự kế tiếp trong thư mục (bắt đầu `001`).

Để viết phần diff, chỉ trích đúng class, enum hoặc endpoint bị ảnh hưởng (`grep -n 'class Tên' contracts/python/advertest_contracts/models.py` rồi `sed -n` khoảng dòng; tương tự với seed và migration). Không Read nguyên `models.py` hay `openapi.json`. Phần "Ảnh hưởng" tìm nơi dùng bằng `grep -rln 'Tên' --include='*.py' --include='*.ts*' .`

```markdown
# Đề xuất contract NNN: <tiêu đề ngắn>

- Người đề xuất: agent <tên>, Phase NN, Group G
- Trạng thái: chờ duyệt

## Vấn đề
<điều gì trong spec hoặc contract hiện tại khiến việc implement không làm được hoặc sai; trích file:mục>

## Thay đổi đề xuất
<diff cụ thể trên file Pydantic / OpenAPI / seed / migration>

## Ảnh hưởng
| Agent / thư mục | Cần thay đổi gì |
- `schema_version`: tăng hay không, vì sao
- Mock cần cập nhật: ...
- Test nghiệm thu cần cập nhật: ...

## Phương án thay thế (không đổi contract)
<ít nhất một phương án, kèm nhược điểm>

## Khuyến nghị
<chọn phương án nào và lý do>
```

## 3. Báo cho người dùng và dừng

Tóm tắt đề xuất trong 3–5 dòng, đường dẫn file, và phần việc nào của group đang bị chặn. **Không** sửa `contracts/`, **không** tiếp tục phần việc phụ thuộc vào đề xuất.

Sau phần tóm tắt, hỏi bằng `AskUserQuestion` (một lần gọi, tối đa 2 câu):

1. `header` "Đề xuất": "Mình sẽ duyệt đề xuất sau, bạn chờ" / "Chọn phương án thay thế trong đề xuất, không đổi contract" (chỉ khi đề xuất có phương án thay thế khả thi).
2. Nếu còn phần việc của group không phụ thuộc vào đề xuất: `header` "Tiếp tục": "Làm tiếp các task không phụ thuộc (Khuyến nghị)" / "Dừng toàn bộ group"; mô tả liệt kê các task đó.

Ghi một dòng vào handoff của group (`.claude/handoff/phaseNN-gG-implement.md`): đường dẫn đề xuất, trạng thái, task bị chặn.

Nếu người dùng chọn phương án thay thế, cập nhật trạng thái trong file đề xuất thành "không áp dụng – dùng phương án thay thế" và tiếp tục theo phương án đó. Nếu công cụ không khả dụng hoặc trả về rỗng: hỏi bằng văn bản và dừng.
