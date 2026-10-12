// Phase R3 Group 6: admin catalog, duyệt spec, đăng ký model (validation.md Group 6).
import type { ReactNode } from 'react'
import { Route, Routes } from 'react-router'
import { describe, expect, it } from 'vitest'

import { listMocks, mockMe, modelMocks } from '@/api/mocks'
import type { AttackAdapterInfo, AttackSpecAdminPage, AttackSpecAdminView } from '@/contracts/api'
import { visibleNav } from '@/nav/config'
import { PendingSpecsPage } from '@/pages/PendingSpecsPage'
import { render } from '@/test-utils'

import { ModelDetailPage } from './ModelDetailPage'
import { ModelsPage, OnnxLayouts, RegisterModelForm } from './ModelsPage'
import { SpecCreatePage } from './SpecCreatePage'
import { SpecDetailPage } from './SpecDetailPage'

const ALL_SPECS_KEY = ['admin', 'attack-specs', 'all']
const catalog = listMocks<AttackSpecAdminPage>('attack_spec_admin_page')[0].items
const views = listMocks<AttackSpecAdminView>('attack_spec_admin_view')
const adapters = listMocks<AttackAdapterInfo>('attack_adapter_info')
const models = modelMocks()

function view(status: AttackSpecAdminView['status']): AttackSpecAdminView {
  const found = views.find((v) => v.status === status && v.name === 'snow_light')
  if (!found) throw new Error(`Thiếu mock snow_light ${status}`)
  return found
}

function at(pattern: string, element: ReactNode) {
  return (
    <Routes>
      <Route path={pattern} element={element} />
    </Routes>
  )
}

function count(html: string, needle: string): number {
  return html.split(needle).length - 1
}

describe('/admin/attacks/new: form sinh từ params_schema', () => {
  const data: [readonly unknown[], unknown][] = [
    [ALL_SPECS_KEY, catalog],
    [['attack-adapters'], adapters],
  ]

  it('ô "Sao chép từ", "Tên spec", "Tên hiển thị", "Mô tả" và nút "Tạo spec"', () => {
    const html = render(<SpecCreatePage />, '/admin/attacks/new', 'admin', data)
    for (const label of ['Sao chép từ', 'Adapter', 'Tên spec', 'Tên hiển thị', 'Mô tả']) {
      expect(html).toContain(`>${label}</label>`)
    }
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*>Tạo spec<\/button>/)
    // Spec nguồn sắp theo tên: "snow v1" đứng trước biến thể "snow_…".
    const snowAt = html.indexOf('>snow v1')
    expect(snowAt).toBeGreaterThan(0)
  })

  it('?from=snow: điền sẵn adapter, tham số enum (danh sách chọn) và dải level', () => {
    const snow = catalog.find((s) => s.name === 'snow')
    if (!snow) throw new Error('Thiếu snow')
    const html = render(<SpecCreatePage />, `/admin/attacks/new?from=${snow.id}`, 'admin', data)
    expect(html).toContain('<option value="corruption.imagecorruptions" selected="">')
    expect(html).toContain('>corruption</label>')
    expect(html).toContain('<option value="&quot;snow&quot;" selected="">snow</option>')
    expect(html).toContain('value="severity"')
    expect(html).toContain('value="1, 2, 3, 4, 5"')
    expect(html).not.toContain('chưa hỗ trợ tạo qua giao diện')
  })

  it('tạo version mới: tên bị khóa, version kế tiếp', () => {
    const snow = catalog.find((s) => s.name === 'snow')
    if (!snow) throw new Error('Thiếu snow')
    const html = render(
      <SpecCreatePage />,
      `/admin/attacks/new?from=${snow.id}&mode=version`,
      'admin',
      data,
    )
    expect(html).toContain('Tạo version mới')
    expect(html).toMatch(/<input[^>]*readOnly=""[^>]*value="snow"/)
    expect(html).toContain('Spec sẽ có version 2.')
  })

  it('adapter có kiểu chưa hỗ trợ (mảng của patch): báo và vô hiệu nút tạo', () => {
    const patch = catalog.find((s) => s.name === 'adv_patch')
    if (!patch) throw new Error('Thiếu adv_patch')
    const patchAdapter: AttackAdapterInfo = {
      name: 'patch.robust_dpatch',
      kind: 'attack',
      requires_gradients: true,
      params_schema: {
        type: 'object',
        properties: { brightness_range: { type: 'array', items: { type: 'number' } } },
      },
    }
    const html = render(<SpecCreatePage />, `/admin/attacks/new?from=${patch.id}`, 'admin', [
      [ALL_SPECS_KEY, catalog],
      [['attack-adapters'], [...adapters, patchAdapter]],
    ])
    expect(html).toContain('Adapter này chưa hỗ trợ tạo qua giao diện')
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""[^>]*>Tạo spec<\/button>/)
  })
})

