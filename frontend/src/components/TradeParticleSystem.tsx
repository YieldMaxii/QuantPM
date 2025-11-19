import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { Trade } from '../models';

interface TradeParticleSystemProps {
    trades: Trade[];
    marketPositions: Record<string, [number, number, number]>;
}

export const TradeParticleSystem = ({ trades, marketPositions }: TradeParticleSystemProps) => {
    // We'll use an InstancedMesh for performance
    const meshRef = useRef<THREE.InstancedMesh>(null);
    const count = 50; // Max concurrent particles
    
    // Store particle state: [active, x, y, z, age, type(0=buy,1=sell)]
    const particles = useMemo(() => {
        return new Float32Array(count * 6);
    }, []);

    const dummy = useMemo(() => new THREE.Object3D(), []);
    const lastTradeId = useRef<string | null>(null);
    const particleIndex = useRef(0);

    useFrame((state, delta) => {
        if (!meshRef.current) return;

        // Check for new trades
        if (trades.length > 0 && trades[0].market_id + trades[0].entry_time !== lastTradeId.current) {
            const trade = trades[0];
            lastTradeId.current = trade.market_id + trade.entry_time;
            
            // Spawn particle if we know the position
            const pos = marketPositions[trade.market_id];
            if (pos) {
                const idx = particleIndex.current;
                const offset = idx * 6;
                
                particles[offset] = 1; // Active
                particles[offset + 1] = pos[0]; // x
                particles[offset + 2] = pos[1] + 1; // y (start slightly above)
                particles[offset + 3] = pos[2]; // z
                particles[offset + 4] = 0; // Age
                particles[offset + 5] = trade.side === 'buy' ? 0 : 1; // Type

                particleIndex.current = (particleIndex.current + 1) % count;
            }
        }

        // Update particles
        for (let i = 0; i < count; i++) {
            const offset = i * 6;
            if (particles[offset] === 1) {
                // Update age
                particles[offset + 4] += delta;
                
                // Move up
                particles[offset + 2] += delta * 2; // Speed

                // Update transform
                dummy.position.set(
                    particles[offset + 1],
                    particles[offset + 2],
                    particles[offset + 3]
                );
                
                // Scale down as it ages
                const life = Math.max(0, 1 - particles[offset + 4]);
                dummy.scale.setScalar(life * 0.5);
                
                dummy.updateMatrix();
                meshRef.current.setMatrixAt(i, dummy.matrix);
                
                // Set color
                const isBuy = particles[offset + 5] === 0;
                meshRef.current.setColorAt(i, new THREE.Color(isBuy ? '#22c55e' : '#ef4444'));

                // Kill if too old
                if (particles[offset + 4] > 1.0) {
                    particles[offset] = 0;
                    dummy.scale.setScalar(0);
                    dummy.updateMatrix();
                    meshRef.current.setMatrixAt(i, dummy.matrix);
                }
            }
        }
        
        meshRef.current.instanceMatrix.needsUpdate = true;
        if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true;
    });

    return (
        <instancedMesh ref={meshRef} args={[undefined, undefined, count]}>
            <sphereGeometry args={[0.3, 16, 16]} />
            <meshBasicMaterial transparent opacity={0.8} />
        </instancedMesh>
    );
};

