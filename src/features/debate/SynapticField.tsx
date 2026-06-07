import { Line, PerspectiveCamera, Sparkles } from "@react-three/drei";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  AdditiveBlending,
  BufferGeometry,
  CatmullRomCurve3,
  Color,
  DoubleSide,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  Object3D,
  ShaderMaterial,
  SphereGeometry,
  TubeGeometry,
  Vector3
} from "three";
import type { DebateClaim } from "../../domain/opencanal";

type SynapticFieldProps = {
  claims: DebateClaim[];
  selectedClaimId: string;
  onSelectClaim: (claimId: string) => void;
};

type SignalKind = "claim" | "counter" | "evidence" | "review";

type SignalSpec = {
  id: string;
  claimId: string;
  kind: SignalKind;
  color: string;
  phase: number;
  speed: number;
  points: Vector3[];
  sourceAgent: number;
  targetAgent: number;
  intensity: number;
};

const sharedMemory = new Vector3(0, 0, 0.2);
const AGENT_COUNT = 6;
const AGENT_COLORS = [
  { core: "#9bf6ff", accent: "#67d6ff" },
  { core: "#dff9fb", accent: "#9bf6ff" },
  { core: "#f4c76b", accent: "#ffe0a3" },
  { core: "#9bf6ff", accent: "#67d6ff" },
  { core: "#dff9fb", accent: "#f5feff" },
  { core: "#dff9fb", accent: "#9bf6ff" }
];

const agentPositions = [
  new Vector3(-3.62, 1.54, -0.16),
  new Vector3(3.55, 1.5, 0.08),
  new Vector3(2.74, -1.64, 0.18),
  new Vector3(-3.18, -1.58, 0.04),
  new Vector3(0, -2.22, 0.18),
  new Vector3(0.14, 2.02, -0.08)
];

const nebulaVertexShader = `
  varying vec2 vUv;

  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const nebulaFragmentShader = `
  uniform float uTime;
  varying vec2 vUv;

  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i + vec2(0.0, 0.0)), hash(i + vec2(1.0, 0.0)), u.x),
      mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
      u.y
    );
  }

  float fbm(vec2 p) {
    float value = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 5; i++) {
      value += noise(p) * amp;
      p *= 2.03;
      amp *= 0.5;
    }
    return value;
  }

  void main() {
    vec2 uv = vUv - 0.5;
    float radial = 1.0 - smoothstep(0.12, 0.78, length(uv));
    float filament = fbm(vec2(vUv.x * 3.2 + uTime * 0.018, vUv.y * 7.8 - uTime * 0.012));
    float deep = fbm(vec2(vUv.x * 9.0 - uTime * 0.01, vUv.y * 4.2 + uTime * 0.016));
    float strata = smoothstep(0.54, 0.86, filament) * 0.22 + smoothstep(0.62, 0.92, deep) * 0.11;
    vec3 cyan = vec3(0.23, 0.88, 1.0);
    vec3 gold = vec3(1.0, 0.72, 0.32);
    vec3 color = mix(cyan, gold, smoothstep(0.62, 0.92, deep));
    float alpha = (strata * 0.32 + radial * 0.055) * smoothstep(0.92, 0.18, length(uv));
    gl_FragColor = vec4(color, alpha);
  }
`;

const signalParticleVertexShader = `
  uniform float uTime;
  attribute vec3 aColor;
  attribute float aSeed;
  attribute float aProgress;
  attribute float aKind;
  varying vec3 vColor;
  varying float vPulse;

  void main() {
    vColor = aColor;
    float laneSpeed = mix(0.18, 0.34, fract(aSeed * 7.13));
    float packet = fract(aProgress - uTime * laneSpeed + aSeed);
    float head = smoothstep(0.0, 0.08, packet) * (1.0 - smoothstep(0.08, 0.2, packet));
    float shimmer = 0.42 + 0.58 * sin(uTime * (2.0 + aSeed * 2.0) + aProgress * 24.0);
    vPulse = max(head, shimmer * 0.24 + aKind * 0.04);

    vec3 displaced = position;
    displaced.z += sin(uTime * 0.45 + aSeed * 12.0 + aProgress * 8.0) * 0.035;
    displaced.xy += vec2(
      sin(uTime * 0.28 + aSeed * 19.0),
      cos(uTime * 0.23 + aSeed * 17.0)
    ) * 0.012;

    vec4 mvPosition = modelViewMatrix * vec4(displaced, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    gl_PointSize = (2.5 + head * 7.5 + aKind * 1.2) * (8.0 / -mvPosition.z);
  }
`;

const signalParticleFragmentShader = `
  varying vec3 vColor;
  varying float vPulse;

  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    float core = smoothstep(0.5, 0.0, d);
    float halo = smoothstep(0.5, 0.08, d);
    float alpha = (core * 0.76 + halo * 0.24) * clamp(vPulse, 0.0, 1.0);
    gl_FragColor = vec4(vColor, alpha);
  }
