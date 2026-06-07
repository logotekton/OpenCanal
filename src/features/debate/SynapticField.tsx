import { Line, PerspectiveCamera, Sparkles } from "@react-three/drei";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import {
  AdditiveBlending,
  CatmullRomCurve3,
  Color,
  DoubleSide,
  Group,
  MathUtils,
  Mesh,
  MeshBasicMaterial,
  OctahedronGeometry,
  SphereGeometry,
  TubeGeometry,
  TorusGeometry,
  Vector3
} from "three";
import { demoAgents } from "../../data/demoAgents";
import type { Agent, DebateClaim } from "../../domain/opencanal";

type SynapticFieldProps = {
  claims: DebateClaim[];
  selectedClaimId: string;
  onSelectClaim: (claimId: string) => void;
};

const agentPositions: Record<string, [number, number, number]> = {
  "agent-proponent": [-3.35, 0.66, 0.1],
  "agent-opponent": [3.35, 0.54, -0.16],
  "agent-evidence": [-2.35, -1.72, 0.3],
  "agent-governance": [2.48, -1.66, 0.18],
  "agent-moderator": [0, 1.88, -0.1]
};

const roleColor: Record<Agent["role"], string> = {
  proponent: "#9bf6ff",
  opponent: "#67d6ff",
  evidence: "#f4c76b",
  governance: "#71f2c7",
  moderator: "#dff9fb"
};

function claimColor(claim: DebateClaim) {
  if (claim.review_status === "blocked" || claim.review_status === "out_of_mandate") return "#ff7a90";
  if (claim.review_status === "disputed" || claim.review_status === "weak") return "#67d6ff";
  if (claim.review_status === "needs_more_evidence") return "#f4c76b";
  return "#9bf6ff";
}

function curveFor(agentId: string, index: number) {
  const start = new Vector3(...agentPositions[agentId]);
  const centerLift = index % 2 === 0 ? 0.32 : -0.24;
  return new CatmullRomCurve3([
    start,
    start.clone().multiplyScalar(0.52).add(new Vector3(0, centerLift, 0.35 + index * 0.025)),
    new Vector3(0, 0, 0)
  ]);
}

function SceneRig() {
  const group = useRef<Group>(null);

  useFrame(({ pointer, clock }) => {
    if (!group.current) return;
    group.current.rotation.y = MathUtils.lerp(group.current.rotation.y, pointer.x * 0.08, 0.03);
    group.current.rotation.x = MathUtils.lerp(group.current.rotation.x, -pointer.y * 0.045, 0.03);
    group.current.position.y = Math.sin(clock.elapsedTime * 0.24) * 0.04;
  });

  return (
    <group ref={group}>
      <AmbientAbyss />
    </group>
  );
}

function AmbientAbyss() {
  return (
    <>
      <color attach="background" args={["#02080e"]} />
      <fog attach="fog" args={["#02080e", 7.5, 15]} />
      <ambientLight intensity={0.18} />
      <pointLight position={[0, 4.2, 2.4]} intensity={12} color="#9bf6ff" distance={8} />
      <pointLight position={[-4, -2.5, 1.8]} intensity={7} color="#f4c76b" distance={7} />
      <Sparkles count={150} scale={[9, 5.6, 3.5]} size={1.8} speed={0.18} opacity={0.42} color="#9bf6ff" />
      <Sparkles count={34} scale={[7, 4.2, 2.8]} size={2.4} speed={0.08} opacity={0.28} color="#f4c76b" />
    </>
  );
}

