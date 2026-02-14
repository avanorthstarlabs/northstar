"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Billboard, Text } from "@react-three/drei";
import * as THREE from "three";

interface BillboardFighterProps {
  position: [number, number, number];
  label: string;
  color: string;
  flipX: boolean;
  hp: number;
  isHurt: boolean;
  isKO: boolean;
}

export function BillboardFighter({ position, label, color, flipX, hp, isHurt, isKO }: BillboardFighterProps) {
  const groupRef = useRef<THREE.Group>(null);
  const meshRef = useRef<THREE.Mesh>(null);

  useFrame(() => {
    if (!groupRef.current) return;

    if (isKO) {
      // Fallen over
      groupRef.current.rotation.z = THREE.MathUtils.lerp(groupRef.current.rotation.z, Math.PI / 2, 0.05);
      groupRef.current.position.y = THREE.MathUtils.lerp(groupRef.current.position.y, 0.3, 0.05);
    } else if (isHurt) {
      // Shake on hit
      groupRef.current.position.x = position[0] + (Math.random() - 0.5) * 0.15;
    } else {
      // Idle bob
      groupRef.current.position.x = position[0];
      groupRef.current.position.y = position[1] + Math.sin(Date.now() * 0.003) * 0.04;
      groupRef.current.rotation.z = 0;
    }
  });

  const opacity = hp > 0 ? 0.95 : 0.4;

  return (
    <Billboard position={position} follow lockX={false} lockY={false} lockZ={false}>
      <group ref={groupRef}>
        {/* Fighter body */}
        <mesh ref={meshRef} scale={flipX ? [-1, 1, 1] : [1, 1, 1]}>
          <planeGeometry args={[1.4, 2.2]} />
          <meshStandardMaterial
            color={color}
            transparent
            opacity={opacity}
            side={THREE.DoubleSide}
            emissive={color}
            emissiveIntensity={isHurt ? 0.8 : 0.15}
          />
        </mesh>

        {/* Name label */}
        <Text
          position={[0, 1.5, 0]}
          fontSize={0.22}
          color="#39ff14"
          anchorX="center"
          anchorY="bottom"
          outlineWidth={0.02}
          outlineColor="#000"
          font={undefined}
        >
          {label}
        </Text>
      </group>
    </Billboard>
  );
}
