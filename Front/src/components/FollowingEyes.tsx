import { useEffect, useRef } from 'react';

const EYE_ASSET = '/assets/af98f.svg';

export default function FollowingEyes() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    if (!container || reduceMotion.matches) return;

    const eyes = Array.from(container.querySelectorAll<HTMLImageElement>('.following-eye'));
    const motions = eyes.map((eye) => ({ eye, current: 0, target: 0 }));
    let frame = 0;

    function animate() {
      let moving = false;
      motions.forEach((motion) => {
        const distance = motion.target - motion.current;
        if (Math.abs(distance) > 0.1) {
          motion.current += distance * 0.14;
          moving = true;
        } else {
          motion.current = motion.target;
        }
        motion.eye.style.rotate = `${motion.current}deg`;
      });
      frame = moving ? window.requestAnimationFrame(animate) : 0;
    }

    function handlePointerMove(event: PointerEvent) {
      if (event.pointerType !== 'mouse') return;
      motions.forEach((motion) => {
        const rect = motion.eye.getBoundingClientRect();
        const angle = Math.atan2(
          event.clientY - (rect.top + rect.height / 2),
          event.clientX - (rect.left + rect.width / 2),
        ) * (180 / Math.PI);
        const rawTarget = angle - 180;
        motion.target =
          motion.current + (((rawTarget - motion.current + 540) % 360) - 180);
      });
      if (!frame) frame = window.requestAnimationFrame(animate);
    }

    window.addEventListener('pointermove', handlePointerMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <div className="following-eyes" ref={containerRef} aria-hidden="true">
      <span className="eye eye-left">
        <img className="following-eye" src={EYE_ASSET} alt="" width="376" height="376" />
      </span>
      <span className="eye eye-right">
        <img className="following-eye" src={EYE_ASSET} alt="" width="376" height="376" />
      </span>
      <span className="eyes-spark eyes-spark-one">✦</span>
      <span className="eyes-spark eyes-spark-two">✦</span>
    </div>
  );
}
