# Hướng dẫn làm việc với agent theo spec

Tài liệu này hướng dẫn dùng 5 skill trong `.claude/skills/` và `CLAUDE.md` để giao các phase của AdverTest cho coding agent (Claude Code), theo quy trình spec-driven development.

## 1. Cài đặt (một lần)

1. Chép vào gốc repo:
   ```text
   advertest/
   ├── CLAUDE.md
   └── .claude/
       └── skills/
           ├── phase-kickoff/SKILL.md
           ├── phase-implement/SKILL.md
           ├── phase-review/SKILL.md
           ├── phase-review/scripts/scan_diff.sh
           ├── phase-close/SKILL.md
           └── contract-proposal/SKILL.md
   ```
2. `chmod +x .claude/skills/phase-review/scripts/scan_diff.sh`
3. Commit cả hai như code: `git add CLAUDE.md .claude && git commit -m "chore: agent workflow skills"`.
4. Mở Claude Code trong repo và hỏi: *"Dự án này có những skill nào?"* để chắc chắn 5 skill đã được nhận.

Claude Code đọc `CLAUDE.md` khi bắt đầu phiên, và tự dùng skill khi yêu cầu của bạn khớp với mô tả của skill. Bạn cũng có thể gọi đích danh bằng cách nêu tên skill trong prompt, ví dụ *"dùng skill phase-review cho nhánh phase01-model"*. Gọi đích danh là cách chắc chắn nhất.

## 2. Vai trò của bạn và của agent

| Việc | Ai làm |
|---|---|
| Viết và duyệt spec, trả lời câu hỏi mơ hồ | Bạn |
| Group 0 (contract), test nghiệm thu | Bạn (agent có thể soạn nháp, bạn duyệt từng dòng) |
| Implement từng group | Agent, dùng `phase-implement` |
| Review nhánh | Agent khác, dùng `phase-review`, trong phiên khác |
| Manual checks trong `validation.md` | Bạn |
| Quyết định merge | Bạn |
| Changelog, đánh dấu tiến độ, replan | Agent dùng `phase-close`, bạn xác nhận |

Nguyên tắc: **người làm không tự duyệt**. Đây cũng chính là nguyên tắc của sản phẩm AdverTest, áp dụng ngay trong cách phát triển nó.

## 3. Chuẩn bị cho nhiều agent làm song song

Mỗi agent một git worktree, một nhánh, một cửa sổ Claude Code:

```bash
# từ thư mục repo chính (nhánh main)
git worktree add ../advertest-ml-data   -b phase01-ml-data
git worktree add ../advertest-ml-model  -b phase01-ml-model
git worktree add ../advertest-ml-metric -b phase01-ml-metric

# mở mỗi thư mục trong một cửa sổ terminal riêng rồi chạy claude
cd ../advertest-ml-model && claude
```

Khi group xong và đã merge:

```bash
git worktree remove ../advertest-ml-model
git branch -d phase01-ml-model
```

Trước khi mở worktree cho một group, cập nhật `main` để worktree có đủ Group 0 và các group phụ thuộc.

## 4. Vòng làm việc của một phase

### Bước 1: Kickoff (một lần cho cả phase, trên `main`)

```text
Dùng skill phase-kickoff cho phase 1.
```

Agent đọc spec, báo cáo điều kiện tiên quyết, phân công, tối đa 5 câu hỏi và các lỗ hổng độ phủ, rồi dừng. Bạn trả lời, rồi:

```text
Đề xuất diff cập nhật spec theo các câu trả lời trên.
```

Duyệt diff, cho phép áp dụng (hoặc tự sửa), commit spec lên `main`. **Mọi quyết định phải vào spec trước khi có agent nào bắt đầu code.**

### Bước 2: Group 0 (bạn làm)

Tự sửa `contracts/`, mock, test nghiệm thu theo Group 0 của `plan.md`; chạy `make contracts` và `make check`; merge vào `main`. Có thể nhờ agent soạn nháp:

```text
Soạn nháp thay đổi contracts/ theo Group 0 của Phase 1, dưới dạng diff.
Không ghi file. Mình sẽ duyệt và tự áp dụng.
```

### Bước 3: Implement (mỗi group, trong worktree riêng)

```text
Dùng skill phase-implement. Bạn là agent ml-model, làm Group 3 của Phase 1.
```

Agent trả về kế hoạch thực thi và dừng. Đọc kỹ phần "Thư mục được sửa", "Test nghiệm thu sẽ pass", "Điểm cần người duyệt quyết định". Nếu ổn:

```text
Kế hoạch đã duyệt, làm đi.
```

Agent code theo task, commit từng task, và kết thúc bằng báo cáo có bảng validation. Nếu agent dừng giữa chừng để hỏi, trả lời rồi **ghi câu trả lời vào spec** nếu nó là quyết định thiết kế.

