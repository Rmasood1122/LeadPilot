import {
  BarChart3,
  CalendarDays,
  GraduationCap,
  KanbanSquare,
  LayoutGrid,
  Megaphone,
  Route,
  Settings,
  Users,
  Video,
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
  // Engagement Hub. Placed immediately after Campaigns and in this order
  // because that is the order the work happens in: a campaign produces a
  // booking, a booking produces a meeting. Both sit ABOVE Strategies, which is
  // a screen you visit while setting up and rarely afterwards, whereas these
  // two are opened on the days you have calls.
  { href: "/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/meetings", label: "Meetings", icon: Video },
  { href: "/strategies", label: "Strategies", icon: Route },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  // Feature 2. Sits before Settings, not after: Settings is the conventional
  // last item, and burying the tutorials below it is the fastest way to make
  // sure nobody finds them. On mobile this is the 6th of 7 bottom tabs --
  // CRM made it seven, which is tight at 360px but still tappable.
  { href: "/learn", label: "Learn", icon: GraduationCap },
  // Feature Group 8: members, approvals, white label.
  { href: "/team", label: "Team", icon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
];
