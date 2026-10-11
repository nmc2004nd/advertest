import { describe, expect, it } from 'vitest'

import { listMocks } from '@/api/mocks'
import type { AttackAdapterInfo, AttackSpecAdminPage, AttackSpecAdminView } from '@/contracts/api'

import {
  adapterOf,
  buildCreate,
  EMPTY_FORM,
  formFieldOf,
  NEEDS_SOURCE,
  nextVersion,
  parseLevelLabels,
  prefillFrom,
  schemaFields,
  type ParamField,
} from './spec-form'

const adapters = listMocks<AttackAdapterInfo>('attack_adapter_info')
const catalog = listMocks<AttackSpecAdminPage>('attack_spec_admin_page')[0].items

function adapter(name: string): AttackAdapterInfo {
  const found = adapters.find((a) => a.name === name)
  if (!found) throw new Error(`Thiếu mock adapter ${name}`)
  return found
}

function spec(name: string): AttackSpecAdminView {
  const found = catalog.find((s) => s.name === name)
  if (!found) throw new Error(`Thiếu spec ${name}`)
  return found
}

function fieldsOf(schema: AttackAdapterInfo['params_schema']): ParamField[] {
  const result = schemaFields(schema)
  if (!result.supported) throw new Error('schema không hỗ trợ')
  return result.fields
}

describe('schemaFields: form sinh từ params_schema (validation.md Group 6)', () => {
  it('mọi adapter của mock GET /attack-adapters đều dựng được form', () => {
    expect(adapters.length).toBeGreaterThan(0)
    for (const a of adapters) expect(schemaFields(a.params_schema).supported).toBe(true)
  })

  it('enum thành danh sách chọn, giữ thứ tự và kiểu', () => {
    const fields = fieldsOf(adapter('corruption.imagecorruptions').params_schema)
    expect(fields).toEqual([
      {
        key: 'corruption',
        required: true,
        kind: 'enum',
        options: ['fog', 'snow', 'frost', 'motion_blur', 'contrast'],
      },
    ])
    expect(fieldsOf({ properties: { norm: { enum: ['inf', 2] } } })[0]).toMatchObject({
      kind: 'enum',
      options: ['inf', 2],
    })
  })

  it('số giữ minimum/maximum và exclusiveMinimum; boolean thành công tắc', () => {
    const fields = fieldsOf({
      type: 'object',
      properties: {
        fill_255: { type: 'integer', minimum: 0, maximum: 255 },
        eps_step_ratio: { type: 'number', exclusiveMinimum: 0 },
        targeted: { type: 'boolean' },
      },
    })
    expect(fields).toEqual([
      {
        key: 'fill_255',
        required: false,
        kind: 'number',
        integer: true,
        min: 0,
        max: 255,
        exclusiveMin: false,
        exclusiveMax: false,
      },
      {
        key: 'eps_step_ratio',
        required: false,
        kind: 'number',
        integer: false,
        min: 0,
        max: undefined,
        exclusiveMin: true,
        exclusiveMax: false,
      },
      { key: 'targeted', required: false, kind: 'boolean' },
    ])
  })

  it('kiểu chưa hỗ trợ (mảng của patch, chuỗi tự do, object lồng) thì báo không hỗ trợ', () => {
    const patch = {
      type: 'object',
      properties: { brightness_range: { type: 'array', items: { type: 'number' } } },
    }
    expect(schemaFields(patch).supported).toBe(false)
    expect(schemaFields({ properties: { label: { type: 'string' } } }).supported).toBe(false)
    expect(schemaFields({ properties: { inner: { type: 'object' } } }).supported).toBe(false)
    expect(schemaFields({ type: 'array' }).supported).toBe(false)
  })
})

describe('adapter và version', () => {
  it('adapter suy từ kind và art_class khi spec seed không ghi', () => {
    expect(adapterOf(spec('snow'))).toBe('corruption.imagecorruptions')
    expect(adapterOf(spec('bbox_occlusion'))).toBe('occlusion.bbox')
    expect(adapterOf(spec('fgsm'))).toBe('art.evasion')
    expect(adapterOf(spec('adv_patch'))).toBe('patch.robust_dpatch')
    expect(adapterOf({ ...spec('snow'), adapter: 'corruption.khac' })).toBe('corruption.khac')
  })

  it('version tiếp theo theo tên', () => {
    expect(nextVersion('adv_patch', catalog)).toBe(3)
    expect(nextVersion('snow', catalog)).toBe(2)
    expect(nextVersion('snow_moi', catalog)).toBe(1)
  })
})