`;

const glowVertexShader = `
  varying vec2 vUv;

  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const glowFragmentShader = `
  uniform vec3 uColor;
  uniform float uTime;
  uniform float uPulse;
  varying vec2 vUv;

  void main() {
    vec2 uv = vUv - 0.5;
    float d = length(uv);
    float core = exp(-d * d * 18.0);
    float halo = exp(-d * d * 4.2);
    float ripple = 0.82 + 0.18 * sin(uTime * 1.6 + d * 22.0 + uPulse);
    float mask = 1.0 - smoothstep(0.34, 0.5, d);
    float alpha = (core * 0.18 + halo * 0.32) * ripple * mask;
    gl_FragColor = vec4(uColor, alpha);
  }
`;

function claimColor(claim: DebateClaim, kind: SignalKind) {
  if (kind === "evidence") return "#f4c76b";
  if (kind === "counter") return "#dff9fb";
  if (claim.review_status === "blocked" || claim.review_status === "out_of_mandate") return "#ff7a90";
  if (claim.review_status === "disputed" || claim.review_status === "weak") return "#67d6ff";
  if (claim.review_status === "needs_more_evidence") return "#f4c76b";
  return "#9bf6ff";
}

function pseudo(index: number) {
  return Math.abs(Math.sin(index * 12.9898) * 43758.5453) % 1;
}

function makeBraidedSignals(claims: DebateClaim[]) {
  const kinds: SignalKind[] = ["claim", "counter", "evidence", "review"];
  const sourceClaims = claims.slice(0, 10);

  return sourceClaims.flatMap((claim, claimIndex) => {
    const sourceAgent = claimIndex % AGENT_COUNT;
    const sourcePosition = agentPositions[sourceAgent];

    return kinds.flatMap((kind, kindIndex) => {
      const strandCount = kind === "evidence" ? 4 : 3;
      return Array.from({ length: strandCount }, (_, strandIndex) => {
        const targetAgent = (sourceAgent + kindIndex + strandIndex + 1) % AGENT_COUNT;
        const targetPosition = agentPositions[targetAgent];
        const sourceToCenter = sharedMemory.clone().sub(sourcePosition);
        const targetToCenter = sharedMemory.clone().sub(targetPosition);
        const sourceNormal = new Vector3(-sourceToCenter.y, sourceToCenter.x, 0).normalize();
        const targetNormal = new Vector3(targetToCenter.y, -targetToCenter.x, 0).normalize();
        const wave = Math.sin((claimIndex + kindIndex * 0.8 + strandIndex * 0.53) * 1.7);
        const braid = wave * (0.16 + strandIndex * 0.08);
        const zLane = 0.14 + kindIndex * 0.055 + strandIndex * 0.04;
        const memoryOffset = new Vector3(
          Math.sin(claimIndex * 0.9 + strandIndex) * 0.2,
          Math.cos(claimIndex * 0.74 + kindIndex) * 0.14,
          zLane + 0.12
        );

        const points = [
          sourcePosition.clone().lerp(sharedMemory, 0.12),
          sourcePosition.clone().lerp(sharedMemory, 0.36).addScaledVector(sourceNormal, braid).add(new Vector3(0, 0, zLane)),
          sharedMemory.clone().add(memoryOffset),
          targetPosition.clone().lerp(sharedMemory, 0.4).addScaledVector(targetNormal, -braid * 0.82).add(new Vector3(0, 0, zLane * 0.75)),
          targetPosition.clone().lerp(sharedMemory, 0.14)
        ];

        return {
          id: `${claim.claim_id}-${kind}-${strandIndex}`,
          claimId: claim.claim_id,
          kind,
          color: claimColor(claim, kind),
          phase: claimIndex * 0.17 + kindIndex * 0.22 + strandIndex * 0.11,
          speed: kind === "evidence" ? 0.1 : kind === "counter" ? 0.14 : 0.18 + strandIndex * 0.012,
          points,
          sourceAgent,
          targetAgent,
          intensity: kind === "evidence" ? 0.9 : kind === "review" ? 0.54 : 0.74
        } satisfies SignalSpec;
      });
    });
  });
}

