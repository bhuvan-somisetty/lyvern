"use client";

import { useEffect, useRef } from "react";

// The hero's 3D centrepiece: a faceted glass crystal with a glowing tangerine core (the reviewer),
// two cobalt chrome rings, pull-request cards orbiting it (one flagged), and a slow star field.
// three.js is loaded only in the browser, after first paint. The scene leans toward the pointer,
// turns with scroll, pauses off screen, and renders one still frame for reduced motion.
export function Core3D({ className = "" }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    let disposed = false;
    let cleanup = () => {};

    (async () => {
      const THREE = await import("three");
      const { RoomEnvironment } = await import(
        "three/examples/jsm/environments/RoomEnvironment.js"
      );
      if (disposed) return;

      let renderer: InstanceType<typeof THREE.WebGLRenderer>;
      try {
        renderer = new THREE.WebGLRenderer({
          antialias: true,
          alpha: true,
          powerPreference: "high-performance",
        });
      } catch {
        return; // no WebGL: the CSS glow behind stays
      }
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.05;
      renderer.setClearColor(0x000000, 0);
      node.appendChild(renderer.domElement);
      renderer.domElement.setAttribute("aria-hidden", "true");

      const scene = new THREE.Scene();
      const pmrem = new THREE.PMREMGenerator(renderer);
      const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
      scene.environment = envTex;
      scene.environmentIntensity = 0.7;

      const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
      camera.position.set(0, 0, 9);

      const COBALT = new THREE.Color("#1558c9");
      const ICE = new THREE.Color("#e9f0f5");
      const TANG = new THREE.Color("#ff693d");

      const rig = new THREE.Group();
      scene.add(rig);

      // glass crystal
      const crystal = new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.45, 1),
        new THREE.MeshPhysicalMaterial({
          color: new THREE.Color("#bcd2ff"),
          metalness: 0,
          roughness: 0,
          transmission: 1,
          thickness: 1.6,
          ior: 1.9,
          dispersion: 4,
          iridescence: 0.8,
          iridescenceIOR: 1.25,
          clearcoat: 1,
          clearcoatRoughness: 0,
          attenuationColor: new THREE.Color("#1558c9"),
          attenuationDistance: 1.1,
          specularIntensity: 1,
          envMapIntensity: 1.1,
          flatShading: true,
        }),
      );
      rig.add(crystal);

      // facet edges catch the light
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(crystal.geometry),
        new THREE.LineBasicMaterial({
          color: ICE,
          transparent: true,
          opacity: 0.16,
        }),
      );
      crystal.add(edges);

      // the glowing core inside
      const core = new THREE.Mesh(
        new THREE.SphereGeometry(0.3, 48, 48),
        new THREE.MeshBasicMaterial({ color: TANG }),
      );
      rig.add(core);
      const halo = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: glowTexture(THREE, "255,105,61"),
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
        }),
      );
      halo.scale.setScalar(3.4);
      rig.add(halo);
      const coreLight = new THREE.PointLight(TANG, 18, 8, 2);
      rig.add(coreLight);

      // chrome rings
      const chrome = new THREE.MeshStandardMaterial({
        color: COBALT,
        metalness: 1,
        roughness: 0.18,
        envMapIntensity: 1.6,
      });
      const ringA = new THREE.Mesh(
        new THREE.TorusGeometry(2.35, 0.022, 24, 220),
        chrome,
      );
      ringA.rotation.set(1.2, 0.2, 0);
      const ringB = new THREE.Mesh(
        new THREE.TorusGeometry(2.8, 0.012, 16, 220),
        new THREE.MeshStandardMaterial({
          color: ICE,
          metalness: 1,
          roughness: 0.25,
        }),
      );
      ringB.rotation.set(1.75, -0.45, 0.3);
      rig.add(ringA, ringB);

      // pull-request cards orbiting on the inner ring
      const cards: InstanceType<typeof THREE.Mesh>[] = [];
      const cardGeo = new THREE.BoxGeometry(0.62, 0.4, 0.035);
      for (let i = 0; i < 6; i++) {
        const flagged = i === 2;
        const card = new THREE.Mesh(
          cardGeo,
          new THREE.MeshPhysicalMaterial({
            color: flagged ? TANG : ICE,
            emissive: flagged ? TANG : COBALT,
            emissiveIntensity: flagged ? 0.55 : 0.08,
            metalness: 0.1,
            roughness: 0.2,
            clearcoat: 1,
            transparent: true,
            opacity: flagged ? 0.95 : 0.55,
          }),
        );
        card.userData.phase = (i / 6) * Math.PI * 2;
        cards.push(card);
        ringA.add(card);
      }

      // star field
      const N = 1400;
      const pos = new Float32Array(N * 3);
      const col = new Float32Array(N * 3);
      for (let i = 0; i < N; i++) {
        const r = 3.2 + Math.pow(Math.random(), 0.6) * 6;
        const a = Math.random() * Math.PI * 2;
        const y = (Math.random() - 0.5) * (1.2 + r * 0.25);
        pos.set([Math.cos(a) * r, y, Math.sin(a) * r], i * 3);
        const c = Math.random() < 0.06 ? TANG : Math.random() < 0.5 ? ICE : COBALT;
        col.set([c.r, c.g, c.b], i * 3);
      }
      const starGeo = new THREE.BufferGeometry();
      starGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      starGeo.setAttribute("color", new THREE.BufferAttribute(col, 3));
      const stars = new THREE.Points(
        starGeo,
        new THREE.PointsMaterial({
          size: 0.035,
          vertexColors: true,
          transparent: true,
          opacity: 0.85,
          depthWrite: false,
          blending: THREE.AdditiveBlending,
          map: glowTexture(THREE, "255,255,255"),
        }),
      );
      stars.rotation.x = 0.35;
      scene.add(stars);

      const key = new THREE.DirectionalLight(ICE, 1.4);
      key.position.set(3, 4, 5);
      const rim = new THREE.DirectionalLight(COBALT, 3);
      rim.position.set(-5, -2, -3);
      scene.add(key, rim, new THREE.AmbientLight(COBALT, 0.4));

      const still =
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      const resize = () => {
        const w = node.clientWidth || 1;
        const h = node.clientHeight || 1;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.position.z = w / h < 0.9 ? 10.5 : 9;
        camera.updateProjectionMatrix();
      };
      resize();
      const ro = new ResizeObserver(resize);
      ro.observe(node);

      let tx = 0,
        ty = 0,
        px = 0,
        py = 0;
      const onMove = (e: PointerEvent) => {
        tx = (e.clientX / window.innerWidth) * 2 - 1;
        ty = (e.clientY / window.innerHeight) * 2 - 1;
      };

      const clock = new THREE.Clock();
      let frame = 0;
      let visible = true;
      const render = () => {
        const t = still ? 4 : clock.getElapsedTime();
        px += (tx - px) * 0.05;
        py += (ty - py) * 0.05;
        const scroll = Math.min(window.scrollY / window.innerHeight, 1.5);

        rig.rotation.y = px * 0.45 + scroll * 0.9;
        rig.rotation.x = py * 0.3 + scroll * 0.25;
        rig.position.y = Math.sin(t * 0.8) * 0.12;
        crystal.rotation.y = t * 0.22;
        crystal.rotation.x = t * 0.13;
        const beat = 1 + Math.sin(t * 2.2) * 0.06;
        core.scale.setScalar(beat);
        halo.scale.setScalar(3.4 * beat);
        coreLight.intensity = 16 + Math.sin(t * 2.2) * 4;
        ringA.rotation.z = t * 0.18;
        ringB.rotation.z = -t * 0.11;
        cards.forEach((c) => {
          const a = c.userData.phase as number;
          c.position.set(Math.cos(a) * 2.35, Math.sin(a) * 2.35, 0);
          c.rotation.z = a + Math.PI / 2;
          c.rotation.x = Math.sin(t + a) * 0.3;
        });
        stars.rotation.y = t * 0.02;

        renderer.render(scene, camera);
        if (!still && visible) frame = requestAnimationFrame(render);
      };

      const io = new IntersectionObserver(([entry]) => {
        const was = visible;
        visible = entry.isIntersecting && !document.hidden;
        if (visible && !was && !still) frame = requestAnimationFrame(render);
      });
      io.observe(node);
      window.addEventListener("pointermove", onMove);
      frame = requestAnimationFrame(render);
      node.dataset.ready = "1";

      cleanup = () => {
        cancelAnimationFrame(frame);
        io.disconnect();
        ro.disconnect();
        window.removeEventListener("pointermove", onMove);
        scene.traverse((o) => {
          const m = o as InstanceType<typeof THREE.Mesh>;
          m.geometry?.dispose();
          const mat = m.material;
          if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
          else mat?.dispose();
        });
        envTex.dispose();
        pmrem.dispose();
        renderer.dispose();
        renderer.domElement.remove();
      };
    })();

    return () => {
      disposed = true;
      cleanup();
    };
  }, []);

  return <div ref={host} aria-hidden className={`core3d ${className}`} />;
}

// a soft round glow drawn once on a small canvas, used for the halo and the stars
function glowTexture(THREE: typeof import("three"), rgb: string) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, `rgba(${rgb},1)`);
  grad.addColorStop(0.25, `rgba(${rgb},0.45)`);
  grad.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