function AgentNeuron({
  agent,
  active,
  onSelect
}: {
  agent: Agent;
  active: boolean;
  onSelect: (event: ThreeEvent<PointerEvent>) => void;
}) {
  const group = useRef<Group>(null);
  const core = useRef<Mesh<SphereGeometry, MeshBasicMaterial>>(null);
  const color = roleColor[agent.role];
  const position = agentPositions[agent.agent_id];

  useFrame(({ clock }) => {
    if (!group.current || !core.current) return;
    const pulse = 1 + Math.sin(clock.elapsedTime * 1.45 + position[0]) * 0.035;
    group.current.scale.setScalar(active ? pulse * 1.18 : pulse);
    group.current.rotation.z += active ? 0.006 : 0.0024;
    core.current.material.opacity = active ? 0.98 : 0.76 + Math.sin(clock.elapsedTime * 1.8) * 0.08;
  });

  const dendrites = useMemo(() => {
    const base = new Vector3(...position);
    return Array.from({ length: 5 }, (_, index) => {
      const angle = (Math.PI * 2 * index) / 5 + position[0] * 0.1;
      const end = base.clone().add(new Vector3(Math.cos(angle) * 0.58, Math.sin(angle) * 0.38, Math.sin(angle * 1.7) * 0.32));
      const mid = base.clone().lerp(end, 0.55).add(new Vector3(0, Math.sin(angle) * 0.12, 0.15));
      return [base, mid, end];
    });
  }, [position]);

  return (
    <group ref={group} position={position} onPointerDown={onSelect}>
      <mesh ref={core}>
        <sphereGeometry args={[0.22, 48, 48]} />
        <meshBasicMaterial color={color} transparent opacity={0.88} blending={AdditiveBlending} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.46, 48, 48]} />
        <meshBasicMaterial color={color} transparent opacity={active ? 0.2 : 0.1} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.72, 48, 48]} />
        <meshBasicMaterial color={color} transparent opacity={active ? 0.08 : 0.035} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.47, 0.006, 12, 96]} />
        <meshBasicMaterial color={color} transparent opacity={active ? 0.72 : 0.32} blending={AdditiveBlending} />
      </mesh>
      <mesh rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[0.58, 0.004, 12, 96]} />
        <meshBasicMaterial color={color} transparent opacity={active ? 0.54 : 0.2} blending={AdditiveBlending} />
      </mesh>
      {dendrites.map((points, index) => (
        <Line key={index} points={points} color={color} transparent opacity={active ? 0.36 : 0.16} lineWidth={1} />
      ))}
    </group>
  );
}

function SynapseSignal({ claim, index, selected }: { claim: DebateClaim; index: number; selected: boolean }) {
  const color = claimColor(claim);
  const curve = useMemo(() => curveFor(claim.agent_id, index), [claim.agent_id, index]);
  const packet = useRef<Mesh<SphereGeometry, MeshBasicMaterial>>(null);
  const echo = useRef<Mesh<SphereGeometry, MeshBasicMaterial>>(null);
  const points = useMemo(() => curve.getPoints(72), [curve]);
  const tube = useMemo(() => new TubeGeometry(curve, 96, selected ? 0.01 : 0.0045, 8, false), [curve, selected]);

  useFrame(({ clock }) => {
    const speed = selected ? 0.22 : 0.13;
    const t = (clock.elapsedTime * speed + index * 0.17) % 1;
    const p = curve.getPoint(t);
    const q = curve.getPoint((1 - t + 0.22) % 1);

    if (packet.current) {
      packet.current.position.copy(p);
      packet.current.scale.setScalar(selected ? 1.35 : 0.85);
    }
    if (echo.current) {
      echo.current.position.copy(q);
      echo.current.scale.setScalar(selected ? 0.95 : 0.62);
    }
  });

  return (
    <group>
      <mesh geometry={tube}>
        <meshBasicMaterial color={color} transparent opacity={selected ? 0.24 : 0.08} blending={AdditiveBlending} depthWrite={false} />
      </mesh>
      <Line points={points} color={color} transparent opacity={selected ? 0.74 : 0.22} lineWidth={selected ? 2 : 1} />
      <mesh ref={packet}>
        <sphereGeometry args={[0.045, 18, 18]} />
        <meshBasicMaterial color={color} transparent opacity={0.94} blending={AdditiveBlending} />
      </mesh>
      <mesh ref={echo}>
        <sphereGeometry args={[0.03, 16, 16]} />
        <meshBasicMaterial color="#dff9fb" transparent opacity={selected ? 0.72 : 0.32} blending={AdditiveBlending} />
      </mesh>
    </group>
  );
}

