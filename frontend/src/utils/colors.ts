import * as THREE from 'three';

/**
 * Generates a color based on probability (0-1) using a granular HSL spectrum.
 * 
 * Range:
 * 0.0 - 0.2: Red (Hue 0 - 30)
 * 0.2 - 0.4: Orange (Hue 30 - 60)
 * 0.4 - 0.6: Yellow/Green (Hue 60 - 120)
 * 0.6 - 0.8: Green/Teal (Hue 120 - 180)
 * 0.8 - 1.0: Blue/Purple (Hue 180 - 240)
 */
export const getProbabilityColor = (probability: number): THREE.Color => {
    // Clamp probability
    const p = Math.max(0, Math.min(1, probability));
    
    // Map 0-1 to Hue 0-220 (Red to Blue)
    // We use a non-linear mapping to give more granularity to the middle ranges
    // or just a direct mapping for a full rainbow
    
    // Let's use a custom gradient approach for better aesthetics
    // 0.0 -> Red (#ef4444)
    // 0.5 -> Yellow (#eab308)
    // 1.0 -> Emerald (#10b981)
    
    // Using HSL:
    // Red: 0
    // Yellow: 50
    // Green: 140
    
    // We want a smooth transition.
    // Let's map 0-1 to Hue 0-150 (Red to Green) which is standard for "bad to good" or "low to high"
    // But user asked for "many shades", so we want to ensure 0.45 looks different from 0.46
    
    const hue = p * 150; // 0 to 150
    const saturation = 0.8 + (p * 0.1); // 80% to 90%
    const lightness = 0.5 + (p * 0.1); // 50% to 60%
    
    return new THREE.Color().setHSL(hue / 360, saturation, lightness);
};

