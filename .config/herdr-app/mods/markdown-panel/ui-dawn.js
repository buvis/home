import { div, image } from "gpui-kit";
import { DAWN_H, DAWN_W, DAWN_MOTION } from "./ui.js";

const RING_FRAMES = 12;
const CLIP = 44;
const layerOf = (c, layer) => c.dawn.art.replace(/\.svg$/, `-${layer}.svg`);

const moving = (el, prop, motion, rising, scale = 1) => {
  const { from, to } = motion[prop];
  return el[prop](rising ? to * scale : from * scale).transition(prop, { duration: motion.duration, delay: motion.delay, easing: motion.easing });
};

export const dawnSky = (id, c, { width = DAWN_W, run = 0, rising = false, ring = RING_FRAMES } = {}) => {
  const scale = width / DAWN_W;
  const art = (layer) => image(layerOf(c, layer)).absolute().top(0).left(0).w(width).h(DAWN_H * scale);
  const faded = (layer) => moving(art(layer), "opacity", DAWN_MOTION[layer], rising);
  const sun = DAWN_MOTION.sun;
  const risingArt = (layer) => moving(art(layer), "top", sun, rising, scale);
  const circle = DAWN_MOTION.circle;
  const ringFrame = Math.min(RING_FRAMES, Math.max(0, ring));
  const ringArt = moving(risingArt(`ring-${ringFrame}`), "opacity", { ...circle, duration: Math.round(circle.duration * circle.opacityBy) }, rising);
  return div().id(`${id}-${run}`).absolute().top(0).left(0).w(width).h(DAWN_H).overflow_hidden().children([
    art("sky"), faded("night"), faded("glow"), art("stars"), faded("clouds"),
    div().id(`${id}-${run}-sun`).absolute().top(0).left(0).w(width).h(CLIP * scale).overflow_hidden().children([risingArt("sun"), ringArt]),
    art("fade"), faded("horizon"),
  ]);
};

export const DAWN_RING_MS = (frame) => DAWN_MOTION.circle.delay + Math.round((DAWN_MOTION.circle.duration * frame) / RING_FRAMES);
export { RING_FRAMES };