describe('buildCreate', () => {
  const corruption = adapter('corruption.imagecorruptions')
  const corruptionFields = fieldsOf(corruption.params_schema)

  function fromSnow(changes: Partial<typeof EMPTY_FORM> = {}) {
    return { ...prefillFrom(spec('snow'), corruptionFields), ...changes }
  }

  it('sao chép snow đổi tên: version 1, giữ tham số và dải level, adapter null như nguồn', () => {
    const values = fromSnow({ name: 'snow_e2e', displayName: 'Tuyết', description: 'Biến thể.' })
    const result = buildCreate(values, {
      adapter: corruption,
      fields: corruptionFields,
      source: spec('snow'),
      catalog,
    })
    if (!result.ok) throw new Error(JSON.stringify(result.errors))
    const snow = spec('snow')
    expect(result.body).toEqual({
      schema_version: 1,
      name: 'snow_e2e',
      version: 1,
      kind: 'corruption',
      access: snow.access,
      art_class: null,
      primary_param: snow.primary_param,
      fixed_params: { corruption: 'snow' },
      cost_model: snow.cost_model,
      requires_gradients: false,
      adapter: snow.adapter,
    })
    expect(result.metadata).toEqual({
      display_name: 'Tuyết',
      description: 'Biến thể.',
      realism: 'medium',
      level_labels: {},
    })
  })

  it('tạo version mới cùng tên: version lớn nhất + 1', () => {
    const values = fromSnow({ displayName: 'Tuyết', description: 'Mô tả' })
    const result = buildCreate(values, {
      adapter: corruption,
      fields: corruptionFields,
      source: spec('snow'),
      catalog,
    })
    expect(result.ok && result.body.version).toBe(2)
  })

  it('corruption không có nguồn: mặc định không áp dụng và chỉ CPU', () => {
    const values = {
      ...EMPTY_FORM,
      adapter: corruption.name,
      name: 'fog_light',
      params: { corruption: '"fog"' },
      primaryName: 'severity',
      primaryType: 'discrete' as const,
      primaryMin: '1',
      primaryMax: '3',
      primaryValues: '1, 2, 3',
      primaryUnit: 'severity',
      displayName: 'Sương nhẹ',
      description: 'Sương mù mức 1–3.',
      levelLabels: '1: mỏng\n3: dày',
    }
    const result = buildCreate(values, {
      adapter: corruption,
      fields: corruptionFields,
      source: undefined,
      catalog,
    })
    if (!result.ok) throw new Error(JSON.stringify(result.errors))
    expect(result.body).toMatchObject({
      access: 'not_applicable',
      art_class: null,
      cost_model: { passes_per_image: null, cpu_only: true },
      adapter: 'corruption.imagecorruptions',
      primary_param: { values: [1, 2, 3] },
      fixed_params: { corruption: 'fog' },
    })
    expect(result.metadata.level_labels).toEqual({ '1': 'mỏng', '3': 'dày' })
  })

  it('adapter kiểu attack không có spec nguồn cùng adapter thì báo cần sao chép', () => {
    const art = adapter('art.evasion')
    const result = buildCreate(
      { ...fromSnow(), adapter: art.name },
      { adapter: art, fields: [], source: spec('snow'), catalog },
    )
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.errors.sourceId).toBe(NEEDS_SOURCE)
  })

  it('attack sao chép từ fgsm giữ art_class, access, chi phí; enum giữ kiểu số', () => {
    const art = adapter('art.evasion')
    const fields = fieldsOf({ properties: { norm: { enum: ['inf', 2] } }, required: ['norm'] })
    const values = {
      ...prefillFrom(spec('fgsm'), fields),
      name: 'fgsm_l2',
      displayName: 'FGSM L2',
      description: 'FGSM chuẩn L2.',
    }
    values.params = { norm: '2' }
    const result = buildCreate(values, { adapter: art, fields, source: spec('fgsm'), catalog })
    if (!result.ok) throw new Error(JSON.stringify(result.errors))
    expect(result.body).toMatchObject({
      kind: 'attack',
      art_class: 'FastGradientMethod',
      access: 'white_box',
      cost_model: spec('fgsm').cost_model,
      requires_gradients: true,
      fixed_params: { norm: 2 },
    })
  })

  it('lỗi theo đúng trường: tên, tham số ngoài dải, dải level, nhãn level', () => {
    const fields = fieldsOf({
      properties: { fill_255: { type: 'integer', minimum: 0, maximum: 255 } },
      required: ['fill_255'],
    })
    const occlusion: AttackAdapterInfo = {
      name: 'occlusion.bbox',
      kind: 'occlusion',
      params_schema: {},
      requires_gradients: false,
    }
    const result = buildCreate(
      {
        ...EMPTY_FORM,
        adapter: 'occlusion.bbox',
        name: 'Che Box',
        params: { fill_255: '300' },
        primaryName: 'ratio',
        primaryMin: '0.9',
        primaryMax: '0.1',
        primaryUnit: 'ratio',
        levelLabels: 'nhẹ',
      },
      { adapter: occlusion, fields, source: undefined, catalog },
    )
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(Object.keys(result.errors).sort()).toEqual(
      ['description', 'displayName', 'levelLabels', 'name', 'params.fill_255', 'primaryMax'].sort(),
    )
    expect(result.errors['params.fill_255']).toBe('Nhập số nguyên ≥ 0 và ≤ 255.')
  })

  it('level rời rạc phải nằm trong dải', () => {
    const result = buildCreate(
      fromSnow({ primaryValues: '1, 9', displayName: 'a', description: 'b' }),
      {
        adapter: corruption,
        fields: corruptionFields,
        source: spec('snow'),
        catalog,
      },
    )
    expect(!result.ok && result.errors.primaryValues).toBeTruthy()
  })
})

describe('nhãn level và lỗi 422', () => {
  it('parseLevelLabels', () => {
    expect(parseLevelLabels('1: nhẹ\n\n2.5 : vừa')).toEqual({ '1': 'nhẹ', '2.5': 'vừa' })
    expect(parseLevelLabels('1: a\n1.0: b')).toBeInstanceOf(Error)
    expect(parseLevelLabels('x: a')).toBeInstanceOf(Error)
  })

  it('formFieldOf ánh xạ đường dẫn của server về trường form', () => {
    expect(formFieldOf('body.fixed_params.norm')).toBe('params.norm')
    expect(formFieldOf('body.primary_param.values')).toBe('primaryValues')
    expect(formFieldOf('body.version')).toBe('name')
    expect(formFieldOf('metadata.display_name')).toBe('displayName')
    expect(formFieldOf('metadata.level_labels')).toBe('levelLabels')
    expect(formFieldOf('body.cost_model')).toBeNull()
  })
})
