/**
 * Aethvion Suite — Particle Sphere
 * Animated 3D particle sphere rendered on a 2D canvas.
 * Reacts to AI "speaking" state with expansion, glow, and speed changes.
 * Mood-aware: color adapts via setColor().
 */

const ParticleSphere = (() => {
    let canvas = null;
    let ctx    = null;
    let animId = null;

    // Animation state
    let angle   = 0;
    let active  = false;   // "talking" — sphere expands and glows
    let visible = false;   // only run RAF loop when visible

    // Color (RGB, updates with mood)
    let color = { r: 0, g: 217, b: 255 };

    // Particle count
    const N = 240;

    // Radii
    const BASE_RADIUS   = 108;
    const ACTIVE_RADIUS = 130;

    // Rotation speeds
    const BASE_SPEED   = 0.0025;
    const ACTIVE_SPEED = 0.010;

    // Pre-compute unit-sphere positions via Fibonacci lattice (even distribution)
    const basePoints = (() => {
        const pts = [];
        const gr  = (1 + Math.sqrt(5)) / 2;   // golden ratio
        for (let i = 0; i < N; i++) {
            const theta = Math.acos(1 - 2 * (i + 0.5) / N);
            const phi   = 2 * Math.PI * i / gr;
            pts.push({
                x:     Math.sin(theta) * Math.cos(phi),
                y:     Math.sin(theta) * Math.sin(phi),
                z:     Math.cos(theta),
                phase: Math.random() * Math.PI * 2   // breath offset
            });
        }
        return pts;
    })();

    // ── Transforms ────────────────────────────────────────────────────────────

    function rotateY(x, z, a) {
        return {
            rx: x * Math.cos(a) - z * Math.sin(a),
            rz: x * Math.sin(a) + z * Math.cos(a)
        };
    }

    function project(x, y, z, cx, cy, radius) {
        const depth = 2.8;
        const scale = depth / (depth + z);
        return {
            px:   cx + x * radius * scale,
            py:   cy + y * radius * scale,
            size: scale,
            z
        };
    }

    // ── Main draw loop ─────────────────────────────────────────────────────────

    function draw() {
        if (!canvas || !ctx || !visible) return;

        const w  = canvas.width;
        const h  = canvas.height;
        const cx = w / 2;
        const cy = h / 2;

        const t = performance.now() / 1000;

        // Radius smoothly approaches target
        const targetRadius = active
            ? BASE_RADIUS + (ACTIVE_RADIUS - BASE_RADIUS) * (0.55 + Math.sin(t * 2.8) * 0.45)
            : BASE_RADIUS;

        // Speed ramp (angle increments per frame, ~60fps assumed)
        angle += active ? ACTIVE_SPEED : BASE_SPEED;

        // Clear
        ctx.clearRect(0, 0, w, h);

        // Ambient inner glow when talking
        if (active) {
            const grd = ctx.createRadialGradient(cx, cy, targetRadius * 0.25, cx, cy, targetRadius * 1.5);
            grd.addColorStop(0, `rgba(${color.r},${color.g},${color.b},0.07)`);
            grd.addColorStop(1, 'transparent');
            ctx.fillStyle = grd;
            ctx.fillRect(0, 0, w, h);
        }

        // Project all particles
        const pts = basePoints.map(p => {
            const { rx, rz } = rotateY(p.x, p.z, angle);
            // Subtle breathing
            const breathe = 1 + Math.sin(t * 1.4 + p.phase) * 0.012;
            return project(rx * breathe, p.y * breathe, rz, cx, cy, targetRadius);
        });

        // Painter's algorithm: back-to-front
        pts.sort((a, b) => a.z - b.z);

        const { r, g, b } = color;

        for (const p of pts) {
            const depthFactor = (p.size - 0.5) / 0.5;   // 0..1 range

            const alpha   = active
                ? 0.25 + depthFactor * 0.75
                : 0.12 + depthFactor * 0.5;

            const dotSize = active
                ? 0.75 + depthFactor * 1.7
                : 0.55 + depthFactor * 1.15;

            // Soft halo on front-facing particles
            if (depthFactor > 0.55) {
                ctx.beginPath();
                ctx.arc(p.px, p.py, dotSize * 2.8, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(${r},${g},${b},${alpha * 0.07})`;
                ctx.fill();
            }

            // Core dot
            ctx.beginPath();
            ctx.arc(p.px, p.py, dotSize, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
            ctx.fill();
        }

        animId = requestAnimationFrame(draw);
    }

    // ── Public API ─────────────────────────────────────────────────────────────

    return {
        /** Attach to a canvas element and begin rendering */
        init(canvasEl) {
            canvas  = canvasEl;
            ctx     = canvas.getContext('2d');
            visible = true;
            angle   = 0;
            if (animId) cancelAnimationFrame(animId);
            draw();
        },

        /** Show or hide without destroying state */
        setVisible(isVisible) {
            visible = !!isVisible;
            if (visible && !animId) draw();
            if (!visible && animId) {
                cancelAnimationFrame(animId);
                animId = null;
            }
        },

        /** Talking = true expands the sphere and makes it glow */
        setActive(isActive) {
            active = !!isActive;
        },

        /** Update the base colour to match Misaka's current mood */
        setColor(r, g, b) {
            color = { r, g, b };
        },

        /** Stop the animation loop and clear the canvas */
        destroy() {
            if (animId) cancelAnimationFrame(animId);
            animId  = null;
            visible = false;
            if (canvas && ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    };
})();

window.ParticleSphere = ParticleSphere;