function MemoryCrystal({ selectedClaim }: { selectedClaim?: DebateClaim }) {
  const mesh = useRef<Mesh<OctahedronGeometry, MeshBasicMaterial>>(null);
  const color = selectedClaim ? claimColor(selectedClaim) : "#9bf6ff";

  useFrame(({ clock }) => {
    if (!mesh.current) return;
    mesh.current.rotation.x = clock.elapsedTime * 0.18;
    mesh.current.rotation.y = clock.elapsedTime * 0.28;
    mesh.current.scale.setScalar(1 + Math.sin(clock.elapsedTime * 1.6) * 0.04);
    mesh.current.material.color = new Color(color);
  });

  return (
    <group>
      <mesh ref={mesh}>
        <octahedronGeometry args={[0.42, 1]} />
        <meshBasicMaterial color={color} transparent opacity={0.46} blending={AdditiveBlending} side={DoubleSide} depthWrite={false} />
      </mesh>
      <mesh scale={1.35}>
        <octahedronGeometry args={[0.42, 1]} />
        <meshBasicMaterial color="#dff9fb" wireframe transparent opacity={0.2} blending={AdditiveBlending} />
      </mesh>
      <mesh>
        <torusGeometry args={[0.92, 0.003, 8, 140]} />
        <meshBasicMaterial color={color} transparent opacity={0.28} blending={AdditiveBlending} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.16, 0.0025, 8, 140]} />
        <meshBasicMaterial color="#9bf6ff" transparent opacity={0.18} blending={AdditiveBlending} />
      </mesh>
    </group>
  );
}

function EvidenceSparks({ claims }: { claims: DebateClaim[] }) {
  const group = useRef<Group>(null);
  const sparkMaterial = useMemo(() => new MeshBasicMaterial({ color: "#f4c76b", transparent: true, opacity: 0.88, blending: AdditiveBlending }), []);
  const sparkGeometry = useMemo(() => new SphereGeometry(0.018, 10, 10), []);
  const sparks = useMemo(() => {
    return claims.flatMap((claim, claimIndex) =>
      claim.evidence.map((_, evidenceIndex) => ({
        id: `${claim.claim_id}-${evidenceIndex}`,
        angle: claimIndex * 1.12 + evidenceIndex * 0.44,
        radius: 0.86 + evidenceIndex * 0.12,
        height: -0.16 + evidenceIndex * 0.08
      }))
    );
  }, [claims]);

  useFrame(({ clock }) => {
    if (!group.current) return;
    group.current.rotation.y = clock.elapsedTime * 0.1;
  });

  return (
    <group ref={group}>
      {sparks.map((spark) => (
        <mesh
          key={spark.id}
          geometry={sparkGeometry}
          material={sparkMaterial}
          position={[Math.cos(spark.angle) * spark.radius, spark.height, Math.sin(spark.angle) * spark.radius]}
        />
      ))}
    </group>
  );
}

export function SynapticField({ claims, selectedClaimId, onSelectClaim }: SynapticFieldProps) {
  const selectedClaim = claims.find((claim) => claim.claim_id === selectedClaimId);

  return (
    <Canvas className="synaptic-canvas" dpr={[1, 2]} gl={{ antialias: true, alpha: false }} camera={{ position: [0, 0.28, 7.2], fov: 45 }}>
      <PerspectiveCamera makeDefault position={[0, 0.28, 7.2]} fov={45} />
      <SceneRig />
      <group position={[0, -0.05, 0]}>
        {demoAgents.map((agent) => {
          const firstClaim = claims.find((claim) => claim.agent_id === agent.agent_id);
          return (
            <AgentNeuron
              active={firstClaim?.claim_id === selectedClaimId}
              agent={agent}
              key={agent.agent_id}
              onSelect={(event) => {
                event.stopPropagation();
                if (firstClaim) onSelectClaim(firstClaim.claim_id);
              }}
            />
          );
        })}
        {claims.map((claim, index) => (
          <SynapseSignal claim={claim} index={index} key={claim.claim_id} selected={claim.claim_id === selectedClaimId} />
        ))}
        <EvidenceSparks claims={claims} />
        <MemoryCrystal selectedClaim={selectedClaim} />
      </group>
    </Canvas>
  );
}