function ellipsePoints(center: Vector3, radiusX: number, radiusY: number, rotation: number, z = 0, count = 156) {
  return Array.from({ length: count + 1 }, (_, index) => {
    const t = (Math.PI * 2 * index) / count;
    const x = Math.cos(t) * radiusX;
    const y = Math.sin(t) * radiusY;
    const xr = x * Math.cos(rotation) - y * Math.sin(rotation);
    const yr = x * Math.sin(rotation) + y * Math.cos(rotation);
    return center.clone().add(new Vector3(xr, yr, z + Math.sin(t * 2 + rotation) * 0.035));
  });
}

function wavePoints(start: Vector3, end: Vector3, amplitude: number, phase: number, count = 168) {
  const direction = end.clone().sub(start);
  const normal = new Vector3(-direction.y, direction.x, 0).normalize();
  return Array.from({ length: count }, (_, index) => {
    const t = index / (count - 1);
    const envelope = Math.sin(Math.PI * t);
    const wave = Math.sin(t * Math.PI * 10 + phase) * amplitude * envelope;
    const lift = Math.sin(t * Math.PI * 2 + phase * 0.4) * 0.18;
    return start.clone().lerp(end, t).addScaledVector(normal, wave).add(new Vector3(0, lift * 0.18, 0.38 + lift));
  });
}

function SceneRig() {
  const group = useRef<Group>(null);

  useFrame(({ pointer, clock }) => {
    if (!group.current) return;
    group.current.rotation.y = MathUtils.lerp(group.current.rotation.y, pointer.x * 0.06, 0.025);
    group.current.rotation.x = MathUtils.lerp(group.current.rotation.x, -pointer.y * 0.035, 0.025);
    group.current.position.y = Math.sin(clock.elapsedTime * 0.22) * 0.025;
  });

  return (
    <>
      <color attach="background" args={["#031018"]} />
      <fog attach="fog" args={["#031018", 6.6, 15.4]} />
      <group ref={group}>
        <ambientLight intensity={0.12} />
        <pointLight position={[0, 2.8, 2.8]} intensity={11} color="#9bf6ff" distance={8} />
        <pointLight position={[2.8, -1.6, 2.2]} intensity={3.4} color="#f4c76b" distance={7} />
        <Sparkles count={520} scale={[9.2, 5.6, 4]} size={1.08} speed={0.1} opacity={0.34} color="#9bf6ff" />
        <Sparkles count={190} scale={[8.6, 4.5, 3.4]} size={1.38} speed={0.075} opacity={0.3} color="#f4c76b" />
        <Sparkles count={130} scale={[8, 4.4, 3.2]} size={0.94} speed={0.06} opacity={0.18} color="#c7b3ff" />
      </group>
    </>
  );
}

