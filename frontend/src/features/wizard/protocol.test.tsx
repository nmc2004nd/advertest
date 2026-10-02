/** Phase 8 (plan task 24): attack bắt buộc của protocol trong wizard; validation.md mục Frontend
 * unit "Wizard: chọn protocol → attack bắt buộc xuất hiện và không xóa được; ngưỡng bị khóa". */
import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { AttackSpec, EstimateResponse, ProtocolView } from '@/contracts/api'
import { render } from '@/test-utils'

import { applyLocks, requiredLocks, withoutLockedFields } from './protocol'
import { AttackStep } from './steps'
import { type Draft, EMPTY_DRAFT, reducer } from './state'

// Catalog đủ attack: seed của contract (mock `attack_spec` chỉ có 4 attack, thiếu fgsm).
const seedFiles = import.meta.glob<AttackSpec[]>('../../../../contracts/seeds/attack_specs.json', {
  eager: true,
  import: 'default',
})
const specs = Object.values(seedFiles)[0]
const views = listMocks<ProtocolView>('protocol_view')
const baseline = views.find((v) => v.name === 'kitti-baseline' && v.status === 'active')
const search = views.find((v) => v.name === 'kitti-search')
if (!baseline || !search) throw new Error('Thiếu mock protocol_view')
const spec = (name: string) => {
  const found = specs.find((s) => s.name === name)
  if (!found) throw new Error(`Thiếu mock ${name}`)
  return found
}

function withProtocol(view: ProtocolView, draft: Draft = EMPTY_DRAFT): Draft {
  const chosen = reducer(draft, { type: 'protocol', id: view.id })
  return reducer(chosen, {
    type: 'requirements',
    protocolId: view.id,
    locks: requiredLocks(view.body, specs).locks,
    minSliceSize: view.body.min_slice_size,
  })
}

describe('requiredLocks', () => {
  it('tra attack bắt buộc theo tên và spec_sha256 trong catalog', () => {
    const { locks, missing } = requiredLocks(baseline.body, specs)
    expect(missing).toEqual([])
    expect(locks.map((l) => [l.name, l.mode, l.levels])).toEqual([
      ['fgsm', 'grid', [2, 4, 8]],
      ['pgd_linf', 'grid', [2, 4, 8]],
    ])
  })

  it('attack không còn đúng version trong catalog thì báo thiếu', () => {
    const body = {
      ...baseline.body,
      required_attacks: [{ ...baseline.body.required_attacks[0], spec_sha256: '0'.repeat(64) }],
    }
    expect(requiredLocks(body, specs)).toEqual({ locks: [], missing: ['fgsm'] })
  })

  it('tìm ngưỡng: điền ngưỡng, dải, max_tol, bootstrap tối thiểu', () => {
    const lock = requiredLocks(search.body, specs).locks.find((l) => l.mode === 'search')
    expect(lock?.search).toMatchObject({
      thresholdKind: 'relative_drop',
      threshold: 0.2,
      classFilter: null,
      lo: 0,
      hi: 32,
      tol: 0.25,
      bootstrapSamples: 200,
    })
  })
})

describe('reducer với protocol', () => {
  it('chọn protocol → attack bắt buộc được thêm; không bỏ chọn, không đổi chế độ được', () => {
    const draft = withProtocol(baseline)
    const fgsm = spec('fgsm')
    expect(draft.attacks.map((a) => a.attackSpecId)).toContain(fgsm.id)
    expect(draft.minSliceSize).toBe(300)
    const toggled = reducer(draft, {
      type: 'toggleAttack',
      attackSpecId: fgsm.id,
      specSha256: fgsm.spec_sha256,
      requiresTraining: false,
    })
    expect(toggled).toBe(draft)
    const moded = reducer(draft, {
      type: 'mode',
      attackSpecId: fgsm.id,
      mode: 'search',
      defaults: requiredLocks(search.body, specs).locks[1].search!,
    })
    expect(moded).toBe(draft)
  })

  it('level bắt buộc không xóa được, level thêm vẫn giữ', () => {
    const draft = withProtocol(baseline)
    const fgsm = spec('fgsm').id
    const next = reducer(draft, { type: 'levels', attackSpecId: fgsm, levels: [16] })
    expect(next.attacks.find((a) => a.attackSpecId === fgsm)?.levels).toEqual([2, 4, 8, 16])
  })

  it('ngưỡng tìm kiếm bị khóa; dải, tol vẫn sửa được', () => {
    const draft = withProtocol(search)
    const pgd = spec('pgd_linf').id
    const next = reducer(draft, {
      type: 'search',
      attackSpecId: pgd,
      patch: { threshold: 0.5, thresholdKind: 'absolute_drop', classFilter: 'person', tol: 0.1 },
    })
    expect(next.attacks.find((a) => a.attackSpecId === pgd)?.search).toMatchObject({
      threshold: 0.2,
      thresholdKind: 'relative_drop',
      classFilter: null,
      tol: 0.1,
    })
  })

  it('đổi protocol bỏ khóa cũ; attack khác giữ nguyên khi áp khóa', () => {
    const draft = withProtocol(baseline)
    expect(reducer(draft, { type: 'protocol', id: search.id }).required).toEqual([])
    const extra = applyLocks(
      [{ ...draft.attacks[0], attackSpecId: 'khac', specSha256: 'x', levels: [1] }],
      draft.required,
    )
    expect(extra.map((a) => a.attackSpecId)).toEqual(['khac', spec('fgsm').id, spec('pgd_linf').id])
  })

  it('withoutLockedFields bỏ đúng ba trường ngưỡng', () => {
    expect(withoutLockedFields({ threshold: 0.3, lo: 1, classFilter: 'car' })).toEqual({ lo: 1 })
  })
})

describe('bước 4 với protocol', () => {
  it('attack bắt buộc có khóa "Theo protocol", ô chọn bị tắt, ngưỡng bị khóa', () => {
    const draft = { ...withProtocol(search), step: 4 as const }
    const html = render(
      <AttackStep
        draft={draft}
        dispatch={() => undefined}
        errors={{}}
        model={undefined}
        onLevelInputError={() => undefined}
        estimate={undefined as EstimateResponse | undefined}
      />,
      '/',
      'engineer',
      [[['attack-specs'], specs]],
    )
    expect(html).toContain('data-testid="khoa-pgd_linf"')
    expect(html).toContain('Theo protocol')
    expect(html).toContain('data-testid="nguong-khoa"')
    expect(html).toMatch(/<input type="checkbox"[^>]*disabled=""[^>]*>/)
    expect(html).toContain('aria-label="Level 2 bắt buộc theo protocol"')
  })
})
