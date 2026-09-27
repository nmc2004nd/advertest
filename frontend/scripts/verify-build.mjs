// Kiểm tra bản build production (dist/) không chứa trang dev và dữ liệu mock.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const FORBIDDEN = ['/dev/contracts', 'ContractsPage', 'contracts/mocks']

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

const hits = files('dist').flatMap((file) => {
  const text = readFileSync(file, 'utf8')
  return FORBIDDEN.filter((needle) => text.includes(needle)).map((needle) => `${file}: ${needle}`)
})

if (hits.length > 0) {
  console.error('Bản build production chứa nội dung chỉ dành cho dev:\n' + hits.join('\n'))
  process.exit(1)
}
console.log('dist/ không chứa /dev/contracts hay dữ liệu mock.')