function NebulaVeil() {
  const material = useRef<ShaderMaterial>(null);

  useFrame(({ clock }) => {
    if (!material.current) return;
    material.current.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <mesh position={[0, 0.04, -1.35]} scale={[1.08, 1.04, 1]} renderOrder={-20}>
      <planeGeometry args={[11.6, 6.8, 1, 1]} />
      <shaderMaterial
        ref={material}
        vertexShader={nebulaVertexShader}
        fragmentShader={nebulaFragmentShader}
        uniforms={{ uTime: { value: 0 } }}
        transparent
        depthWrite={false}
        depthTest={false}
        blending={AdditiveBlending}
      />
    </mesh>
  );
}

function GlowDisc({
  position,
  color,
  scale,
  pulse = 0
}: {
  position: Vector3;
  color: string;
  scale: number;
  pulse?: number;
}) {
  const material = useRef<ShaderMaterial>(null);
  const colorValue = useMemo(() => new Color(color), [color]);

  useFrame(({ clock }) => {
    if (!material.current) return;
    material.current.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <mesh position={[position.x, position.y, position.z - 0.08]} scale={[scale, scale, scale]} renderOrder={-2}>
      <planeGeometry args={[1, 1, 1, 1]} />
      <shaderMaterial
        ref={material}
        vertexShader={glowVertexShader}
        fragmentShader={glowFragmentShader}
        uniforms={{ uTime: { value: 0 }, uColor: { value: colorValue }, uPulse: { value: pulse } }}
        transparent
        depthWrite={false}
        depthTest={false}
        blending={AdditiveBlending}
      />
    </mesh>
  );
}

function AgentCore({
  index,
  position,
  active,
  onSelect
}: {
  index: number;
  position: Vector3;
  active: boolean;
  onSelect: (event: ThreeEvent<PointerEvent>) => void;
}) {
  const group = useRef<Group>(null);
  const core = useRef<Mesh>(null);
  const color = AGENT_COLORS[index % AGENT_COLORS.length].core;
  const accent = AGENT_COLORS[index % AGENT_COLORS.length].accent;

  const resonances = useMemo(() => {
    const ringCount = 12 + (index % 3) * 4;
    return Array.from({ length: ringCount }, (_, ringIndex) => {
      const radius = 0.64 + ringIndex * 0.046;
      const squash = 0.82 + (ringIndex % 4) * 0.04;
      const rotation = ringIndex * 0.43 + index * 0.55;
      const z = Math.sin(ringIndex * 0.72 + index) * 0.24;
      return ellipsePoints(new Vector3(0, 0, 0), radius, radius * squash, rotation, z, 160);
    });
  }, [index]);

  const dendrites = useMemo(() => {
    const dendriteCount = 22 + (index % 4) * 4;
    return Array.from({ length: dendriteCount }, (_, dendriteIndex) => {
      const angle = (Math.PI * 2 * dendriteIndex) / dendriteCount;
      const reach = 0.92 + (dendriteIndex % 4) * 0.14;
      const start = new Vector3(Math.cos(angle) * 0.46, Math.sin(angle) * 0.46, Math.sin(angle * 2) * 0.08);
      const mid = new Vector3(Math.cos(angle) * 0.78, Math.sin(angle) * 0.7, Math.cos(angle * 1.6) * 0.2);
      const end = new Vector3(Math.cos(angle) * reach, Math.sin(angle) * reach * 0.7, Math.sin(angle * 1.3) * 0.28);
      return [start, mid, end];
    });
  }, [index]);

  useFrame(({ clock }) => {
    if (!group.current || !core.current) return;
    const pulse = 1 + Math.sin(clock.elapsedTime * 1.18 + index * 0.7) * 0.026;
    group.current.scale.setScalar(active ? pulse * 1.05 : pulse);
    group.current.rotation.z += index % 2 === 0 ? 0.0015 : -0.002;
    group.current.rotation.y += index % 2 === 0 ? 0.001 : -0.0007;
    (core.current.material as MeshBasicMaterial).opacity = active ? 0.98 : 0.74 + Math.sin(clock.elapsedTime * 1.6 + index) * 0.08;
  });

  return (
    <group ref={group} position={position} onPointerDown={onSelect}>
      <mesh ref={core}>
        <sphereGeometry args={[0.18, 48, 48]} />
        <meshBasicMaterial color={color} transparent opacity={0.58} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh rotation={[index * 0.2, index * 0.32, index * 0.12]}>
        {index % 3 === 1 ? <tetrahedronGeometry args={[0.38, 1]} /> : index % 3 === 2 ? <icosahedronGeometry args={[0.34, 1]} /> : <octahedronGeometry args={[0.34, 1]} />}
        <meshBasicMaterial color={accent} wireframe transparent opacity={active ? 0.54 : 0.34} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.055, 24, 24]} />
        <meshBasicMaterial color="#f5feff" transparent opacity={0.96} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.58, 64, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.06} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.96, 64, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.022} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      {resonances.map((points, ringIndex) => (
        <Line key={`r-${ringIndex}`} points={points} color={ringIndex % 3 === 0 ? accent : color} transparent opacity={active ? 0.24 : 0.11} lineWidth={ringIndex % 4 === 0 ? 0.92 : 0.54} />
      ))}
      {dendrites.map((points, dendriteIndex) => (
        <Line key={`d-${dendriteIndex}`} points={points} color={dendriteIndex % 4 === 0 ? accent : color} transparent opacity={active ? 0.28 : 0.12} lineWidth={0.62} />
      ))}
    </group>
  );
}

