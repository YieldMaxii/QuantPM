import { useRef, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text, RoundedBox, Html } from '@react-three/drei';
import type { EventGroup, Market } from '../models';
import * as THREE from 'three';
import { MarketBuilding } from './MarketBuilding';
import { getProbabilityColor } from '../utils/colors';

interface EventBuildingProps {
    event: EventGroup;
    position: [number, number, number];
    isExpanded: boolean;
    isHidden: boolean;
    onClick: () => void;
    onMarketClick?: (market: Market) => void;
}

export const EventBuilding = ({ event, position, isExpanded, isHidden, onClick, onMarketClick }: EventBuildingProps) => {
    const groupRef = useRef<THREE.Group>(null);
    const [hovered, setHover] = useState(false);

    // Animation state
    const [expandProgress, setExpandProgress] = useState(0);
    const [visibilityProgress, setVisibilityProgress] = useState(1);

    useFrame((state, delta) => {
        // Animate expansion
        const targetExpand = isExpanded ? 1 : 0;
        if (Math.abs(expandProgress - targetExpand) > 0.001) {
            setExpandProgress(THREE.MathUtils.lerp(expandProgress, targetExpand, delta * 3));
        }

        // Animate visibility (fade out if hidden)
        const targetVis = isHidden ? 0 : 1;
        if (Math.abs(visibilityProgress - targetVis) > 0.001) {
            setVisibilityProgress(THREE.MathUtils.lerp(visibilityProgress, targetVis, delta * 5));
        }

        // Hover effect for main building
        if (groupRef.current && !isExpanded && !isHidden) {
            const yTarget = hovered ? 0.2 : 0;
            groupRef.current.position.y = THREE.MathUtils.lerp(groupRef.current.position.y, yTarget, delta * 5);
        }
    });

    // Calculate average outcome for the main building color
    const avgOutcome = event.markets.reduce((acc, m) => acc + m.outcome, 0) / event.markets.length;
    const baseColor = getProbabilityColor(avgOutcome);

    // Layout for expanded markets
    const marketSpacing = 2.5;
    
    return (
        <group position={position} scale={[visibilityProgress, visibilityProgress, visibilityProgress]}>
            {/* Main Event Building (The Hub) */}
            <group 
                ref={groupRef} 
                onClick={(e) => { e.stopPropagation(); onClick(); }}
                onPointerOver={() => setHover(true)}
                onPointerOut={() => setHover(false)}
                visible={expandProgress < 0.9} 
            >
                {/* Base */}
                <RoundedBox args={[4, 0.5, 4]} radius={0.2} smoothness={4} position={[0, 0.25, 0]}>
                    <meshStandardMaterial color="#ffffff" transparent opacity={visibilityProgress} />
                </RoundedBox>
                
                {/* Center Pillar */}
                <RoundedBox args={[3, 1.5, 3]} radius={0.1} smoothness={4} position={[0, 1.25, 0]}>
                    <meshStandardMaterial 
                        color={baseColor} 
                        transparent 
                        opacity={0.9 * visibilityProgress}
                    />
                </RoundedBox>

                {/* Label */}
                <Html position={[0, 2.5, 0]} center transform={false} distanceFactor={15} style={{ pointerEvents: 'none' }}>
                    <div style={{
                        background: 'rgba(255, 255, 255, 0.95)',
                        padding: '8px 16px',
                        borderRadius: '8px',
                        boxShadow: '0 4px 10px rgba(0,0,0,0.1)',
                        textAlign: 'center',
                        width: '200px',
                        opacity: (1 - expandProgress) * visibilityProgress,
                        transition: 'opacity 0.2s'
                    }}>
                        <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#111' }}>{event.name}</div>
                        <div style={{ fontSize: '12px', color: '#666' }}>{event.markets.length} Outcomes</div>
                    </div>
                </Html>
            </group>

            {/* Expanded Markets */}
            <group visible={expandProgress > 0.01}>
                {event.markets.map((market, index) => {
                    // Grid layout relative to center
                    const gridSize = Math.ceil(Math.sqrt(event.markets.length));
                    const row = Math.floor(index / gridSize);
                    const col = index % gridSize;
                    const xTarget = (col - gridSize / 2 + 0.5) * marketSpacing;
                    const zTarget = (row - gridSize / 2 + 0.5) * marketSpacing;

                    const x = xTarget * expandProgress;
                    const z = zTarget * expandProgress;
                    
                    const scale = expandProgress;

                    return (
                        <group 
                            key={market.market_id} 
                            position={[x, 0, z]} 
                            scale={[scale, scale, scale]}
                            onClick={(e) => {
                                e.stopPropagation();
                                if (onMarketClick) onMarketClick(market);
                            }}
                        >
                            <MarketBuilding 
                                market={market} 
                                position={[0, 0, 0]} 
                            />
                        </group>
                    );
                })}
            </group>
            
            {/* Back Button / Title when expanded */}
            {isExpanded && (
                <Html position={[0, 0, 5]} center transform={false} distanceFactor={15}>
                    <div style={{
                        background: 'rgba(255, 255, 255, 0.9)',
                        padding: '8px 16px',
                        borderRadius: '20px',
                        cursor: 'pointer',
                        fontWeight: 'bold',
                        color: '#333',
                        boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
                        opacity: expandProgress
                    }} onClick={(e) => { e.stopPropagation(); onClick(); }}>
                        ← Back to Events
                    </div>
                </Html>
            )}
        </group>
    );
};