### Bước 4: Review (phiên mới, không dùng phiên đã code)

```text
Dùng skill phase-review cho nhánh phase01-ml-model, Phase 1, Group 3.
```

Nếu kết luận là "CẦN SỬA": quay lại phiên implement, dán danh sách phát hiện, yêu cầu sửa, rồi review lại. Nếu "SẴN SÀNG MERGE": tự làm các manual check mà reviewer liệt kê, rồi merge.

### Bước 5: Đóng group

```text
Dùng skill phase-close, chế độ đóng group, cho nhánh phase01-ml-model.
Mình đã review và đồng ý merge.
```

### Bước 6: Đóng phase và replan (khi mọi group xong)

```text
Dùng skill phase-close, đóng Phase 1.
```

Agent đi qua Definition of Done và hỏi bạn xác nhận từng manual check (kèm số liệu như baseline mAP, thời gian mỗi ảnh). Sau đó nó đề xuất diff cập nhật spec cho các phase sau. Duyệt, áp dụng, commit, rồi mới kickoff phase tiếp theo.

## 5. Ví dụ lịch làm Phase 1

| Thứ tự | Việc | Ở đâu |
|---|---|---|
| 1 | `phase-kickoff` phase 1, cập nhật spec | `main` |
| 2 | Group 0: thêm `ModelCard`, `CleanEvalResult` | `main` (bạn làm) |
| 3 | Group 1 (`ml-core`): store, letterbox, khung CLI | worktree `phase01-ml-core` |
| 4 | Review + merge Group 1 | phiên mới |
| 5 | Song song: Group 2 (`ml-data`), Group 3 (`ml-model`), Group 4 (`ml-metric`) | 3 worktree, 3 cửa sổ |
| 6 | Review + merge từng nhánh khi xong | phiên mới cho mỗi lần review |
| 7 | Group 5 (`ml-core`): eval, cache, viz | worktree `phase01-ml-core-2` |
| 8 | Group 6: bạn viết test nghiệm thu còn thiếu, chạy manual check trên KITTI | `main` |
| 9 | `phase-close` đóng Phase 1 và replan | `main` |

Nếu merge nhánh này làm nhánh khác xung đột, bảo agent của nhánh kia: *"main đã thay đổi, rebase nhánh này lên main và chạy lại make check"*.

## 6. Xử lý tình huống

**Agent đề xuất đổi contract** (skill `contract-proposal` tạo file trong `contract-proposals/`): đọc đề xuất, quyết định, nếu đồng ý thì tự cập nhật `contracts/` như một Group 0 bổ sung, merge vào `main`, rồi báo agent rebase và tiếp tục. Nếu không đồng ý, ghi lý do vào file đề xuất và chọn phương án thay thế trong đó.

**Reviewer phát hiện file cấm bị sửa hoặc test bị làm yếu:** không merge. Yêu cầu agent hoàn tác đúng phần đó (`git checkout main -- <file>`) và giải quyết bằng cách khác. Nếu test nghiệm thu thật sự sai, đó là việc của bạn: sửa test trên `main` và ghi vào changelog.

**Agent sửa mãi không được:** skill đã yêu cầu agent dừng sau 3 lần và viết báo cáo chẩn đoán. Đọc báo cáo, chọn hướng, hoặc quyết định kích hoạt phương án dự phòng trong spec (ví dụ Faster R-CNN ở Phase 1).

**Phiên quá dài, agent bắt đầu quên ràng buộc:** kết thúc phiên, mở phiên mới trong cùng worktree với *"Dùng skill phase-implement, agent X, tiếp tục Group G của Phase N từ task T"*. Mọi thứ cần thiết đã nằm trong spec, git log và báo cáo trước.

**Agent làm thêm việc ngoài phạm vi "cho tiện":** reviewer sẽ đánh dấu scope creep. Tách phần đó ra (hoàn tác), ghi ý tưởng vào backlog trong `roadmap.md` nếu đáng làm.

## 7. Cải tiến skill theo thời gian

Skill là code: khi thấy agent lặp lại một kiểu sai, sửa skill thay vì nhắc lại trong prompt mỗi lần. Ví dụ:
- agent hay quên chạy test nghiệm thu trước khi code → nhấn mạnh hơn trong `phase-implement` bước 3;
- reviewer hay bỏ sót một luật của mission → thêm vào mục 5 của `phase-review`;
- script quét bỏ sót một kiểu làm yếu test → thêm mẫu vào `scan_diff.sh`.

Commit mọi thay đổi của skill kèm lý do trong `CHANGELOG.md`, như bất kỳ thay đổi quy trình nào.
