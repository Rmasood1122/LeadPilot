import {
  BarChart3,
  GraduationCap,
  KanbanSquare,
  Megaphone,
  Route,
  Settings,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Nav sections per project knowledge section H. */
export const NAV: NavItem[] = [
  { href: "/pipeline", label: "Pipeline", icon: KanbanSquare },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
  { href: "/strategies", label: "Strategies", icon: Route },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  // Feature 2. Sits before Settings, not after: Settings is the conventional
  // last item, and burying the tutorials below it is the fastest way to make
  // sure nobody finds them. On mobile this is the 5th of 6 bottom tabs.
  { href: "/learn", label: "Learn", icon: GraduationCap },
  { href: "/settings", label: "Settings", icon: Settings },
];
