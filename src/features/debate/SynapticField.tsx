import { Line, PerspectiveCamera, Sparkles } from "@react-three/drei";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  AdditiveBlending,
  CatmullRomCurve3,
  DoubleSide,
  Group,
  InstancedMesh,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  Object3D,
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
const AGENT_RADIUS = 3.38;
const AGENT_COLORS = [
  { core: "#9bf6ff", accent: "#67d6ff" },
  { core: "#f4c76b", accent: "#ffe0a3" },
  { core: "#c7b3ff", accent: "#a78bfa" },
  { core: "#6effc8", accent: "#34d399" },
  { core: "#ff9eb5", accent: "#fb7185" },
  { core: "#dff9fb", accent: "#9bf6ff" }
];

const agentPositions = Array.from({ length: AGENT_COUNT }, (_, index) => {
  const angle = (Math.PI * 2 * index) / AGENT_COUNT - Math.PI / 2;
  return new Vector3(
    Math.cos(angle) * AGENT_RADIUS,
    Math.sin(angle) * AGENT_RADIUS * 0.62,
    Math.sin(angle * 1.35) * 0.42
  );
});

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
      <color attach="background" args={["#02070d"]} />
      <fog attach="fog" args={["#02070d", 7.8, 16.2]} />
      <group ref={group}>
        <ambientLight intensity={0.12} />
        <pointLight position={[0, 2.8, 2.8]} intensity={11} color="#9bf6ff" distance={8} />
        <pointLight position={[2.8, -1.6, 2.2]} intensity={3.4} color="#f4c76b" distance={7} />
        <Sparkles count={420} scale={[8.8, 5.2, 3.8]} size={1.18} speed={0.1} opacity={0.36} color="#9bf6ff" />
        <Sparkles count={148} scale={[8.4, 4.1, 3.2]} size={1.5} speed={0.075} opacity={0.32} color="#f4c76b" />
        <Sparkles count={96} scale={[7.8, 4.2, 3]} size={1.0} speed={0.06} opacity={0.2} color="#c7b3ff" />
      </group>
    </>
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
        <octahedronGeometry args={[0.34, 1]} />
        <meshBasicMaterial color={accent} wireframe transparent opacity={active ? 0.54 : 0.34} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.055, 24, 24]} />
        <meshBasicMaterial color="#f5feff" transparent opacity={0.96} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.58, 64, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.085} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.96, 64, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.032} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      {resonances.map((points, ringIndex) => (
        <Line key={`r-${ringIndex}`} points={points} color={ringIndex % 3 === 0 ? accent : color} transparent opacity={active ? 0.34 : 0.18} lineWidth={ringIndex % 4 === 0 ? 1.35 : 0.72} />
      ))}
      {dendrites.map((points, dendriteIndex) => (
        <Line key={`d-${dendriteIndex}`} points={points} color={dendriteIndex % 4 === 0 ? accent : color} transparent opacity={active ? 0.24 : 0.1} lineWidth={0.66} />
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
          <octahedronGeometry args={[0.48, 2]} />
          <meshBasicMaterial color={color} transparent opacity={0.34} blending={AdditiveBlending} side={DoubleSide} depthWrite={false} />
        </mesh>
        <mesh scale={1.42}>
          <octahedronGeometry args={[0.48, 1]} />
          <meshBasicMaterial color="#dff9fb" wireframe transparent opacity={0.42} blending={AdditiveBlending} depthWrite={false} />
        </mesh>
        <mesh scale={1.86}>
          <octahedronGeometry args={[0.48, 1]} />
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

  return (
    <group>
      {filaments.map((curve, index) => (
        <Line key={`f-${index}`} points={curve.getPoints(92)} color={index % 4 === 0 ? "#f4c76b" : "#1cb9ca"} transparent opacity={index % 4 === 0 ? 0.052 : 0.044} lineWidth={0.5} />
      ))}
      {nodeWeb.map((curve, index) => (
        <Line key={`w-${index}`} points={curve.getPoints(132)} color={index % 2 === 0 ? "#9bf6ff" : "#f4c76b"} transparent opacity={0.12} lineWidth={0.64} />
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
        <BackgroundFilaments />
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
        <EvidenceSparks claims={claims} />
        <MemoryCrystal selectedClaim={selectedClaim} />
      </group>
    </Canvas>
  );
}
