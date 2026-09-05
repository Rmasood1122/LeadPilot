import {
  BarChart3,
  GraduationCap,
  KanbanSquare,
  LayoutGrid,
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
  // M9. Sits next to Pipeline because they are the same data seen two
  // ways -- the kanban for working a handful of leads by hand, the CRM
  // for the dashboard view and for editing hundreds at a time. Pipeline
  // stays first: it is the screen people open every morning.
  { href: "/crm", label: "CRM", icon: LayoutGrid },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
  { href: "/strategies", label: "Strategies", icon: Route },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  // Feature 2. Sits before Settings, not after: Settings is the conventional
  // last item, and burying the tutorials below it is the fastest way to make
  // sure nobody finds them. On mobile this is the 6th of 7 bottom tabs --
  // CRM made it seven, which is tight at 360px but still tappable.
  { href: "/learn", label: "Learn", icon: GraduationCap },
  { href: "/settings", label: "Settings", icon: Settings },
];