describe('/admin/attacks/:id: chi tiết spec', () => {
  function detail(spec: AttackSpecAdminView, extra: [readonly unknown[], unknown][] = []) {
    return render(
      at('/admin/attacks/:id', <SpecDetailPage />),
      `/admin/attacks/${spec.id}`,
      'admin',
      [[ALL_SPECS_KEY, [...catalog, spec]], ...extra],
    )
  }

  it('kiểm tra không đạt: 7 mục theo thứ tự, mục lỗi kèm details, nút "Kiểm tra lại"', () => {
    const spec = view('check_failed')
    const html = detail(spec)
    expect(html).toContain('data-testid="spec-status"')
    expect(html).toContain('Kiểm tra không đạt')
    expect(count(html, 'data-testid="check-item"')).toBe(7)
    const order = [...html.matchAll(/data-check="([a-z_]+)"/g)].map((m) => m[1])
    expect(order).toEqual([
      'runs',
      'value_range',
      'pad_unchanged',
      'identity',
      'batch_invariant',
      'norm_bound',
      'deterministic',
    ])
    const failed = spec.check?.items.find((i) => !i.passed)
    if (failed?.details) expect(html).toContain(failed.details)
    expect(html).toContain('Kiểm tra lại')
    expect(html).toContain('Sửa metadata')
    expect(html).toContain('Tạo version mới')
  })

  it('đang kiểm tra: ghi chú tự cập nhật, không có "Kiểm tra lại"', () => {
    const html = detail(view('checking'))
    expect(html).toContain('Đang kiểm tra')
    expect(html).toContain('Trang tự cập nhật')
    expect(html).not.toContain('Kiểm tra lại')
  })

  it('nháp bị từ chối: lý do từ audit log và hướng dẫn tạo version mới', () => {
    const spec = view('draft')
    const html = detail(spec, [
      [['audit', 'attack_spec.rejected', spec.id], 'Severity 3 trùng với snow.'],
    ])
    expect(html).toContain('Lý do từ chối: Severity 3 trùng với snow.')
    expect(html).toContain('tạo version mới')
  })

  it('id không có trong catalog: trạng thái trống', () => {
    const html = render(
      at('/admin/attacks/:id', <SpecDetailPage />),
      '/admin/attacks/00000000-0000-0000-0000-000000000000',
      'admin',
      [[ALL_SPECS_KEY, catalog]],
    )
    expect(html).toContain('data-testid="empty-state"')
  })
})

describe('/attack-specs/pending: reviewer kích hoạt hoặc từ chối', () => {
  const pending = view('pending_approval')

  function page(me: string, spec: AttackSpecAdminView = pending) {
    return render(<PendingSpecsPage />, '/attack-specs/pending', me, [
      [['attack-specs', 'pending'], [spec]],
      [['attack-specs'], catalog],
    ])
  }

  it('spec do chính mình tạo: hai nút bị vô hiệu kèm lý do', () => {
    expect(pending.created_by?.id).toBe(mockMe('reviewer').id)
    const html = page('reviewer')
    expect(count(html, 'data-testid="pending-spec"')).toBe(1)
    expect(html).toContain('Bạn đã tạo spec này')
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>.*Kích hoạt<\/button>/)
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>.*Từ chối<\/button>/)
  })

  it('spec người khác tạo: nút bật, kèm kết quả tự kiểm tra và khác biệt với version đang dùng', () => {
    const other = { ...pending, name: 'snow', version: 2 }
    const html = page('reviewer', {
      ...other,
      created_by: { id: '11111111-1111-4111-8111-111111111111', full_name: 'Người khác' },
    })
    expect(html).not.toContain('Bạn đã tạo spec này')
    expect(html).not.toMatch(/<button[^>]*disabled=""[^>]*>.*Kích hoạt<\/button>/)
    expect(html).toContain('So với snow v1 đang dùng')
    expect(html).toContain('primary_param.max')
    expect(html).toContain('Tự kiểm tra: 7/7 mục đạt')
  })

  it('không có spec chờ: trạng thái trống', () => {
    const html = render(<PendingSpecsPage />, '/attack-specs/pending', 'reviewer', [
      [['attack-specs', 'pending'], []],
      [['attack-specs'], catalog],
    ])
    expect(html).toContain('data-testid="empty-state"')
  })
})

