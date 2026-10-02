/** Phase 8 (plan task 30): trang protocol và form xây dựng protocol. */
import { describe, expect, it } from 'vitest'

import { ApiError } from '@/api/errors'
import { listMocks } from '@/api/mocks'
import type { AttackSpec, ProtocolBody, ProtocolSummary, ProtocolView } from '@/contracts/api'
import { expectLabelledControls, render } from '@/test-utils'

import {
  buildProtocol,
  EMPTY_ATTACK,
  EMPTY_FORM,
  formOf,
  formPath,
  isShownPath,
  type ProtocolForm,
} from './form'
import { ProtocolEditor } from './ProtocolEditor'
import { ProtocolBodyView, ProtocolsPage } from './ProtocolsPage'

// Mock attack_spec thiếu fgsm: dùng seed của catalog (như test wizard).
const seedFiles = import.meta.glob<AttackSpec[]>('../../../../contracts/seeds/attack_specs.json', {
  eager: true,
  import: 'default',
})
const specs = Object.values(seedFiles)[0]
const bodies = Object.fromEntries(
  Object.entries(
    import.meta.glob<ProtocolBody>('../../../../contracts/mocks/protocol_body/*.json', {
      eager: true,
      import: 'default',
    }),
  ).map(([path, data]) => [path.split('/').pop()?.replace('.json', '') ?? path, data]),
)
const views = listMocks<ProtocolView>('protocol_view')
const summaries: ProtocolSummary[] = views.map(({ id, name, version, status, body_sha256 }) => ({
  id,
  name,
  version,
  status,
  body_sha256,
}))

