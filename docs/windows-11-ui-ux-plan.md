# SnapEdit — Kế hoạch UI/UX theo Windows 11

Ngày: 2026-09-08. Trạng thái: đã triển khai đợt đầu trên source; các hạng mục còn lại giữ trong roadmap.

## 1. Hướng thiết kế

Giữ PyQt6 và luồng làm việc từ tray/hotkey. Editor tập trung vào ảnh chụp; công cụ được phân nhóm, thuộc tính xuất hiện theo ngữ cảnh. Thiết kế Fluent trên nền Qt, không mặc định chuyển framework sang WinUI 3.

Microsoft cung cấp nguyên tắc về màu, chữ, hình học, bố cục và tương tác; các quyết định bố trí cụ thể bên dưới là đề xuất cho SnapEdit. Tham chiếu: [Guidelines overview](https://learn.microsoft.com/en-us/windows/apps/design/guidelines-overview).

## 2. Đối chiếu source hiện tại

| Khu vực | Hiện trạng đã đọc trong source | Việc cần làm |
| --- | --- | --- |
| Theme | `theme.py` có token Fluent; `main.py` áp dụng Fusion và dark palette cố định | Theme System/Light/Dark, màu theo vai trò, trạng thái focus và disabled |
| Toolbar | Công cụ, thuộc tính, Undo/Redo, Copy, Gallery, Save chung một hàng; nút cơ sở 24×24 | Vùng bấm rộng hơn, chia hàng chức năng, overflow thật |
| Cửa sổ hẹp | `_update_compact_mode()` ẩn Undo/Redo; Settings/Gallery có minimum size lớn | Lệnh luôn có đường truy cập; layout co giãn và nội dung cuộn |
| Thuộc tính | Toolbar có control theo tool; canvas còn popup cho object | Đồng bộ theo object đang chọn; ghi rõ thuộc tính mặc định của nét mới |
| Gallery | Một lần click thumbnail mở ngay; đọc thumbnails cho toàn bộ danh sách | Click chọn, Enter/double-click/Open để mở; tải thumbnail có giới hạn |
| OCR | Tên tray `Text OCR`; thông báo còn trộn Anh/Việt, hiển thị lỗi thô | Ngôn ngữ UI nhất quán, phân biệt đang đọc/không có chữ/lỗi |
| DPI và RAM | Đã có WindowScaler, giải phóng scene/popup, cache ảnh giới hạn | Giữ các cơ chế này, mở rộng kiểm tra khi đổi layout/theme |

Đây là đánh giá dựa trên mã nguồn. Đợt triển khai đầu đã áp dụng command bar/context row, responsive compact mode, zoom/status controls, Settings scrolling/focus state và tray shortcut refresh; kiểm thử trực quan trên nhiều máy vẫn là bước tiếp theo.

## 3. Nền tảng giao diện

- Font chính Segoe UI Variable, fallback Segoe UI; kiểm tra fallback tiếng Nhật bằng Yu Gothic UI. Body 14, caption 12, section 20, page title 28 đơn vị thiết kế. Theo [Typography](https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/typography).
- Spacing dùng thang 4/8/12/16/24. Control radius 4, flyout/dialog radius 8. Hình học của ảnh, selection và annotation không bị bo theo theme. Theo [Geometry](https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/geometry).
- Kích thước đề xuất riêng cho app: icon toolbar 20, icon menu 16, vùng bấm toolbar 36×36; control thường cao 32–36. Có thể tăng theo text scaling; không khóa chiều cao làm cắt chữ.
- Icon hệ thống ưu tiên Segoe Fluent Icons có sẵn; icon vẽ shape đặc thù giữ đường vector đồng nhất. Không dùng emoji làm command icon. Theo [Iconography](https://learn.microsoft.com/en-us/windows/apps/design/iconography/).
- Mặc định theme System; cho chọn Light/Dark. Token theo vai trò: window, canvas surround, control, hover, selected, disabled, text, border, accent, success, warning, error. Accent nhấn vào công cụ đang chọn và hành động chính. Theo [Color](https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/color).
- Khung cửa sổ và nút minimize/maximize/close dùng hành vi Windows hiện có; kiểm tra Snap Layouts, Alt+Space, resize và maximized. DWM bo góc phụ thuộc trạng thái cửa sổ, không ép góc khi snapped/maximized. Theo [Desktop rounded corners](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/ui/apply-rounded-corners).
- Mica là thử nghiệm bổ sung cho nền editor/Settings sau khi layout ổn định. Không coi QSS bán trong suốt là Mica. Nền màu đặc là fallback khi tích hợp Qt/DWM không phù hợp. Acrylic chỉ cân nhắc ở menu/flyout tạm; canvas và vùng chụp giữ pixel gốc. Theo [Materials](https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/materials) và [Mica](https://learn.microsoft.com/en-us/windows/apps/design/style/mica).

Các kích thước trên dùng đơn vị logic ở 100%, không phải pixel ảnh chụp. Vì app chủ động tắt Qt auto scaling cho overlay, chuyển đổi sang pixel vật lý qua WindowScaler đúng một lần. Không bật auto scaling toàn app trong đợt redesign.

## 4. Editor

Sơ đồ chỉ mô tả thứ bậc và vị trí, chưa phải mockup pixel-perfect:

```text
┌ SnapEdit — Editor ──────────────────────────────── ─ □ × ┐
│ Select Text Line Arrow Rect Ellipse Bubble | Undo Redo   │
│                                [Copy] [Save] [More …]   │
├ Thuộc tính: Stroke [màu]  Width [3 px]  Fill [ ] ─────────┤
│                                                        │
│                       ẢNH CHỤP                         │
│                                                        │
├ 1920 × 1080 px                 Zoom [−] [80%] [+] [Fit] ┤
└────────────────────────────────────────────────────────┘
```

Ở cửa sổ rộng, công cụ và Copy/Save/More nằm trên cùng một hàng command bar; hai dòng trong sơ đồ nhằm dễ đọc tên. Một hàng thứ hai cố định dành cho thuộc tính.

1. Giữ bảy công cụ quen thuộc và phím tắt hiện có. Copy có nhãn và accent nhẹ; Save có nhãn. Gallery nằm trong More và vẫn dùng Ctrl+G.
2. Thuộc tính theo tool/object: shape → màu, độ dày, fill; text → màu chữ, nền, cỡ chữ; bubble → màu và thuộc tính đang hỗ trợ. Khi không chọn object, ghi rõ đây là mặc định cho đối tượng mới. Khi chọn object, phản ánh giá trị của nó; multi-selection có trạng thái mixed.
3. Dành sẵn chiều cao hàng thuộc tính để ảnh không nhảy khi đổi tool. Context menu trên object giữ các lệnh phụ; không mở nhiều bảng thuộc tính trùng nhau.
4. Undo/Redo nhận enabled state từ QUndoStack. Mỗi thay đổi thuộc tính của object cần undo được; thay đổi DPI/theme không trở thành edit.
5. Zoom có giá trị hiện tại, Fit và 100%; Ctrl+wheel giữ nguyên. Phân biệt zoom nội dung với scale UI.
6. Copy/Save báo kết quả ngắn trên status bar. Chỉ báo Save thành công sau khi ghi ảnh thành công. Khi thay ảnh hoặc đóng editor có annotation chưa xuất, cho Save/Discard/Cancel; không hỏi với capture chưa chỉnh sửa.

Việc ưu tiên lệnh và đưa lệnh phụ vào More dựa trên [Command bar](https://learn.microsoft.com/en-us/windows/apps/design/controls/command-bar). Bố cục hai hàng là quyết định riêng cho SnapEdit.

## 5. Responsive, màn hình 13 inch và 27 inch 4K

Tính breakpoint bằng chiều rộng client quy về đơn vị logic. Microsoft hướng dẫn dựa vào cửa sổ thực tế và effective pixels: [Responsive layout](https://learn.microsoft.com/en-us/windows/apps/design/layout/screen-sizes-and-breakpoints-for-responsive-design).

| Chiều rộng logic đề xuất | Hành vi |
| --- | --- |
| Từ 1008 | Đầy đủ công cụ, Undo/Redo, Copy/Save có nhãn |
| 640–1007 | Giữ công cụ chính và xuất ảnh; chuyển lệnh thiếu chỗ vào More; thuộc tính rút nhãn hoặc mở flyout |
| Dưới 640 | Gom Line/Rect/Ellipse vào Shapes; Properties thành flyout; Copy và More luôn truy cập được |

Breakpoint chỉ là điểm bắt đầu; đo kích thước chữ/control thực tế để tránh cắt khi tăng text size. Không làm nút nhỏ lại để nhét vừa.

- Settings có navigation thu gọn khi hẹp, nội dung cuộn dọc, footer luôn truy cập được. Minimum size phải phù hợp work area; Gallery tương tự.
- Test 100/125/150/200/250% và di chuyển qua hai màn hình khác DPI, kể cả tọa độ âm.
- Windows text size phải được xét riêng với display scaling. Trên 4K đặt 100%, kích thước UI vẫn theo 100%; không suy đoán tỷ lệ dựa trên số inch. Có thể bổ sung UI size riêng nếu người dùng muốn, ngoài phạm vi bắt buộc của đợt đầu.
- Pixel ảnh xuất và annotation cũ giữ nguyên khi chuyển màn hình; mặc định nét mới tiếp tục theo hành vi DPI đã có.

## 6. Tray, chọn vùng và Text OCR

- Tray chia nhóm Capture full screen / Capture region / Timed region capture / Text OCR; nhóm Gallery / Settings; nhóm Exit SnapEdit. Hiện hotkey thực tế đang cấu hình ở cột phải, tự cập nhật sau khi Save Settings.
- Nhãn `Text OCR` thống nhất ở tray, Settings và tooltip. Lệnh menu và hotkey dùng chung action routing, tránh đăng ký shortcut thêm gây chạy hai lần.
- Chọn vùng có hint ngắn theo chế độ: kéo để chụp hoặc lấy chữ; Esc hủy. Viền rõ trên cả nền trắng/đen; kích thước vùng được đặt trong work area. Hint/UI không lọt vào kết quả capture.
- Timed capture giữ lựa chọn 3/5/10 giây và khả năng tương tác với desktop khi đếm ngược; bảng điều khiển đủ lớn và không bị cắt ở mép màn hình.
- Luồng OCR: chọn vùng → xử lý nền → copy. Không thêm bước xác nhận hay editor OCR bắt buộc.
- Nếu OCR kéo dài hơn ngưỡng đề xuất 300 ms, hiện trạng thái nhỏ không giành focus. Hoàn tất: “Text copied”; không có chữ: “No text found. Try another area.”; lỗi: thông báo dễ hiểu và đường mở chi tiết. Không có chữ/lỗi không ghi đè clipboard cũ.
- Phân biệt thiếu OCR language, thiếu thư viện/quyền đọc và nhận diện thất bại; chỉ hướng dẫn cài language khi thực sự thiếu. Chi tiết exception để trong phần chẩn đoán, không đưa thẳng vào toast.
- Dùng một cơ chế thông báo thành công cho mỗi thao tác; tôn trọng cài đặt thông báo. Thông báo chạy nền khi startup chỉ cần lần đầu hoặc khi có vấn đề.
- Giữ sửa lỗi tiếng Nhật và khoảng trắng quanh `々`; thiết kế UI không tự đổi thuật toán OCR. Bộ chọn ngôn ngữ OCR là hạng mục riêng nếu bổ sung về sau.

## 7. Settings và Gallery

Settings giữ ba nhóm General / Hotkeys / Storage; các property Drawing được chỉnh ngay trong editor và lưu lại cho lần sau. Theme nằm trong General; hàng Text OCR trong Hotkeys. Mỗi hàng có tên, mô tả ngắn khi cần, control căn thẳng hàng. UI dùng English nhất quán với phần lớn app hiện tại, vẫn hỗ trợ nội dung tiếng Nhật/Việt.

Giữ cơ chế Save/Cancel. Mở Settings tạo bản nháp; Reset chỉ đổi bản nháp; Cancel không ghi thay đổi. Save kiểm tra phím trùng trong app, kiểm tra đăng ký hotkey thật với Windows và lỗi thư mục, rồi áp dụng có rollback nếu thất bại. Không để mất binding cũ khi hotkey mới không đăng ký được.

Gallery có Recent captures và Saved images, thumbnail cùng tỉ lệ ô, ảnh không bị méo. Single click chọn; double-click/Enter hoặc nút Open mới mở. Thêm Open folder và empty/error state rõ ràng. Phân biệt không có ảnh với không có quyền đọc thư mục. Thumbnail tải theo nhu cầu, cache hữu hạn và hủy tác vụ khi đóng.

## 8. Accessibility và hiệu năng

Tab order ổn định, focus ring rõ, accessible name/role cho icon button và custom control; Escape đóng menu/flyout, trả focus về control gọi. Phím V/T/A… không đổi tool khi người dùng đang nhập text. Hỗ trợ high contrast và giảm chuyển động theo Windows. Kiểm tra Narrator cho tray, toolbar, Settings và thông báo. Theo [Accessibility](https://learn.microsoft.com/en-us/windows/apps/design/accessibility/accessibility-overview).

Chữ thông thường đặt mục tiêu contrast tối thiểu 4.5:1; chọn palette tương phản cao khi hệ thống yêu cầu. Theo [Accessible text](https://learn.microsoft.com/en-us/windows/apps/design/accessibility/accessible-text-requirements).

Đo baseline source trước thay đổi: thời gian khởi động, lần chọn vùng đầu tiên, mở editor, OCR, RAM sau đóng cửa sổ. So sánh cùng máy/cùng kích thước ảnh ở các vòng lặp. Giữ cache recent tối đa 5 ảnh/64 MiB, giải phóng scene/scaler/dialog và giới hạn cache icon/thumbnail. Không đặt lại mục tiêu RAM dưới 20 MiB. Hiệu ứng chỉ bật nếu không gây trễ hoặc tăng bộ nhớ kéo dài.

## 9. Thứ tự triển khai và nghiệm thu

| Đợt | Kết quả | File chính dự kiến | Điều kiện hoàn tất |
| --- | --- | --- | --- |
| 0 — Preview | Mockup editor light/dark ở rộng và hẹp; Settings, tray/OCR; bảng state hover/pressed/checked/disabled/focus | Tài liệu và preview riêng | Đánh giá trực quan layout trước khi thay nhiều màn hình; ghi baseline |
| 1 — Nền tảng | Theme service, typography/spacing tokens, icon renderer, control states, tích hợp DPI | `theme.py`, `ui_widgets.py`, `ui_scaling.py`, `main.py` | Đổi theme/DPI không scale lặp hay sinh cache vô hạn |
| 2 — Editor | Command bar, context row, overflow, zoom, undo state, feedback xuất ảnh | `editor/toolbar.py`, `editor/editor_window.py`, `editor/canvas.py` | Tất cả lệnh dùng được ở cửa sổ hẹp; drawing/export/undo đúng |
| 3 — Các luồng còn lại | Tray, capture hint, OCR state, Settings, Gallery | `main.py`, `capture/*`, `settings/*`, `editor/gallery_dialog.py` | Không thêm bước cản OCR; Save/Cancel đúng; popup/thumbnail được giải phóng |
| 4 — Windows polish | Thử nghiệm DWM/Mica, system preference changes, accessibility và kiểm tra tích hợp | `windows_integration.py`, các component mới, tests | Native window behavior đúng, fallback tốt, đạt ma trận DPI/theme/RAM |

Implementation note: style hiện được tạo bằng f-string/import hằng và WindowScaler giữ bản QSS gốc. Theme service phải dựng lại QSS từ token chưa scale rồi cập nhật bản gốc của scaler; không chỉ đổi palette toàn app hoặc scale tiếp chuỗi QSS đã scale. Khi responsive tạo control mới, phải bảo đảm control được đăng ký scale và focus đúng.

Ma trận nghiệm thu cuối: Light/Dark/System/High contrast × DPI phổ biến × cửa sổ rộng/hẹp; di chuyển màn hình; nhập annotation bằng IME Nhật; hotkey/cancel; OCR Nhật/Anh/rỗng/lỗi; save lỗi; Gallery rỗng/lỗi; 20–50 vòng mở/đóng để kiểm tra bộ nhớ. Tận dụng các regression test DPI, lifecycle, hotkeys, OCR hiện có và bổ sung test hành vi cần thiết.

Trong quá trình triển khai kiểm tra source bằng `python main.py` bằng tài khoản Windows của người dùng; không chỉ dựa vào import test trong tài khoản sandbox. Theo yêu cầu hiện tại, không tự build `.exe`; người dùng sẽ build sau khi test source.
