import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

/**
 * Cảnh 3D "lụa" chuyển màu xanh → tím → hồng (tham khảo beehiiv): một trường độ cao được uốn bằng
 * nhiễu simplex, chiếu sáng giả bằng pháp tuyến tính từ đạo hàm nên các dải màu có khối, có vệt
 * bóng. Chạy bằng WebGL trên một canvas, chỉ tự trôi theo thời gian (không theo chuột). Không có WebGL
 * thì nền CSS gradient phía dưới vẫn hiện. `prefers-reduced-motion`: vẽ một khung hình rồi dừng.
 * Tạm dừng khi khung ra khỏi màn hình hoặc tab bị ẩn để không tốn pin.
 */

const VERT = `
attribute vec2 a;
void main(){ gl_Position = vec4(a, 0.0, 1.0); }
`

const FRAG = `
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform float uScale;
uniform float uPastel;

vec3 mod289(vec3 x){ return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x){ return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x){ return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r){ return 1.79284291400159 - 0.85373472095314 * r; }
float snoise(vec3 v){
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0)) + i.y + vec4(0.0, i1.y, i2.y, 1.0)) + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}

float warp(vec2 p, float t){
  return snoise(vec3(p * 0.75, t)) * 0.62 + snoise(vec3(p * 1.9 + 3.1, t * 1.35)) * 0.16;
}

// Độ cao của tấm lụa: các nếp gấp chạy chéo, bị nhiễu uốn cong.
float height(vec2 p, float t){
  float w = warp(p, t);
  float u = (p.x * 0.85 + p.y * 1.25 + w) * 8.5 * uScale;
  return sin(u) * 0.5 + 0.5 + sin(u * 2.0 + 1.3) * 0.12;
}

vec3 ramp(float x){
  // Lụa: xanh → tím → hồng → đào. Sóng (uPastel = 1): xanh oải hương → hồng phấn như ảnh mẫu.
  vec3 c0 = mix(vec3(0.145, 0.388, 0.922), vec3(0.33, 0.40, 0.90), uPastel);
  vec3 c1 = mix(vec3(0.486, 0.227, 0.929), vec3(0.56, 0.53, 0.93), uPastel);
  vec3 c2 = mix(vec3(0.925, 0.282, 0.600), vec3(0.87, 0.55, 0.82), uPastel);
  vec3 c3 = mix(vec3(0.984, 0.749, 0.627), vec3(0.96, 0.80, 0.91), uPastel);
  x = clamp(x, 0.0, 1.0);
  if (x < 0.36) return mix(c0, c1, smoothstep(0.0, 0.36, x));
  if (x < 0.72) return mix(c1, c2, smoothstep(0.36, 0.72, x));
  return mix(c2, c3, smoothstep(0.72, 1.0, x));
}

float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main(){
  vec2 p = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
  float t = uTime * 0.06;

  float e = 1.5 / uRes.y;
  float h = height(p, t);
  float hx = height(p + vec2(e, 0.0), t) - height(p - vec2(e, 0.0), t);
  float hy = height(p + vec2(0.0, e), t) - height(p - vec2(0.0, e), t);
  vec3 n = normalize(vec3(-hx / (2.0 * e) * 0.07, -hy / (2.0 * e) * 0.07, 1.0));

  vec3 L = normalize(vec3(-0.45, 0.55, 0.75));
  float diff = clamp(dot(n, L), 0.0, 1.0);
  vec3 V = vec3(0.0, 0.0, 1.0);
  float spec = pow(max(dot(reflect(-L, n), V), 0.0), 16.0);
  float rim = pow(1.0 - n.z, 2.0);

  float hue = 0.4 + 0.5 * (p.x * 0.55 - p.y * 0.35) + 0.22 * warp(p * 0.6 + 7.0, t * 0.7) + 0.12 * (h - 0.5);
  // Sóng: màu đổi theo từng dải để các lớp xanh và hồng xen nhau như ảnh mẫu.
  hue += uPastel * (smoothstep(0.25, 0.75, h) - 0.5) * 0.85;
  vec3 col = ramp(hue);
  col *= mix(0.48 + 0.72 * diff, 0.74 + 0.36 * diff, uPastel);
  col += spec * mix(0.5, 0.3, uPastel) * vec3(1.0, 0.95, 1.0);
  col += rim * 0.22 * ramp(hue + 0.25);
  // Vùng sáng phía trên như ánh đèn studio.
  float glow = 1.0 - smoothstep(-0.2, 0.9, length(p - vec2(-0.35, 0.55)));
  col = mix(col, vec3(0.98, 0.96, 1.0), glow * 0.28);
  col += (hash(gl_FragCoord.xy + fract(uTime)) - 0.5) * 0.035;
  gl_FragColor = vec4(col, 1.0);
}
`

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader | null {
  const shader = gl.createShader(type)
  if (!shader) return null
  gl.shaderSource(shader, src)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader)
    return null
  }
  return shader
}

