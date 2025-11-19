import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Environment, ContactShadows } from '@react-three/drei';
import { EventBuilding } from './EventBuilding';
import { TradeParticleSystem } from './TradeParticleSystem';
import type { Market, EventGroup, Trade } from '../models';
import { useMemo, useState, useRef, useEffect } from 'react';
import * as THREE from 'three';

interface VoxelWorldProps {
    markets: Market[];
    trades?: Trade[];
    onMarketClick?: (market: Market) => void;
}

// Camera controller component to handle smooth transitions
const CameraController = ({ expandedEvent, events, spacingX, columns, offsetX, offsetZ }: { 
    expandedEvent: string | null, 
    events: EventGroup[], 
    spacingX: number, 
    columns: number,
    offsetX: number,
    offsetZ: number
}) => {
    const [isAnimating, setIsAnimating] = useState(false);
    const targetPosition = useRef(new THREE.Vector3(0, 12, 25));
    const targetLookAt = useRef(new THREE.Vector3(0, 0, 0));
    const prevExpandedEvent = useRef<string | null>(undefined as any);

    useEffect(() => {
        // Only trigger animation if expandedEvent actually changed
        if (prevExpandedEvent.current === expandedEvent) {
            return;
        }
        prevExpandedEvent.current = expandedEvent;

        if (expandedEvent) {
            // Find the position of the expanded event
            const index = events.findIndex(e => e.event_slug === expandedEvent);
            if (index !== -1) {
                const row = Math.floor(index / columns);
                const col = index % columns;
                const x = col * spacingX + offsetX;
                const z = row * spacingX + offsetZ;

                // Target position: 70 degree angle looking at the event
                targetPosition.current.set(x, 20, z + 10);
                targetLookAt.current.set(x, 0, z);
            }
        } else {
            // Default head-on view
            targetPosition.current.set(0, 12, 25);
            targetLookAt.current.set(0, 0, 0);
        }
        setIsAnimating(true);
    }, [expandedEvent, events, spacingX, columns, offsetX, offsetZ]);

    useFrame((state, delta) => {
        if (!isAnimating) return;

        // Interpolate position
        state.camera.position.lerp(targetPosition.current, 0.1);
        state.controls?.target.lerp(targetLookAt.current, 0.1);
        
        state.controls?.update();

        // Check if close enough to stop animating
        if (state.camera.position.distanceTo(targetPosition.current) < 0.1 &&
            state.controls?.target.distanceTo(targetLookAt.current) < 0.1) {
            setIsAnimating(false);
        }
    });
    return null;
};

export const VoxelWorld = ({ markets, trades = [], onMarketClick }: VoxelWorldProps) => {
    // Group markets by event_slug
    const events = useMemo(() => {
        const groups: Record<string, EventGroup> = {};
        
        markets.forEach(market => {
            const slug = market.event_slug || 'misc';
            if (!groups[slug]) {
                const name = slug.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                groups[slug] = {
                    event_slug: slug,
                    name: name,
                    markets: []
                };
            }
            groups[slug].markets.push(market);
        });
        
        return Object.values(groups);
    }, [markets]);

    const [expandedEvent, setExpandedEvent] = useState<string | null>(null);

    // Layout configuration
    const spacingX = 8;
    const columns = 3;

    const handleEventClick = (slug: string) => {
        setExpandedEvent(expandedEvent === slug ? null : slug);
    };

    const gridWidth = (Math.min(events.length, columns) - 1) * spacingX;
    const gridHeight = (Math.ceil(events.length / columns) - 1) * spacingX;
    const offsetX = -gridWidth / 2;
    const offsetZ = -gridHeight / 2;

    // Calculate positions for all markets to pass to particle system
    const marketPositions = useMemo(() => {
        const positions: Record<string, [number, number, number]> = {};
        const marketSpacing = 2.5;

        events.forEach((event, index) => {
            const row = Math.floor(index / columns);
            const col = index % columns;
            const eventX = col * spacingX + offsetX;
            const eventZ = row * spacingX + offsetZ;

            // If expanded, calculate expanded positions
            // If not expanded, they are at event center (approx)
            // For particles, we want them to appear where the market IS.
            // This is tricky because positions animate.
            // For now, let's assume particles only show when expanded or just spawn at event center if collapsed.
            
            event.markets.forEach((market, mIndex) => {
                // Calculate expanded position relative to event
                const gridSize = Math.ceil(Math.sqrt(event.markets.length));
                const mRow = Math.floor(mIndex / gridSize);
                const mCol = mIndex % gridSize;
                const xRel = (mCol - gridSize / 2 + 0.5) * marketSpacing;
                const zRel = (mRow - gridSize / 2 + 0.5) * marketSpacing;

                // If this event is expanded, use expanded pos. Else use event center.
                if (expandedEvent === event.event_slug) {
                    positions[market.market_id] = [eventX + xRel, 0, eventZ + zRel];
                } else {
                    positions[market.market_id] = [eventX, 0, eventZ];
                }
            });
        });
        return positions;
    }, [events, expandedEvent, spacingX, columns, offsetX, offsetZ]);

    return (
        <Canvas 
            shadows 
            camera={{ position: [0, 12, 25], fov: 35 }}
            style={{ background: '#f0f2f5' }}
        >
            <ambientLight intensity={0.7} />
            <spotLight 
                position={[10, 20, 10]} 
                angle={0.3} 
                penumbra={1} 
                intensity={1} 
                castShadow 
                shadow-mapSize={2048}
            />
            <Environment preset="city" />

            <OrbitControls 
                enableRotate={true}
                enableZoom={true}
                minZoom={10}
                maxZoom={60}
                enablePan={true}
                maxPolarAngle={Math.PI / 2 - 0.1} // Don't go below ground
                minPolarAngle={0.1} // Allow almost top-down
                makeDefault
            />

            <CameraController 
                expandedEvent={expandedEvent} 
                events={events} 
                spacingX={spacingX} 
                columns={columns}
                offsetX={offsetX}
                offsetZ={offsetZ}
            />

            <group position={[offsetX, 0, offsetZ]}>
                {events.map((event, index) => {
                    const row = Math.floor(index / columns);
                    const col = index % columns;
                    const x = col * spacingX;
                    const z = row * spacingX;

                    // If another event is expanded, hide this one
                    const isHidden = expandedEvent !== null && expandedEvent !== event.event_slug;

                    return (
                        <EventBuilding
                            key={event.event_slug}
                            event={event}
                            position={[x, 0, z]}
                            isExpanded={expandedEvent === event.event_slug}
                            isHidden={isHidden}
                            onClick={() => handleEventClick(event.event_slug)}
                            onMarketClick={onMarketClick}
                        />
                    );
                })}
            </group>

            <TradeParticleSystem 
                trades={trades} 
                marketPositions={marketPositions} 
            />

            <ContactShadows 
                position={[0, -0.01, 0]} 
                opacity={0.4} 
                scale={60} 
                blur={2} 
                far={4} 
            />
        </Canvas>
    );
};
