import { useState } from 'react'

import type { ClassMappingCreate, DatasetSummary, DifficultyFilter } from '@/contracts/api'
import { MODEL_ADMIN_COPY } from '@/copy/model-admin'

import {
  effectiveMapping,
  KITTI_COCO,
  KITTI_MODERATE,
  type MappingClasses,
  mappingError,
  suggestMapping,
} from './class-mapping'

export type Difficulty = 'moderate' | 'none'

interface VersionOption {
  id: string
  label: string
  classNames: string[]
}

function versionOptions(datasets: readonly DatasetSummary[]): VersionOption[] {
  return datasets.flatMap((dataset) =>
    dataset.versions.map((version, index) => ({
      id: version.id,
      label:
        `${dataset.name} · ${version.num_images} ảnh` +
        (dataset.versions.length > 1 ? ` · bản ${dataset.versions.length - index}` : ''),
      classNames: version.class_names,
    })),
  )
}

const looksKitti = (classes: readonly string[]) =>
  classes.length > 0 && classes.every((name) => name in KITTI_COCO)

export interface MappingDraft {
  options: VersionOption[]
  versionId: string | null
  setVersionId: (id: string) => void
  datasetClasses: string[]
  classes: MappingClasses
  setTarget: (source: string, target: string | null) => void
  difficulty: Difficulty
  setDifficulty: (value: Difficulty) => void
  error: string | null
  /** Thân `POST /class-mappings`; null khi chưa có dataset hoặc mapping chưa hợp lệ. */
  body: (modelVersionId: string) => ClassMappingCreate | null
}

/** Trạng thái chọn mapping: gợi ý theo preset hoặc tên trùng, người dùng đè từng class. */
export function useMappingDraft(
  datasets: readonly DatasetSummary[],
  modelClasses: readonly string[],
): MappingDraft {
  const options = versionOptions(datasets)
  const [chosen, setChosen] = useState<string | null>(null)
  const [overrides, setOverrides] = useState<MappingClasses>({})
  const [difficultyChoice, setDifficultyChoice] = useState<Difficulty | null>(null)
  const version = options.find((o) => o.id === chosen) ?? options[0] ?? null
  const datasetClasses = version?.classNames ?? []
  const classes = effectiveMapping(
    suggestMapping(datasetClasses, modelClasses),
    overrides,
    modelClasses,
  )
  const difficulty = difficultyChoice ?? (looksKitti(datasetClasses) ? 'moderate' : 'none')
  const error = version ? mappingError(classes) : MODEL_ADMIN_COPY.noDataset
  const filter: DifficultyFilter | null = difficulty === 'moderate' ? KITTI_MODERATE : null
  return {
    options,
    versionId: version?.id ?? null,
    setVersionId: (id) => {
      setChosen(id)
      setOverrides({})
      setDifficultyChoice(null)
    },
    datasetClasses,
    classes,
    setTarget: (source, target) => setOverrides((prev) => ({ ...prev, [source]: target })),
    difficulty,
    setDifficulty: setDifficultyChoice,
    error,
    body: (modelVersionId) =>
      version && error === null
        ? {
            dataset_version_id: version.id,
            model_version_id: modelVersionId,
            classes,
            difficulty: filter,
          }
        : null,
  }
}