export function GradientWaves({
  className,
  variant = 'silk',
  scale = variant === 'flow' ? 0.32 : 1,
  hexagons = variant === 'silk',
  speed = 1,
}: {
  className?: string
  /** `silk`: lụa nhiều nếp, màu đậm. `flow`: vài dải sóng lớn màu phấn (nền trang). */
  variant?: 'silk' | 'flow'
  /** Mật độ nếp gấp; lớn hơn = nhiều dải hơn. */
  scale?: number
  hexagons?: boolean
  speed?: number
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const gl = canvas.getContext('webgl', { antialias: false, premultipliedAlpha: false })
    if (!gl) return
    const vs = compile(gl, gl.VERTEX_SHADER, VERT)
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG)
    if (!vs || !fs) return
    const prog = gl.createProgram()
    gl.attachShader(prog, vs)
    gl.attachShader(prog, fs)
    gl.linkProgram(prog)
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS) || gl.isContextLost()) return
    gl.useProgram(prog)
    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const loc = gl.getAttribLocation(prog, 'a')
    gl.enableVertexAttribArray(loc)
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)
    const uRes = gl.getUniformLocation(prog, 'uRes')
    const uTime = gl.getUniformLocation(prog, 'uTime')
    const uScale = gl.getUniformLocation(prog, 'uScale')
    const uPastel = gl.getUniformLocation(prog, 'uPastel')
    gl.uniform1f(uScale, scale)
    gl.uniform1f(uPastel, variant === 'flow' ? 1 : 0)
    canvas.dataset.ready = 'true'

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let visible = true
    const start = performance.now() - 18000

    const resize = () => {
      // Độ phân giải thấp hơn màn hình một chút: cảnh mềm nên không thấy khác, nhẹ GPU hơn nhiều.
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5) * 0.7
      const w = Math.max(1, Math.round(canvas.clientWidth * ratio))
      const h = Math.max(1, Math.round(canvas.clientHeight * ratio))
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
        gl.viewport(0, 0, w, h)
      }
      gl.uniform2f(uRes, w, h)
    }

    const draw = (now: number) => {
      gl.uniform1f(uTime, ((now - start) / 1000) * speed)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
    }

    const loop = (now: number) => {
      draw(now)
      if (visible && !document.hidden) raf = requestAnimationFrame(loop)
      else raf = 0
    }
    const kick = () => {
      if (!reduce && !raf && visible && !document.hidden) raf = requestAnimationFrame(loop)
    }

    const ro = new ResizeObserver(() => {
      resize()
      if (reduce) draw(performance.now())
    })
    ro.observe(canvas)
    const io = new IntersectionObserver(([entry]) => {
      visible = entry?.isIntersecting ?? true
      kick()
    })
    io.observe(canvas)
    const onVis = () => kick()
    document.addEventListener('visibilitychange', onVis)
    resize()
    draw(performance.now())
    kick()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
      document.removeEventListener('visibilitychange', onVis)
      // Không gọi loseContext(): StrictMode chạy effect hai lần trên cùng canvas, context đã mất
      // sẽ không lấy lại được và cảnh chỉ còn màu trắng.
      gl.deleteBuffer(buf)
      gl.deleteProgram(prog)
      gl.deleteShader(vs)
      gl.deleteShader(fs)
    }
  }, [scale, speed, variant])

  return (
    <div aria-hidden className={cn('waves pointer-events-none overflow-hidden', className)}>
      <canvas ref={canvasRef} className="absolute inset-0 size-full" />
      {hexagons && <HexPattern />}
      <div className="waves-grain absolute inset-0" />
    </div>
  )
}

/** Lưới lục giác mảnh phủ lên cảnh (tham khảo họa tiết beehiiv), mờ dần ra mép. */
function HexPattern() {
  return (
    <svg className="waves-hex absolute inset-0 size-full">
      <defs>
        <pattern
          id="hex-grid"
          width="56"
          height="97"
          patternUnits="userSpaceOnUse"
          patternTransform="scale(1.1)"
        >
          <path
            d="M28 0 L56 16.2 L56 48.5 L28 64.7 L0 48.5 L0 16.2 Z M28 64.7 L28 97"
            fill="none"
            stroke="white"
            strokeWidth="1"
          />
        </pattern>
        <radialGradient id="hex-fade" cx="70%" cy="40%" r="75%">
          <stop offset="0" stopColor="white" stopOpacity="0.9" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </radialGradient>
        <mask id="hex-mask">
          <rect width="100%" height="100%" fill="url(#hex-fade)" />
        </mask>
      </defs>
      <rect width="100%" height="100%" fill="url(#hex-grid)" mask="url(#hex-mask)" />
    </svg>
  )
}