describe('/admin/models: đăng ký và kiểm tra model', () => {
  it('danh sách có trạng thái và nút "Đăng ký model"', () => {
    const html = render(<ModelsPage />, '/admin/models', 'admin', [[['models'], models]])
    expect(html).toMatch(/<button[^>]*>.*Đăng ký model<\/button>/)
    for (const m of models) expect(html).toContain(`href="/admin/models/${m.id}"`)
    expect(html).toContain('data-status="check_failed"')
  })

  it('form: ô "Framework", "File weights" chỉ nhận .onnx/.safetensors; mặc định torchvision', () => {
    const html = render(<RegisterModelForm onCancel={() => undefined} />, '/admin/models', 'admin')
    expect(html).toContain('>Framework</label>')
    expect(html).toContain('>File weights</label>')
    expect(html).toContain('accept=".onnx,.safetensors"')
    expect(html).toContain('fasterrcnn_resnet50_fpn_v2')
    expect(html).not.toContain('data-testid="onnx-layouts"')
  })

  it('form: trường bắt buộc có mặc định để chọn (kích thước 640, class COCO 91 cho torchvision)', () => {
    const html = render(<RegisterModelForm onCancel={() => undefined} />, '/admin/models', 'admin')
    // File chọn trước tiên: các trường sau điền sẵn từ metadata của file.
    expect(html.indexOf('>File weights</label>')).toBeLessThan(html.indexOf('>Tên model</label>'))
    expect(html).toMatch(/role="radio" aria-checked="true"[^>]*>640</)
    expect(html).toContain('<option value="coco91" selected="">COCO 91 class (torchvision COCO_V1)')
    expect(html).toContain('91 class: __background__, person')
    expect(html).not.toContain('type="number"')
    expect(html).not.toContain('<textarea')
  })

  it('ghi chú hai layout ONNX', () => {
    const html = render(<OnnxLayouts />)
    expect(html).toContain('data-testid="onnx-layouts"')
    expect(html).toContain('(1, 4+C, N)')
    expect(html).toContain('boxes/scores/labels')
  })

  it('chi tiết model kiểm tra không đạt: trạng thái, kết quả kiểm tra, "Kiểm tra lại"', () => {
    const failed = models.find((m) => m.status === 'check_failed')
    if (!failed?.check) throw new Error('Thiếu mock model check_failed')
    const html = render(
      at('/admin/models/:id', <ModelDetailPage />),
      `/admin/models/${failed.id}`,
      'admin',
      [[['models', failed.id], failed]],
    )
    expect(html).toContain('data-testid="model-status"')
    expect(html).toContain('Kiểm tra không đạt')
    expect(html).toContain('data-testid="model-check"')
    if (failed.check.details) expect(html).toContain(failed.check.details)
    expect(html).toContain('Kiểm tra lại')
  })

  it('model sẵn sàng không có "Kiểm tra lại"', () => {
    const ready = models.find((m) => m.status === 'ready')
    if (!ready) throw new Error('Thiếu mock model ready')
    const html = render(
      at('/admin/models/:id', <ModelDetailPage />),
      `/admin/models/${ready.id}`,
      'admin',
      [[['models', ready.id], ready]],
    )
    expect(html).toContain('Sẵn sàng')
    expect(html).not.toContain('Kiểm tra lại')
  })
})

describe('điều hướng theo quyền (task 27)', () => {
  it('reviewer có "Spec chờ duyệt"; admin có "Model"; engineer không có cả hai', () => {
    const paths = (me: string) => visibleNav(mockMe(me)).map((i) => i.path)
    expect(paths('reviewer')).toContain('/attack-specs/pending')
    expect(paths('reviewer')).not.toContain('/admin/models')
    expect(paths('admin')).toContain('/admin/models')
    expect(paths('admin')).not.toContain('/attack-specs/pending')
    expect(paths('engineer')).not.toContain('/attack-specs/pending')
    expect(paths('engineer')).not.toContain('/admin/models')
  })
})