function SignalFlare({
  position,
  color = "#dff9fb",
  scale = 1,
  phase = 0
}: {
  position: Vector3;
  color?: string;
  scale?: number;
  phase?: number;
}) {
  const group = useRef<Group>(null);
  const core = useRef<Mesh>(null);
  const rings = useMemo(
    () => [
      ellipsePoints(new Vector3(0, 0, 0), 0.22 * scale, 0.12 * scale, phase, 0.01, 96),
      ellipsePoints(new Vector3(0, 0, 0), 0.31 * scale, 0.09 * scale, phase + Math.PI / 2.7, 0.04, 96),
      ellipsePoints(new Vector3(0, 0, 0), 0.4 * scale, 0.14 * scale, phase + Math.PI / 1.7, -0.02, 96)
    ],
    [phase, scale]
  );

  useFrame(({ clock }) => {
    if (!group.current || !core.current) return;
    group.current.rotation.z = clock.elapsedTime * 0.16 + phase;
    group.current.rotation.y = Math.sin(clock.elapsedTime * 0.22 + phase) * 0.3;
    (core.current.material as MeshBasicMaterial).opacity = 0.66 + Math.sin(clock.elapsedTime * 1.9 + phase) * 0.18;
  });

  return (
    <group ref={group} position={position}>
      <mesh ref={core}>
        <sphereGeometry args={[0.045 * scale, 18, 18]} />
        <meshBasicMaterial color="#f7ffff" transparent opacity={0.76} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.16 * scale, 32, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.09} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      {rings.map((points, index) => (
        <Line key={index} points={points} color={index === 1 ? "#f4c76b" : color} transparent opacity={0.28 - index * 0.045} lineWidth={0.72} />
      ))}
    </group>
  );
}