describe('form protocol', () => {
  it.each(['default', 'search'])('body %s đi qua form rồi dựng lại y nguyên', (name) => {
    const body = bodies[name]
    const result = buildProtocol(formOf('P', body), specs)
    expect(result).toEqual({
      ok: true,
      name: 'P',
      body: {
        ...body,
        cases_to_review_per_attack: body.cases_to_review_per_attack ?? 5,
        forbid_dirty_runs: body.forbid_dirty_runs ?? true,
      },
    })
  })

  it('form trống báo lỗi từng trường, cần ít nhất một attack và một tiêu chí', () => {
    const empty = buildProtocol({ ...EMPTY_FORM, attacks: [], criteria: [] }, specs)
    expect(empty.ok).toBe(false)
    if (empty.ok) return
    expect(empty.errors).toMatchObject({
      name: expect.any(String),
      description: expect.any(String),
      attacks: 'Cần ít nhất một attack bắt buộc',
      criteria: 'Cần ít nhất một tiêu chí',
    })
  })

  it('cùng luật với contract: attack không trùng, level tiêu chí thuộc level bắt buộc, điểm gãy trong (lo, hi]', () => {
    const base = formOf('P', bodies.search)
    const form: ProtocolForm = {
      ...base,
      attacks: [...base.attacks, { ...EMPTY_ATTACK, name: 'fgsm', levels: '1' }],
      criteria: [
        { ...base.criteria[0], level: '3' },
        { ...base.criteria[1], level: '99' },
      ],
    }
    const result = buildProtocol(form, specs)
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.errors['attacks.2.name']).toBe('Mỗi attack chỉ một lần (một chế độ)')
    expect(result.errors['criteria.0.level']).toBe('Phải là một level bắt buộc của attack')
    expect(result.errors['criteria.1.level']).toMatch(/< level ≤/)
  })

  it('attack cần train patch không tìm ngưỡng được; tiêu chí sai loại theo chế độ', () => {
    const base = formOf('P', bodies.default)
    const patch = specs.find((s) => s.requires_training)
    if (!patch) throw new Error('seed thiếu attack cần train')
    const result = buildProtocol(
      {
        ...base,
        attacks: [...base.attacks, { ...EMPTY_ATTACK, name: patch.name, mode: 'search' }],
        criteria: [{ ...base.criteria[0], kind: 'min_breaking_point' }],
      },
      specs,
    )
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.errors['attacks.2.mode']).toMatch(/train patch/)
    expect(result.errors['criteria.0.kind']).toMatch(/tìm ngưỡng/)
  })

  it('đường dẫn lỗi 422 của server ánh xạ về form', () => {
    expect(formPath('body.required_attacks.1.spec_sha256')).toBe('attacks.1')
    expect(formPath('body.pass_criteria.0')).toBe('criteria.0')
    expect(formPath('body.required_attacks.0.mode')).toBe('attacks.0.mode')
    expect(formPath('body.min_slice_size')).toBe('minSliceSize')
    expect(formPath('name')).toBe('name')
    expect(isShownPath(formPath('body'))).toBe(false)
    expect(isShownPath(formPath('body.required_attacks.0.search'))).toBe(true)
  })

  it('lỗi 422 không gắn được với ô nào vẫn hiện ở đầu form', () => {
    const error = new ApiError(422, 'validation_error', 'Dữ liệu không hợp lệ', [
      { path: 'body', message: 'Tiêu chí 1 tham chiếu attack không bắt buộc' },
      { path: 'body.required_attacks.0.spec_sha256', message: 'Không có fgsm với hash này' },
    ])
    const html = render(
      <ProtocolEditor
        specs={specs}
        pending={false}
        error={error}
        submitLabel="Lưu"
        onSubmit={() => undefined}
        onCancel={() => undefined}
        initial={formOf('P', bodies.default)}
      />,
    )
    expect(html).toContain('Tiêu chí 1 tham chiếu attack không bắt buộc')
    expect(html).toContain('Không có fgsm với hash này')
  })

  it('form hiển thị đủ ô có nhãn; version mới khóa tên', () => {
    const props = {
      specs,
      pending: false,
      error: null,
      submitLabel: 'Lưu',
      onSubmit: () => undefined,
      onCancel: () => undefined,
    }
    const html = render(<ProtocolEditor {...props} initial={formOf('P', bodies.search)} lockName />)
    expect(html).toMatch(/id="protocol-ten"[^>]*disabled=""|disabled=""[^>]*id="protocol-ten"/)
    expect(html).toContain('Không chấp nhận run chạy từ code chưa commit')
    expect(html).toContain('Ngưỡng và class lấy theo cấu hình tìm ngưỡng của attack.')
    // Tên, mục đích, slice, số case; attack quét lưới 3 ô, tìm ngưỡng 9 ô; tiêu chí 6 + 3 ô.
    expectLabelledControls(html.replace(/<input type="checkbox"[^>]*>/g, ''), 4 + 3 + 9 + 6 + 3)
  })
})

describe('trang protocol', () => {
  it('reviewer: danh sách gồm bản đã ngừng dùng, nút tạo, version mới và ngừng dùng', () => {
    const html = render(<ProtocolsPage />, '/protocols', 'reviewer', [
      [['protocols', 'all'], summaries],
    ])
    expect(html).toContain('Tạo protocol')
    for (const p of summaries) expect(html).toContain(p.name)
    if (summaries.some((p) => p.status === 'retired')) expect(html).toContain('Đã ngừng dùng')
    expect(html).toContain('Tạo version mới')
    expect(html).toContain('Ngừng dùng')
  })

  it('engineer chỉ xem, không có nút sửa', () => {
    const html = render(<ProtocolsPage />, '/protocols', 'engineer', [
      [['protocols', 'all'], summaries],
    ])
    expect(html).toContain('Xem nội dung')
    expect(html).not.toContain('Tạo protocol</button>')
    expect(html).not.toContain('Tạo version mới')
  })

  it('nội dung version: attack bắt buộc, tiêu chí, điều kiện chung', () => {
    const view = views.find((v) => v.body.required_attacks.length > 0)
    if (!view) throw new Error('thiếu mock')
    const html = render(<ProtocolBodyView protocol={view} />)
    for (const a of view.body.required_attacks) expect(html).toContain(a.attack_spec_name)
    expect(html).toContain('Tiêu chí đạt')
    expect(html).toContain(`Slice tối thiểu ${view.body.min_slice_size}`)
  })
})
