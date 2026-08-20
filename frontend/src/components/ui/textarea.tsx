// Combined-build shim: the admin pages import Textarea from ui/textarea,
// but the M5 frontend defines it inside ui/input.tsx. Re-export it.
export { Textarea } from "./input";