function BraidedSignal({ spec, selected }: { spec: SignalSpec; selected: boolean }) {
  const curve = useMemo(() => new CatmullRomCurve3(spec.points), [spec.points]);
  const points = useMemo(() => curve.getPoints(164), [curve]);
  const tube = useMemo(() => new TubeGeometry(curve, 180, selected ? 0.012 : 0.004, 8, false), [curve, selected]);
  const packetRefs = useRef<Mesh[]>([]);

  useEffect(() => {
    return () => {
      tube.dispose();
    };
  }, [tube]);

  useFrame(({ clock }) => {
    packetRefs.current.forEach((packet, packetIndex) => {
      const t = (clock.elapsedTime * spec.speed + spec.phase + packetIndex * 0.22) % 1;
      const p = curve.getPoint(t);
      packet.position.copy(p);
      packet.scale.setScalar((selected ? 1.24 : 0.84) * (packetIndex === 0 ? 1 : 0.74));
    });
  });

  return (
    <group>
      <mesh geometry={tube}>
        <meshBasicMaterial color={spec.color} transparent opacity={(selected ? 0.2 : 0.072) * spec.intensity} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <Line points={points} color={spec.color} transparent opacity={(selected ? 0.58 : 0.22) * spec.intensity} lineWidth={selected ? 1.45 : 0.72} />
      {[0, 1, 2].map((index) => (
        <mesh
          key={index}
          ref={(node) => {
            if (node) packetRefs.current[index] = node;
          }}
        >
          <sphereGeometry args={[index === 0 ? 0.032 : 0.021, 18, 18]} />
          <meshBasicMaterial color={index === 2 ? "#dff9fb" : spec.color} transparent opacity={0.82 - index * 0.14} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}

function SignalParticleField({ signals }: { signals: SignalSpec[] }) {
  const material = useRef<ShaderMaterial>(null);
  const geometry = useMemo(() => {
    const positions: number[] = [];
    const colors: number[] = [];
    const seeds: number[] = [];
    const progress: number[] = [];
    const kinds: number[] = [];

    signals.forEach((signal, signalIndex) => {
      const color = new Color(signal.color);
      const curve = new CatmullRomCurve3(signal.points);
      const sampleCount = signal.kind === "evidence" ? 76 : 58;

      Array.from({ length: sampleCount }).forEach((_, pointIndex) => {
        const t = pointIndex / (sampleCount - 1);
        const p = curve.getPoint(t);
        const jitter = pseudo(signalIndex * 101 + pointIndex * 17) * 0.028;
        positions.push(p.x + Math.sin(pointIndex) * jitter, p.y + Math.cos(pointIndex * 1.7) * jitter, p.z + Math.sin(pointIndex * 0.7) * jitter);
        colors.push(color.r, color.g, color.b);
        seeds.push(pseudo(signalIndex * 37 + pointIndex * 13));
        progress.push(t);
        kinds.push(signal.kind === "evidence" ? 1.0 : signal.kind === "counter" ? 0.7 : signal.kind === "review" ? 0.45 : 0.2);
      });
    });

    const backgroundCount = 360;
    Array.from({ length: backgroundCount }).forEach((_, index) => {
      const angle = pseudo(index + 5) * Math.PI * 2;
      const radius = 0.9 + pseudo(index + 11) * 4.2;
      const yScale = 0.56 + pseudo(index + 17) * 0.22;
      const color = new Color(index % 5 === 0 ? "#f4c76b" : "#67d6ff");
      positions.push(Math.cos(angle) * radius, Math.sin(angle) * radius * yScale, -0.38 + pseudo(index + 23) * 1.1);
      colors.push(color.r, color.g, color.b);
      seeds.push(pseudo(index + 29));
      progress.push(pseudo(index + 31));
      kinds.push(0.06);
    });

    const buffer = new BufferGeometry();
    buffer.setAttribute("position", new Float32BufferAttribute(positions, 3));
    buffer.setAttribute("aColor", new Float32BufferAttribute(colors, 3));
    buffer.setAttribute("aSeed", new Float32BufferAttribute(seeds, 1));
    buffer.setAttribute("aProgress", new Float32BufferAttribute(progress, 1));
    buffer.setAttribute("aKind", new Float32BufferAttribute(kinds, 1));
    return buffer;
  }, [signals]);

  useEffect(() => {
    return () => {
      geometry.dispose();
    };
  }, [geometry]);

  useFrame(({ clock }) => {
    if (!material.current) return;
    material.current.uniforms.uTime.value = clock.elapsedTime;
  });

  return (
    <points geometry={geometry} renderOrder={12}>
      <shaderMaterial
        ref={material}
        vertexShader={signalParticleVertexShader}
        fragmentShader={signalParticleFragmentShader}
        uniforms={{ uTime: { value: 0 } }}
        transparent
        depthWrite={false}
        blending={AdditiveBlending}
      />
    </points>
  );
}

function MemoryCrystal({ selectedClaim }: { selectedClaim?: DebateClaim }) {
  const group = useRef<Group>(null);
  const inner = useRef<Group>(null);
  const color = selectedClaim ? claimColor(selectedClaim, "claim") : "#9bf6ff";
  const petals = useMemo(() => {
    return Array.from({ length: 16 }, (_, index) => ellipsePoints(new Vector3(0, 0, 0), 0.92, 0.26, (Math.PI * index) / 16, Math.sin(index) * 0.09, 144));
  }, []);

  useFrame(({ clock }) => {
    if (!group.current) return;
    group.current.rotation.y = clock.elapsedTime * 0.17;
    group.current.rotation.z = Math.sin(clock.elapsedTime * 0.2) * 0.08;
    group.current.scale.setScalar(1 + Math.sin(clock.elapsedTime * 1.5) * 0.035);
    if (inner.current) {
      inner.current.rotation.y = -clock.elapsedTime * 0.32;
      inner.current.rotation.x = Math.sin(clock.elapsedTime * 0.42) * 0.18;
    }
  });

  return (
    <group ref={group} position={sharedMemory}>
      <group ref={inner}>
        <mesh>
          <icosahedronGeometry args={[0.5, 2]} />
          <meshBasicMaterial color={color} transparent opacity={0.22} blending={AdditiveBlending} side={DoubleSide} depthWrite={false} />
        </mesh>
        <mesh scale={1.42}>
          <icosahedronGeometry args={[0.5, 1]} />
          <meshBasicMaterial color="#dff9fb" wireframe transparent opacity={0.54} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
        <mesh scale={1.86}>
          <icosahedronGeometry args={[0.5, 1]} />
          <meshBasicMaterial color="#f4c76b" wireframe transparent opacity={0.11} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
      </group>
      <mesh>
        <sphereGeometry args={[1.05, 64, 64]} />
        <meshBasicMaterial color="#9bf6ff" transparent opacity={0.026} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[1.48, 64, 64]} />
        <meshBasicMaterial color="#67d6ff" transparent opacity={0.012} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      {petals.map((points, index) => (
        <Line key={index} points={points} color={index % 3 === 0 ? "#f4c76b" : "#9bf6ff"} transparent opacity={0.18} lineWidth={index % 4 === 0 ? 1 : 0.62} />
      ))}
    </group>
  );
}

function BackgroundFilaments() {
  const filaments = useMemo(() => {
    return Array.from({ length: 54 }, (_, index) => {
      const y = -2.5 + (index / 53) * 5 + Math.sin(index * 1.3) * 0.18;
      const z = -1 + Math.cos(index * 1.7) * 0.6;
      return new CatmullRomCurve3([
        new Vector3(-4.9, y * 0.44, z),
        new Vector3(-2.4, y * 0.58 + Math.sin(index) * 0.22, z + 0.34),
        new Vector3(0, y * 0.18, z + 0.62),
        new Vector3(2.4, -y * 0.2 + Math.cos(index) * 0.16, z + 0.34),
        new Vector3(4.9, -y * 0.38, z)
      ]);
    });
  }, []);

  const nodeWeb = useMemo(() => {
    return agentPositions.map((position, index) => {
      const next = agentPositions[(index + 1) % AGENT_COUNT];
      const far = agentPositions[(index + 2) % AGENT_COUNT];
      return [
        new CatmullRomCurve3([position.clone().lerp(sharedMemory, 0.08), position.clone().lerp(sharedMemory, 0.52).add(new Vector3(0, 0, 0.18)), next.clone().lerp(sharedMemory, 0.08)]),
        new CatmullRomCurve3([position.clone().lerp(sharedMemory, 0.15), sharedMemory.clone().add(new Vector3(0, 0, -0.16)), far.clone().lerp(sharedMemory, 0.15)])
      ];
    }).flat();
  }, []);

  const distantWeb = useMemo(() => {
    const points = [
      new Vector3(-4.45, 2.1, -0.65),
      new Vector3(-2.35, 2.64, -0.3),
      new Vector3(0.16, 2.45, -0.38),
      new Vector3(2.3, 2.54, -0.2),
      new Vector3(4.28, 1.9, -0.62),
      new Vector3(-4.14, -2.18, -0.42),
      new Vector3(-1.8, -2.58, -0.34),
      new Vector3(1.84, -2.5, -0.34),
      new Vector3(4.1, -2.08, -0.42)
    ];

    return points.flatMap((point, index) => {
      const next = points[(index + 1) % points.length];
      const across = points[(index + 4) % points.length];
      return [
        new CatmullRomCurve3([point, point.clone().lerp(next, 0.5).add(new Vector3(0, Math.sin(index) * 0.34, 0.22)), next]),
        new CatmullRomCurve3([point.clone().lerp(sharedMemory, 0.18), sharedMemory.clone().add(new Vector3(Math.sin(index) * 0.5, Math.cos(index * 1.3) * 0.32, -0.18)), across.clone().lerp(sharedMemory, 0.18)])
      ];
    });
  }, []);

  return (
    <group>
      {filaments.map((curve, index) => (
        <Line key={`f-${index}`} points={curve.getPoints(92)} color={index % 4 === 0 ? "#f4c76b" : "#1cb9ca"} transparent opacity={index % 4 === 0 ? 0.052 : 0.044} lineWidth={0.5} />
      ))}
      {nodeWeb.map((curve, index) => (
        <Line key={`w-${index}`} points={curve.getPoints(132)} color={index % 2 === 0 ? "#9bf6ff" : "#f4c76b"} transparent opacity={0.12} lineWidth={0.64} />
      ))}
      {distantWeb.map((curve, index) => (
        <Line key={`dw-${index}`} points={curve.getPoints(96)} color={index % 3 === 0 ? "#f4c76b" : "#1cb9ca"} transparent opacity={0.052} lineWidth={0.42} />
      ))}
    </group>
  );
}

function SemanticWaveLayer() {
  const waves = useMemo(
    () => [
      { points: wavePoints(agentPositions[0].clone().lerp(sharedMemory, 0.08), agentPositions[1].clone().lerp(sharedMemory, 0.08), 0.08, 0.4), color: "#9bf6ff", opacity: 0.26 },
      { points: wavePoints(agentPositions[3].clone().lerp(sharedMemory, 0.05), agentPositions[4].clone().lerp(sharedMemory, 0.05), 0.1, 1.7), color: "#67d6ff", opacity: 0.18 },
      { points: wavePoints(agentPositions[1].clone().lerp(sharedMemory, 0.18), agentPositions[2].clone().lerp(sharedMemory, 0.08), 0.07, 2.6), color: "#f4c76b", opacity: 0.18 }
    ],
    []
  );

  return (
    <group>
      {waves.map((wave, index) => (
        <Line key={index} points={wave.points} color={wave.color} transparent opacity={wave.opacity} lineWidth={index === 0 ? 1.15 : 0.82} />
      ))}
    </group>
  );
}

function EvidenceSparks({ claims }: { claims: DebateClaim[] }) {
  const group = useRef<Group>(null);
  const mesh = useRef<InstancedMesh>(null);
  const sparkMaterial = useMemo(() => new MeshBasicMaterial({ color: "#f4c76b", transparent: true, opacity: 0.86, blending: AdditiveBlending, depthWrite: false }), []);
  const sparkGeometry = useMemo(() => new SphereGeometry(0.014, 10, 10), []);
  const dummy = useMemo(() => new Object3D(), []);
  const sparks = useMemo(() => {
    const evidenceCount = Math.max(96, claims.reduce((count, claim) => count + claim.evidence.length, 0) * 14);
    return Array.from({ length: evidenceCount }, (_, index) => {
      const theta = Math.PI * 2 * pseudo(index + 1);
      const phi = Math.acos(2 * pseudo(index + 17) - 1);
      const radius = 0.72 + pseudo(index + 31) * 2.16;
      return {
        id: `spark-${index}`,
        x: Math.sin(phi) * Math.cos(theta) * radius,
        y: Math.sin(phi) * Math.sin(theta) * radius * 0.58,
        z: 0.2 + Math.cos(phi) * radius * 0.62
      };
    });
  }, [claims]);

  useFrame(({ clock }) => {
    if (!group.current) return;
    group.current.rotation.y = Math.sin(clock.elapsedTime * 0.14) * 0.09;
    group.current.rotation.z = clock.elapsedTime * 0.018;
  });

  useEffect(() => {
    if (!mesh.current) return;
    sparks.forEach((spark, index) => {
      dummy.position.set(spark.x, spark.y, spark.z);
      dummy.scale.setScalar(1 + pseudo(index + 41) * 0.9);
      dummy.updateMatrix();
      mesh.current?.setMatrixAt(index, dummy.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  }, [dummy, sparks]);

  return (
    <group ref={group}>
      <instancedMesh ref={mesh} args={[sparkGeometry, sparkMaterial, sparks.length]} />
    </group>
  );
}

export function SynapticField({ claims, selectedClaimId, onSelectClaim }: SynapticFieldProps) {
  const selectedClaim = claims.find((claim) => claim.claim_id === selectedClaimId);
  const signals = useMemo(() => makeBraidedSignals(claims), [claims]);
  const selectedSignals = signals.filter((signal) => signal.claimId === selectedClaimId);

  return (
    <Canvas className="synaptic-canvas" dpr={[1, 2]} gl={{ antialias: true, alpha: false }}>
      <PerspectiveCamera makeDefault position={[0, 0.36, 8.85]} fov={50} />
      <SceneRig />
      <group position={[0, -0.02, 0]}>
        <NebulaVeil />
        <BackgroundFilaments />
        <SemanticWaveLayer />
        <GlowDisc position={sharedMemory} color="#9bf6ff" scale={3.35} pulse={0.2} />
        {agentPositions.map((position, index) => (
          <GlowDisc key={`glow-${index}`} position={position} color={AGENT_COLORS[index % AGENT_COLORS.length].core} scale={1.72 + (index % 3) * 0.18} pulse={index * 0.66} />
        ))}
        <SignalFlare position={sharedMemory} color="#9bf6ff" scale={1.9} phase={0.2} />
        {agentPositions.map((position, index) => (
          <SignalFlare key={`flare-${index}`} position={position.clone().lerp(sharedMemory, 0.23)} color={AGENT_COLORS[index % AGENT_COLORS.length].accent} scale={0.65} phase={index * 0.7} />
        ))}
        {agentPositions.map((position, index) => {
          const active = selectedSignals.some((signal) => signal.sourceAgent === index || signal.targetAgent === index);
          return (
            <AgentCore
              key={index}
              index={index}
              position={position}
              active={selectedSignals.length === 0 || active}
              onSelect={(event) => {
                event.stopPropagation();
                const claim = claims[index % claims.length];
                if (claim) onSelectClaim(claim.claim_id);
              }}
            />
          );
        })}
        {signals.map((signal) => (
          <BraidedSignal key={signal.id} spec={signal} selected={signal.claimId === selectedClaimId} />
        ))}
        <SignalParticleField signals={signals} />
        <EvidenceSparks claims={claims} />
        <MemoryCrystal selectedClaim={selectedClaim} />
      </group>
    </Canvas>
  );
}
