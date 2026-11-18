"use client";

import { useEffect, useRef } from "react";

// Flowing silk drawn on the GPU: domain-warped noise in the house palette
// (midnight base, cobalt folds, ice highlights, a faint tangerine rim). No library, about 2 KB.
const VERT = `attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;

const FRAG = `precision mediump float;
uniform vec2 r;uniform float t;uniform vec2 m;
float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return v;}
void main(){
 vec2 uv=gl_FragCoord.xy/r;vec2 q=(gl_FragCoord.xy-.5*r)/r.y;
 q+= (m-.5)*.12;
 float s=t*.045;
 vec2 w=vec2(fbm(q*1.6+vec2(s,-s)),fbm(q*1.6+vec2(-s*.8,s*1.2)+5.2));
 float f=fbm(q*1.2+w*2.4+vec2(s*.6,0.));
 float fold=smoothstep(.35,.95,f);
 float sheen=pow(smoothstep(.55,1.,fbm(q*2.2+w*3.+s)),3.);
 vec3 night=vec3(.012,.018,.035),navy=vec3(.06,.13,.24),cobalt=vec3(.08,.35,.79),ice=vec3(.91,.94,.96),tang=vec3(1.,.41,.24);
 vec3 c=mix(night,navy,smoothstep(.2,.8,f));
 c=mix(c,cobalt,pow(fold,1.7)*.8);
 c+=ice*sheen*.42;
 float glow=exp(-3.*length(vec2(q.x*.7,q.y+.15)));
 c+=cobalt*glow*.2;
 c+=tang*pow(smoothstep(.78,1.,f),4.)*.18*(1.-uv.y);
 c*=1.-.4*length(uv-vec2(.5,.45));
 gl_FragColor=vec4(c,1.);
}`;

export function SilkShader({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", {
      antialias: false,
      premultipliedAlpha: false,
    });
    if (!gl) return; // the CSS gradient behind it stays visible

    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );
    const loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const uR = gl.getUniformLocation(prog, "r");
    const uT = gl.getUniformLocation(prog, "t");
    const uM = gl.getUniformLocation(prog, "m");

    const still =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Render at reduced resolution: the silk is soft, so this costs nothing visually.
    const scale = Math.min(window.devicePixelRatio || 1, 1.5) * 0.5;
    const resize = () => {
      const w = Math.max(1, Math.floor(canvas.clientWidth * scale));
      const h = Math.max(1, Math.floor(canvas.clientHeight * scale));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
      }
    };

    let mx = 0.5,
      my = 0.5,
      tx = 0.5,
      ty = 0.5;
    const onMove = (e: PointerEvent) => {
      tx = e.clientX / window.innerWidth;
      ty = 1 - e.clientY / window.innerHeight;
    };

    let frame = 0;
    let visible = true;
    const start = performance.now();
    const draw = (now: number) => {
      resize();
      mx += (tx - mx) * 0.04;
      my += (ty - my) * 0.04;
      gl.uniform2f(uR, canvas.width, canvas.height);
      gl.uniform1f(uT, still ? 12 : (now - start) / 1000 + 12);
      gl.uniform2f(uM, mx, my);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (!still && visible) frame = requestAnimationFrame(draw);
    };

    // Pause when scrolled away or the tab is hidden.
    const io = new IntersectionObserver(([entry]) => {
      const was = visible;
      visible = entry.isIntersecting && !document.hidden;
      if (visible && !was && !still) frame = requestAnimationFrame(draw);
    });
    io.observe(canvas);
    window.addEventListener("pointermove", onMove);
    frame = requestAnimationFrame(draw);
    canvas.dataset.ready = "1";

    return () => {
      cancelAnimationFrame(frame);
      io.disconnect();
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  return (
    <canvas ref={ref} aria-hidden className={`silk-canvas ${className}`} />
  );
}
