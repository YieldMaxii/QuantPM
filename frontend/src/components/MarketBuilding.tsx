import { useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text, RoundedBox, Html } from '@react-three/drei';
import type { Market } from '../models';
import * as THREE from 'three';
import { getProbabilityColor } from '../utils/colors';

interface MarketBuildingProps {
    market: Market;
    position: [number, number, number];
}

export const MarketBuilding = ({ market, position }: MarketBuildingProps) => {
    const meshRef = useRef<THREE.Group>(null);
    const [hovered, setHover] = useState(false);

    // Height represents probability/price (0-1)
    const outcome = market.outcome || 0;
    const minHeight = 0.2;
    const maxHeight = 5.0;
    const height = minHeight + (outcome * (maxHeight - minHeight));
    
    // Use granular color utility
    const baseColor = getProbabilityColor(outcome);
    
    useFrame((state) => {
        if (meshRef.current && hovered) {
            meshRef.current.position.y = THREE.MathUtils.lerp(meshRef.current.position.y, 0.2, 0.1);
        } else if (meshRef.current) {
            meshRef.current.position.y = THREE.MathUtils.lerp(meshRef.current.position.y, 0, 0.1);
        }
    });

    // Clean up name: remove "Will the " and " win..."
    const cleanName = market.name
        .replace(/^Will the /i, '')
        .replace(/^Will /i, '')
        .replace(/ win .*$/i, '')
        .replace(/ \?$/i, '');

    return (
        <group position={position} ref={meshRef}>
            {/* Card Base */}
            <RoundedBox 
                args={[2.8, 0.2, 2.8]} 
                radius={0.1} 
                smoothness={4}
                position={[0, 0.1, 0]}
                onPointerOver={() => setHover(true)}
                onPointerOut={() => setHover(false)}
            >
                <meshStandardMaterial color="#ffffff" />
            </RoundedBox>

            {/* Probability Bar */}
            <RoundedBox
                args={[2.4, height, 2.4]}
                radius={0.05}
                smoothness={4}
                position={[0, 0.2 + height / 2, 0]}
            >
                <meshStandardMaterial 
                    color={baseColor} 
                    transparent 
                    opacity={0.9}
                    roughness={0.2}
                    metalness={0.1}
                />
            </RoundedBox>

            {/* HTML Overlay - Only visible on hover or if very high probability */}
            <Html position={[0, height + 0.5, 0]} center transform={false} distanceFactor={15} style={{ pointerEvents: 'none' }}>
                <div style={{
                    background: 'rgba(255, 255, 255, 0.95)',
                    padding: '6px 10px',
                    borderRadius: '6px',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                    width: '140px',
                    textAlign: 'center',
                    opacity: hovered ? 1 : 0, // Only show on hover to reduce clutter
                    transform: `translateY(${hovered ? 0 : 10}px)`, // Slide up animation
                    transition: 'all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
                    fontFamily: 'Inter, system-ui, sans-serif',
                    border: '1px solid rgba(0,0,0,0.05)'
                }}>
                    <div style={{ 
                        fontSize: '11px', 
                        fontWeight: '600', 
                        color: '#4b5563', 
                        marginBottom: '2px',
                        lineHeight: '1.2',
                        whiteSpace: 'normal' // Allow wrapping
                    }}>
                        {cleanName}
                    </div>
                    <div style={{ fontSize: '16px', fontWeight: '800', color: '#111' }}>
                        {(outcome * 100).toFixed(1)}%
                    </div>
                </div>
            </Html>
        </group>
    );
};
